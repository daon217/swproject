"""
[preprocessor.py]
OpenCV(cv2)와 NumPy를 활용한 이미지 디코딩, 가로 블록 타일링(Tiling),
앵커 기반 관심 영역(ROI) 슬라이싱 및 원본 메모리 즉시 해제,
CLAHE + 블러 보정을 수행하는 컴퓨터 비전 전처리 모듈입니다.
"""

import base64
import gc
from typing import List, Optional, Tuple
import cv2
import numpy as np

from app.config import settings


def decode_image(image_source: bytes | str) -> Optional[np.ndarray]:
    """
    Base64 문자열 또는 Raw Bytes 데이터를 OpenCV BGR NumPy 배열로 디코딩합니다.
    메모리 복사를 최소화하기 위해 np.frombuffer를 사용합니다.
    """
    try:
        if isinstance(image_source, str):
            # "data:image/jpeg;base64,..." 헤더가 포함된 경우 분리
            if "," in image_source:
                image_source = image_source.split(",", 1)[1]
            raw_bytes = base64.b64decode(image_source)
        elif isinstance(image_source, (bytes, bytearray)):
            raw_bytes = bytes(image_source)
        else:
            return None

        np_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        return image
    except Exception:
        return None


def split_into_horizontal_tiles(
    image: np.ndarray,
    tile_height: int = settings.TILE_MAX_HEIGHT,
    overlap: int = settings.TILE_OVERLAP,
) -> List[Tuple[int, np.ndarray]]:
    """
    [1단계: 가로 블록 단위 분할 (Tiling)]
    쇼핑몰 상세페이지처럼 세로로 긴 이미지가 입력되었을 때,
    OCR 인식률 저하와 OOM(Out-Of-Memory)을 방지하기 위해 가로 블록(Tile) 단위로 분할합니다.

    Returns:
        List[Tuple[y_offset, tile_ndarray]]: 원본 기준 Y 시작 좌표와 타일 이미지 튜플 리스트
    """
    height, _ = image.shape[:2]

    # 이미지 높이가 타일 기준치 이하이면 분할 없이 원본 뷰 반환
    if height <= tile_height:
        return [(0, image)]

    tiles: List[Tuple[int, np.ndarray]] = []
    stride = max(tile_height - overlap, 200)

    for y_start in range(0, height, stride):
        y_end = min(y_start + tile_height, height)
        tile = image[y_start:y_end, :]
        tiles.append((y_start, tile))
        if y_end >= height:
            break

    return tiles


def crop_roi_and_release_memory(
    full_image: np.ndarray,
    anchor_y: int,
    crop_height: int = settings.ROI_CROP_HEIGHT,
    top_padding: int = settings.ROI_TOP_PADDING,
) -> np.ndarray:
    """
    [2단계: 앵커 Y 좌표 기준 하단 ROI 크롭 및 원본 메모리 즉시 해제]
    1차 스캔에서 '원재료명', '성분명' 등 앵커 키워드가 발견되면,
    해당 바운딩 박스의 Y 좌표를 기준으로 아래쪽 영역(y ~ y + 500px)만 Array Slicing으로 잘라내고,
    원본 고해상도 이미지 배열 참조를 끊어 메모리를 즉시 회수합니다.
    """
    img_h, img_w = full_image.shape[:2]

    # 크롭할 Y 범위 산출 (앵커 문구 자체도 포함되도록 상단 약간의 여유 마진 부여)
    y_start = max(0, int(anchor_y) - top_padding)
    y_end = min(img_h, int(anchor_y) + crop_height)

    # 주의: NumPy 슬라이싱(full_image[y_start:y_end, :])은 원본 버퍼의 View를 참조하므로
    # 원본 대용량 배열이 가비지 컬렉션(GC)되지 않습니다.
    # 반드시 .copy()로 독립된 작은 ROI 메모리 블록만 복제한 뒤 원본을 해제합니다.
    roi_cropped = full_image[y_start:y_end, 0:img_w].copy()

    # 원본 대용량 프레임 메모리 즉시 해제 유도 (OOM 방지)
    del full_image
    gc.collect()

    return roi_cropped


def enhance_roi_for_ocr(
    roi_image: np.ndarray,
    use_adaptive_binarization: bool = False,
) -> np.ndarray:
    """
    [3단계: 스크롤 블러 및 저대비 보정을 위한 OpenCV 정밀 전처리]
    1. Grayscale 변환 (3채널 -> 1채널로 연산량 1/3 축소)
    2. CLAHE (Contrast Limited Adaptive Histogram Equalization, clipLimit=2.0, tileGridSize=(8,8))로
       배경과 글자 간의 국소 대비(Local Contrast) 극대화
    3. 가우시안 블러 + 언샤프 마스크(Unsharp Masking) 또는 적응형 이진화로 스크롤 모션 블러 보정
    """
    # 1. Grayscale 변환
    if len(roi_image.shape) == 3:
        gray = cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = roi_image.copy()

    # 2. CLAHE 적용 (clipLimit=2.0, tileGridSize=(8,8))
    clahe = cv2.createCLAHE(
        clipLimit=settings.CLAHE_CLIP_LIMIT,
        tileGridSize=settings.CLAHE_TILE_GRID_SIZE,
    )
    clahe_img = clahe.apply(gray)

    # 3. 스크롤 블러 및 노이즈 보정
    # 미세 노이즈를 가우시안 블러로 억제한 뒤, 가중합(addWeighted)으로 문자 경계선(Edge)을 선명화
    blurred = cv2.GaussianBlur(clahe_img, (3, 3), 0)
    sharpened = cv2.addWeighted(clahe_img, 1.5, blurred, -0.5, 0)

    if use_adaptive_binarization:
        # 배경 그라데이션이 심한 경우를 위한 적응형 가우시안 이진화 옵션
        processed = cv2.adaptiveThreshold(
            sharpened,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=15,
            C=8,
        )
    else:
        processed = sharpened

    # PaddleOCR 입력 호환성을 위해 3채널 BGR 형태로 변환하여 반환
    return cv2.cvtColor(processed, cv2.COLOR_GRAY2BGR)

