"""
[celery_app.py]
Celery 분산 작업 큐 인스턴스 및 워커 생명주기 시그널(Signal) 설정 모듈입니다.
워커 프로세스가 포크(Fork)/시작될 때 `worker_process_init` 시그널을 통해
PaddleOCR 싱글톤 모델을 메모리에 딱 한 번 미리 로드(Warm-up)합니다.
"""

import logging
from celery import Celery
from celery.signals import worker_process_init

from app.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kkulpick_vision_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.tasks"],
)

# Celery 운영 최적화 설정 (OOM 방지 및 공정한 분산 처리)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    # 한 워커가 한 번에 1개의 프레임 태스크만 가져오도록 제한 (무거운 비전 작업의 메모리 폭주 방지)
    worker_prefetch_multiplier=1,
    # 작업 완료 후에 ACK를 보내도록 설정
    task_acks_late=True,
    # 일정 횟수 이상 태스크 처리 후 워커 프로세스 재시작 (메모리 누수 방지)
    worker_max_tasks_per_child=200,
    # 작업 수가 아니라 실제 메모리 기준 안전장치(#66): 자식 프로세스 RSS가 기준(KiB)을 넘으면 작업을 마친 뒤 교체
    worker_max_memory_per_child=settings.WORKER_MAX_MEMORY_PER_CHILD_KB,
    # 자식이 강제 종료(OOM)돼도 같은 작업을 다시 넣지 않는다. 다시 넣으면 같은 이미지가 새 자식도 죽이는 연쇄 종료가 난다.
    task_reject_on_worker_lost=False,
    # 로컬/경량 Redis 브로커 호환성 및 불필요한 pidbox 브로드캐스트 오버헤드 제거
    worker_enable_remote_control=False,
    worker_send_task_events=False,
)


@worker_process_init.connect
def preload_paddle_ocr_on_worker_start(**kwargs) -> None:
    """
    [핵심 요구사항 5: 워커 프로세스 시작 시 PaddleOCR 싱글톤 사전 로드]
    매 프레임마다 무거운 OCR 모델을 로딩하지 않도록,
    Celery 워커 프로세스가 부팅될 때 메모리에 1회 로드하여 상주시킵니다.
    """
    from app.vision.ocr_engine import get_ocr_engine

    logger.info("[Celery Worker Init] 워커 프로세스 시작 -> PaddleOCR 싱글톤 사전 로드 시작")
    get_ocr_engine()
    logger.info("[Celery Worker Init] PaddleOCR 싱글톤 준비 완료")

