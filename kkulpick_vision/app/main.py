"""
[main.py]
꿀픽(KkulPick) 실시간 쇼핑몰 상세페이지 성분표 추출 비전 AI 파이프라인의 FastAPI 서버 엔드포인트 모듈입니다.
프론트엔드로부터 들어오는 초기 세션 요청과 1초 간격 스트리밍 프레임 요청을
Non-blocking I/O 방식으로 수신하여 즉시 Celery 분산 큐로 밀어 넣습니다.
(JSON Base64 요청과 Multipart/form-data UploadFile 요청을 모두 지원합니다.)
"""

import base64
import json
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.schemas import (
    AsyncDispatchResponse,
    VisionAnalysisResultResponse,
)
from app.tasks import (
    extract_metadata_fallback_task,
    get_redis_client,
    get_session_key,
    initialize_session_in_redis,
    process_frame_task,
)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="실시간 쇼핑몰 상세페이지 스트리밍 성분표 추출 비전 AI 파이프라인 API",
    version="1.0.0",
)

# 프론트엔드(크롬 익스텐션 / 웹앱) 연동을 위한 CORS 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # 인증은 쿠키가 아니라 Authorization 헤더. "*"와 credentials를 같이 켜면 모든 사이트에 자격 증명 요청을 허용한다.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _extract_payload_from_request(request: Request) -> dict:
    """
    클라이언트가 `application/json`(Base64 이미지)으로 보내거나
    `multipart/form-data`(UploadFile 또는 텍스트 필드)로 보내는 경우를 모두 비동기로 파싱합니다.
    """
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        return await request.json()

    if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        data = {}
        for key, value in form.items():
            if isinstance(value, UploadFile) or hasattr(value, "read"):
                file_bytes = await value.read()
                data[key] = base64.b64encode(file_bytes).decode("utf-8") if file_bytes else None
            else:
                data[key] = value
        return data

    # 기본 JSON 파싱 시도
    try:
        return await request.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"지원하지 않는 요청 포맷입니다 (JSON 또는 multipart/form-data 필요): {exc}",
        )


# ==============================================================================
# [Phase 1] 투트랙 비동기 수신 및 메타데이터 Fallback 엔드포인트
# ==============================================================================
@app.post(
    f"{settings.API_V1_STR}/init",
    response_model=AsyncDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Phase 1] 세션 초기화 및 상품명 Vision Fallback 트리거",
)
async def init_vision_session(request: Request) -> AsyncDispatchResponse:
    """
    **[Phase 1: 투트랙 비동기 수신 및 메타데이터 Fallback]**
    - 프론트엔드로부터 `session_id`, `product_name`(Optional), `price`(Optional),
      `first_frame_image`(Base64 문자열 또는 UploadFile)를 비동기로 수신합니다.
    - Redis에 해당 `session_id`의 상태 해시(`status: "processing"`, `frame_count: 0`, `product_name`, `price`)를 생성합니다.
    - **[Fallback 로직]**: 만약 `product_name`이 비어 있거나 null이면, Celery 워커가 즉시 `first_frame_image`를
      PaddleOCR로 스캔하여 가장 면적(Width × Height)이 큰 텍스트를 `product_name`으로 추출하고
      `source_of_meta: "vision_fallback"`으로 기록합니다 (정상 수신 시 `"html_crawler"`).
    """
    payload = await _extract_payload_from_request(request)

    session_id: Optional[str] = payload.get("session_id")
    if not session_id or not str(session_id).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id는 필수 입력값입니다.",
        )

    product_name: Optional[str] = payload.get("product_name")
    raw_price = payload.get("price")
    price: Optional[int] = int(raw_price) if raw_price not in (None, "") else None
    first_frame_image: Optional[str] = payload.get("first_frame_image")

    # 1. Redis에 초기 세션 해시 생성
    initialize_session_in_redis(
        session_id=session_id,
        product_name=product_name,
        price=price,
    )

    queued_task_id: Optional[str] = None

    # 2. [Fallback 판정] product_name이 비어 있거나 null이면 0초 차 최상단 화면 OCR 태스크 즉시 큐잉
    if not product_name or not str(product_name).strip():
        if first_frame_image:
            task = extract_metadata_fallback_task.delay(session_id, first_frame_image)
            queued_task_id = task.id
            msg = "세션이 생성되었으며, 상품명 미수신으로 Vision Fallback 추출 태스크가 시작되었습니다."
        else:
            msg = "세션이 생성되었습니다. (상품명 및 초기 프레임 이미지가 제공되지 않음)"
    else:
        msg = "세션이 정상적으로 초기화되었습니다 (source_of_meta: html_crawler)."

    return AsyncDispatchResponse(
        session_id=session_id,
        status="processing",
        queued_task_id=queued_task_id,
        message=msg,
    )


# ==============================================================================
# [Phase 2] 실시간 스트리밍 프레임 비동기 수신 엔드포인트 (HTTP 202)
# ==============================================================================
@app.post(
    f"{settings.API_V1_STR}/frame",
    response_model=AsyncDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="[Phase 2] 1초 간격 스크롤 프레임 비동기 큐 적재",
)
async def receive_streaming_frame(request: Request) -> AsyncDispatchResponse:
    """
    **[Phase 2: 실시간 스트리밍 프레임 분석 (Interval Capture)]**
    - 스크롤 중 1초 간격으로 들어오는 `session_id`, `frame_index`, `is_last_frame`(bool), `image`를 수신합니다.
    - 이미 종료된 세션(`success` 또는 `analysis_unavailable`)인 경우 큐에 넣지 않고 즉시 응답하여 브로커 부하를 아낍니다.
    - 진행 중인 세션이면 즉시 Celery 큐로 밀어 넣고 **HTTP 202 Accepted**를 반환합니다.
    """
    payload = await _extract_payload_from_request(request)

    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="session_id는 필수 입력값입니다.",
        )

    try:
        frame_index = int(payload.get("frame_index", 0))
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="frame_index는 정수여야 합니다.",
        )

    raw_last = payload.get("is_last_frame", False)
    if isinstance(raw_last, str):
        is_last_frame = raw_last.lower() in ("true", "1", "yes")
    else:
        is_last_frame = bool(raw_last)

    image_b64: Optional[str] = payload.get("image")
    if not image_b64 and not is_last_frame:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="image 데이터가 누락되었습니다.",
        )

    # API 수신단에서도 Redis 상태를 가볍게 확인하여 이미 Early Exit된 세션이면 큐 적재 생략
    r = get_redis_client()
    key = get_session_key(session_id)
    session_state = r.hgetall(key)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"초기화되지 않거나 만료된 session_id입니다: {session_id}",
        )

    if session_state.get("status") != "processing" or session_state.get("early_exit_flag") == "1":
        return AsyncDispatchResponse(
            session_id=session_id,
            status=session_state.get("status", "success"),
            queued_task_id=None,
            message="이미 분석이 종료된 세션이므로 추가 프레임 큐잉을 생략합니다.",
        )

    # Non-blocking으로 Celery 큐에 프레임 분석 태스크 적재 후 즉시 HTTP 202 반환
    task = process_frame_task.delay(
        session_id=session_id,
        frame_index=frame_index,
        is_last_frame=is_last_frame,
        image_b64=image_b64 or "",
    )

    return AsyncDispatchResponse(
        session_id=session_id,
        status="processing",
        queued_task_id=task.id,
        message=f"프레임 #{frame_index} 분석 작업이 큐에 등록되었습니다.",
    )


# ==============================================================================
# [Phase 3] 세션 상태 및 최종 추출 성분표 폴링 엔드포인트
# ==============================================================================
@app.get(
    f"{settings.API_V1_STR}/status/{{session_id}}",
    response_model=VisionAnalysisResultResponse,
    summary="[Phase 3] 성분표 추출 상태 및 최종 결과 JSON 조회",
)
async def get_vision_session_status(session_id: str) -> VisionAnalysisResultResponse:
    """
    **[Phase 3: 조기 종료(Early Exit) 및 최종 JSON 반환]**
    프론트엔드가 폴링(`GET /api/v1/vision/status/{session_id}`)하여
    실시간 성분표 분석 상태(`processing` | `success` | `analysis_unavailable`)와
    최종 정제된 성분 리스트(`ingredients`)를 조회합니다.
    """
    r = get_redis_client()
    key = get_session_key(session_id)
    session_state = r.hgetall(key)

    if not session_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"세션을 찾을 수 없습니다: {session_id}",
        )

    raw_price = session_state.get("price", "")
    price_val: Optional[int] = int(raw_price) if raw_price.isdigit() else None

    raw_product_name = session_state.get("product_name", "")
    product_name_val: Optional[str] = raw_product_name if raw_product_name else None

    try:
        ingredients_list = json.loads(session_state.get("ingredients", "[]"))
    except Exception:
        ingredients_list = []

    source_of_meta = session_state.get("source_of_meta", "html_crawler")
    if source_of_meta not in ("html_crawler", "vision_fallback"):
        source_of_meta = "html_crawler"

    current_status = session_state.get("status", "processing")
    if current_status not in ("processing", "success", "analysis_unavailable"):
        current_status = "processing"

    return VisionAnalysisResultResponse(
        session_id=session_id,
        status=current_status,
        product_name=product_name_val,
        price=price_val,
        source_of_meta=source_of_meta,
        ingredients=ingredients_list,
        message=session_state.get("message", ""),
    )


# Integrated deployments use a private service credential; never ship it to clients.
import os
import secrets
from starlette.responses import JSONResponse
@app.middleware('http')
async def service_auth(request,call_next):
    token=os.getenv('VISION_SERVICE_TOKEN','')
    if request.url.path.startswith('/api/'):
        if not token:
            # 토큰이 비면 열지 않고 닫는다. 혼자 로컬에서 띄울 때만 VISION_DEV_NO_AUTH=1로 끈다.
            if os.getenv('VISION_DEV_NO_AUTH') == '1':
                return await call_next(request)
            return JSONResponse({'detail':'SERVICE_TOKEN_NOT_CONFIGURED'},status_code=503)
        given=request.headers.get('authorization','')
        if not secrets.compare_digest(given.encode(),('Bearer '+token).encode()):
            return JSONResponse({'detail':'SERVICE_AUTH_REQUIRED'},status_code=401)
    return await call_next(request)
