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

