"""
[config.py]
꿀픽(KkulPick) 비전 AI 파이프라인의 환경 변수 및 하이퍼파라미터 설정 모듈입니다.
Redis 연결 정보, 15프레임 하드 타임아웃(Hard Timeout), ROI 크롭 크기, 앵커 키워드 등을 관리합니다.
"""

import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # 프로젝트 기본 설정
    PROJECT_NAME: str = "KkulPick Vision AI Pipeline"
    API_V1_STR: str = "/api/v1/vision"

    # Redis & Celery 브로커/백엔드 설정
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB_STATE: int = int(os.getenv("REDIS_DB_STATE", 0))    # 세션 상태 관리용 DB
    REDIS_DB_BROKER: int = int(os.getenv("REDIS_DB_BROKER", 1))  # Celery 메시지 큐용 DB
    REDIS_DB_BACKEND: int = int(os.getenv("REDIS_DB_BACKEND", 2)) # Celery 결과 저장용 DB

    @property
    def REDIS_STATE_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_STATE}"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_BROKER}"

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB_BACKEND}"

    # 세션 및 생명주기(Lifecycle) 제어 상수
    SESSION_TTL_SECONDS: int = 1800          # Redis 세션 만료 시간 (30분, OOM 방지)
    MAX_FRAME_LIMIT: int = 15                # 시나리오 C: 최대 허용 프레임 수 (Hard Timeout = 15장)

    # OpenCV 전처리 및 ROI 크롭 파라미터
    TILE_MAX_HEIGHT: int = 1600              # 세로로 긴 상세페이지를 분할할 타일 높이(px)
    TILE_OVERLAP: int = 200                  # 타일 경계에서 앵커 텍스트가 잘리는 것을 방지하는 오버랩(px)
    ROI_CROP_HEIGHT: int = 500               # 앵커(Anchor) Y좌표 하단으로 크롭할 영역 높이(px)
    ROI_TOP_PADDING: int = 15                # 앵커 텍스트 상단 여유 마진(px)

    # OCR 입력 모양 고정 (메모리 증가 방지, devlog #66)
    # Paddle 추론 엔진은 새 입력 모양(크기)마다 메모리를 잡고 돌려주지 않는다. 페이지·줄마다 크기가 다르면
    # 분석할수록 워커 메모리가 계단식으로 오르고, 줄이 많은 페이지 한 장으로도 OOM이 난다.
    # 그래서 글자 검출 입력은 항상 같은 크기의 캔버스로, 글자 인식 입력은 항상 같은 폭·배치로 맞춘다.
    OCR_CANVAS_WIDTH: int = 1920             # 검출 입력 캔버스 폭(이보다 넓으면 축소, 좁으면 오른쪽을 흰색으로 채움)
    OCR_CANVAS_HEIGHT: int = 1600            # 검출 입력 캔버스 높이(= TILE_MAX_HEIGHT)
    # 검출 모델 입력의 긴 변(px). 1920 캔버스에 예전 값 736을 쓰면 글자가 너무 작아져 성분 재현율이 42% → 20%로 떨어졌다.
    # 1280이면 48%(원래보다 약간 높음), 메모리 0.83GiB로 고정.
    OCR_DET_LIMIT_SIDE: int = 1280
    # 인식 입력 폭은 이 비율(폭/높이 48px) 중 하나로만: 짧은 줄 8(384px), 긴 줄 20(960px). 더 긴 줄은 960px로 축소.
    # 측정(89줄 페이지, batch=1): 가변 28.6s·6.9GiB / 20 하나 19.7s·0.67GiB / 8,20 13.2s·0.70GiB / 6,12,20 13.1s·1.85GiB
    # 결과 일치율(가변 대비) 94~97%. 크기가 늘수록 메모리가 커지므로 2개를 권장.
    REC_WIDTH_RATIOS: str = "8,20"
    REC_BATCH_NUM: int = 1                   # 배치 크기도 모양의 일부. 1이면 인식 입력 모양이 하나뿐(측정상 속도 차이 없음)

    # Celery 자식 프로세스가 이 메모리(KiB)를 넘으면 작업을 마친 뒤 새 프로세스로 교체(안전장치)
    WORKER_MAX_MEMORY_PER_CHILD_KB: int = 1500000

    # CLAHE (Contrast Limited Adaptive Histogram Equalization) 파라미터
    CLAHE_CLIP_LIMIT: float = 2.0
    CLAHE_TILE_GRID_SIZE: tuple = (8, 8)

    # 성분표 탐색을 위한 앵커(Anchor) 키워드 리스트
    ANCHOR_KEYWORDS: List[str] = [
        "원재료명",
        "영양정보",
        "성분명",
        "원재료 및 함량",
        "원재료명및함량",
        "전성분",
        "원료명",
    ]


settings = Settings()

