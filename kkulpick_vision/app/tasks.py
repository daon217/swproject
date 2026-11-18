"""
[tasks.py]
꿀픽(KkulPick) 3-Phase 비전 파이프라인의 핵심 비즈니스 로직을 수행하는 Celery 비동기 태스크 모듈입니다.
- Phase 1: 메타데이터 Vision Fallback (상품명 미수신 시 0초 차 프레임 최대 면적 텍스트 추출)
- Phase 2: 실시간 스트리밍 프레임 타일링 -> 앵커 탐색 -> ROI 크롭 & 메모리 해제 -> CLAHE 전처리 -> 성분 정제
- Phase 3: 조기 종료(Early Exit), 사용자 이탈(EOF), 서버 보호(15프레임 Hard Timeout) 생명주기 제어
"""

import gc
import json
import logging
from typing import Any, Dict, List, Optional
import redis

from app.celery_app import celery_app
from app.config import settings
from app.vision.ocr_engine import get_ocr_engine
from app.vision.preprocessor import (
    crop_roi_and_release_memory,
    decode_image,
    enhance_roi_for_ocr,
    split_into_horizontal_tiles,
)

logger = logging.getLogger(__name__)

# 워커 및 API 서버에서 공유하는 Redis Connection Pool
redis_pool = redis.ConnectionPool.from_url(
    settings.REDIS_STATE_URL,
    decode_responses=True,
)


def get_redis_client() -> redis.Redis:
    """Redis 클라이언트를 반환합니다."""
    return redis.Redis(connection_pool=redis_pool)


def get_session_key(session_id: str) -> str:
    """Redis Hash 키 네임스페이스 생성"""
    return f"kkulpick:vision:session:{session_id}"


def initialize_session_in_redis(
    session_id: str,
    product_name: Optional[str],
    price: Optional[int],
) -> Dict[str, Any]:
    """
    [Phase 1] `/api/v1/vision/init` 호출 시 Redis에 세션 상태 해시(Hash)를 생성합니다.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    has_product_name = bool(product_name and product_name.strip())
    source_of_meta = "html_crawler" if has_product_name else "vision_fallback"

    session_data = {
        "session_id": session_id,
        "status": "processing",
        "frame_count": "0",
        "product_name": product_name.strip() if has_product_name else "",
        "price": str(price) if price is not None else "",
        "source_of_meta": source_of_meta,
        "ingredients": json.dumps([], ensure_ascii=False),
        "message": "성분표 탐색 중입니다.",
        "early_exit_flag": "0",
    }

    r.hset(key, mapping=session_data)
    r.expire(key, settings.SESSION_TTL_SECONDS)
    return session_data


def finalize_session_state(
    r: redis.Redis,
    session_id: str,
    status: str,
    ingredients: List[str],
    message: str,
) -> None:
    """
    [Phase 3] 세션을 최종 상태(success 또는 analysis_unavailable)로 마감하고,
    남은 대기열의 프레임 태스크들이 즉시 작업을 스킵하도록 `early_exit_flag="1"`을 설정합니다.
    """
    key = get_session_key(session_id)
    r.hset(
        key,
        mapping={
            "status": status,
            "ingredients": json.dumps(ingredients, ensure_ascii=False),
            "message": message,
            "early_exit_flag": "1",
        },
    )
    r.expire(key, settings.SESSION_TTL_SECONDS)


# ==============================================================================
# [Phase 1 Task] 0초 차 최상단 화면 기반 상품명 Vision Fallback 태스크
# ==============================================================================
@celery_app.task(name="app.tasks.extract_metadata_fallback_task")
def extract_metadata_fallback_task(session_id: str, first_frame_b64: str) -> Dict[str, Any]:
    """
    [Phase 1: Fallback 로직]
    프론트엔드에서 안티 크롤링 등으로 `product_name`이 비어 있거나 null로 들어온 경우,
    Celery 워커가 즉시 `first_frame_image`(0초 차 최상단 화면)를 PaddleOCR로 스캔합니다.
    검출된 바운딩 박스들의 면적(Width × Height)을 계산해 가장 큰 글씨를 `product_name`으로 추출하여
    Redis 세션에 업데이트하고 `source_of_meta: "vision_fallback"`으로 기록합니다.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    if not r.exists(key):
        logger.warning(f"[Phase 1 Fallback] 존재하지 않는 세션입니다: {session_id}")
        return {"session_id": session_id, "updated": False}

    image = decode_image(first_frame_b64)
    if image is None:
        logger.warning(f"[Phase 1 Fallback] 이미지 디코딩 실패: {session_id}")
        return {"session_id": session_id, "updated": False}

    try:
        ocr_engine = get_ocr_engine()
        detected_title = ocr_engine.extract_largest_text_as_product_name(image)

        if detected_title:
            r.hset(
                key,
                mapping={
                    "product_name": detected_title,
                    "source_of_meta": "vision_fallback",
                },
            )
            logger.info(
                f"[Phase 1 Fallback 완료] session={session_id}, 추출된 상품명='{detected_title}'"
            )
            return {
                "session_id": session_id,
                "product_name": detected_title,
                "source_of_meta": "vision_fallback",
                "updated": True,
            }
        else:
            r.hset(key, "source_of_meta", "vision_fallback")
            return {"session_id": session_id, "updated": False}
    finally:
        # 0초 차 프레임 이미지 메모리 즉시 해제
        del image
        gc.collect()


# ==============================================================================
# [Phase 2 & 3 Task] 실시간 스트리밍 프레임 분석 및 조기 종료/타임아웃 제어 태스크
# ==============================================================================
@celery_app.task(name="app.tasks.process_frame_task")
def process_frame_task(
    session_id: str,
    frame_index: int,
    is_last_frame: bool,
    image_b64: str,
) -> Dict[str, Any]:
    """
    [Phase 2 & Phase 3 통합 파이프라인]
    1. 작업 전 Redis에서 세션의 현재 `status`를 확인해 이미 종료된 세션(`success` 또는 `analysis_unavailable`)이면 즉시 스킵(Early Exit).
    2. `frame_count`를 원자적(HINCRBY)으로 1 증가시키고 15프레임 도달 여부를 체크.
    3. OpenCV 가로 타일링 -> PaddleOCR 1차 스캔으로 앵커 키워드 탐색.
    4. 앵커 발견 시 하단 500px ROI 크롭 및 원본 이미지 메모리 즉시 해제 -> CLAHE 전처리 -> 성분 정규식 정제.
    5. 시나리오 A(성공), 시나리오 B(EOF 이탈), 시나리오 C(15프레임 Hard Timeout)에 따라 생명주기 마감.
    """
    r = get_redis_client()
    key = get_session_key(session_id)

    # --------------------------------------------------------------------------
    # [Step 1] 조기 종료(Early Exit) 사전 검사
    # 이미 앞선 프레임에서 성분표를 찾았거나 타임아웃된 세션이면 이미지 디코딩조차 하지 않고 즉시 스킵
    # --------------------------------------------------------------------------
    session_state = r.hgetall(key)
    if not session_state:
        logger.warning(f"[Phase 2] 세션 정보가 없습니다 ({session_id}). 작업을 건너뜁니다.")
        return {"session_id": session_id, "skipped": True, "reason": "session_not_found"}

    current_status = session_state.get("status", "processing")
    early_exit_flag = session_state.get("early_exit_flag", "0")

    if current_status != "processing" or early_exit_flag == "1":
        logger.info(
            f"[Phase 3 Early Exit Skip] 이미 종료된 세션({current_status})입니다. "
            f"session={session_id}, frame_index={frame_index} 스킵."
        )
        return {"session_id": session_id, "skipped": True, "reason": f"already_{current_status}"}

    # --------------------------------------------------------------------------
    # [Step 2] 프레임 카운트 원자적 증가 및 Hard Timeout(15프레임) 초과 검사
    # --------------------------------------------------------------------------
    current_frame_count: int = int(r.hincrby(key, "frame_count", 1))

    # 이미 15프레임을 초과하여 들어온 잔여 큐 작업인 경우 즉시 차단 (시나리오 C 방어)
    if current_frame_count > settings.MAX_FRAME_LIMIT:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.warning(
            f"[Phase 3 Hard Timeout] 15프레임 한도 초과 (현재 {current_frame_count}장). 강제 종료: {session_id}"
        )
        return {"session_id": session_id, "status": "analysis_unavailable", "reason": "hard_timeout"}

    # --------------------------------------------------------------------------
    # [Step 3] 이미지 디코딩 및 OpenCV 타일링 + 1차 앵커 탐색
    # --------------------------------------------------------------------------
    full_image = decode_image(image_b64)
    extracted_ingredients: List[str] = []

    if full_image is not None:
        ocr_engine = get_ocr_engine()

        # 3-1. 세로로 긴 이미지를 가로 블록 단위로 분할 (Tiling)
        tiles = split_into_horizontal_tiles(full_image)

        # 3-2. 1차 스캔: ["원재료명", "영양정보", "성분명", "원재료 및 함량"] 등 앵커 Y좌표 탐색
        anchor_y = ocr_engine.find_anchor_y_coordinate(tiles)

        # 타일 참조 리스트 정리
        del tiles

        if anchor_y is not None:
            # 3-3. 앵커 Y 좌표 기준 아래쪽 영역(y ~ y + 500px)만 ROI 크롭 & 원본 배열 즉시 메모리 해제
            roi_image = crop_roi_and_release_memory(
                full_image=full_image,
                anchor_y=anchor_y,
                crop_height=settings.ROI_CROP_HEIGHT,
            )
            full_image = None  # 원본 참조 명시적 제거

            try:
                # 3-4. 크롭된 ROI에 Grayscale -> CLAHE(clipLimit=2.0, tileGridSize=(8,8)) -> 블러 보정 적용
                enhanced_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=False)

                # 3-5. 2차 정밀 OCR 추출 및 정규표현식 기반 성분 리스트 정제
                extracted_ingredients = ocr_engine.extract_and_clean_ingredients(enhanced_roi)

                # 만약 기본 샤프닝 전처리에서 성분이 추출되지 않았다면 적응형 이진화로 1회 재시도
                if not extracted_ingredients:
                    binarized_roi = enhance_roi_for_ocr(roi_image, use_adaptive_binarization=True)
                    extracted_ingredients = ocr_engine.extract_and_clean_ingredients(binarized_roi)
                    del binarized_roi

                del enhanced_roi
            finally:
                del roi_image
                gc.collect()
        else:
            # 앵커가 없는 프레임도 즉시 메모리에서 해제
            del full_image
            gc.collect()

    # --------------------------------------------------------------------------
    # [Step 4] Phase 3 생명주기 제어 (시나리오 A / B / C 판정)
    # --------------------------------------------------------------------------

    # [시나리오 A: 정상 발견 - Early Exit]
    if len(extracted_ingredients) > 0:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="success",
            ingredients=extracted_ingredients,
            message="성분표 추출이 완료되었습니다.",
        )
        logger.info(
            f"[Phase 3 시나리오 A - Early Exit 성공] session={session_id}, "
            f"frame_index={frame_index}, 추출 성분 수={len(extracted_ingredients)}"
        )
        return {
            "session_id": session_id,
            "status": "success",
            "ingredients": extracted_ingredients,
        }

    # [시나리오 B: 사용자 이탈/방치 - EOF]
    # 요청의 is_last_frame == True인데 현재 프레임에서도 성분표를 찾지 못한 경우 즉시 중단
    if is_last_frame:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.info(
            f"[Phase 3 시나리오 B - EOF 종료] 마지막 프레임(index={frame_index})까지 성분표 미발견: {session_id}"
        )
        return {
            "session_id": session_id,
            "status": "analysis_unavailable",
            "reason": "eof_reached",
        }

    # [시나리오 C: 서버 보호 - Hard Timeout (15프레임 도달)]
    # frame_count가 15장(15프레임)에 도달할 때까지 성분표를 찾지 못하면 강제 종료
    if current_frame_count >= settings.MAX_FRAME_LIMIT:
        finalize_session_state(
            r=r,
            session_id=session_id,
            status="analysis_unavailable",
            ingredients=[],
            message="성분표를 찾지 못해 알레르기 분석이 불가합니다.",
        )
        logger.warning(
            f"[Phase 3 시나리오 C - 15프레임 Hard Timeout] 15장 도달 성분표 미발견 강제 종료: {session_id}"
        )
        return {
            "session_id": session_id,
            "status": "analysis_unavailable",
            "reason": "max_frames_15_timeout",
        }

    # 아직 탐색 중 (다음 프레임 대기)
    return {
        "session_id": session_id,
        "status": "processing",
        "frame_count": current_frame_count,
    }

