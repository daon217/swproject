"""
[schemas.py]
FastAPI 요청/응답 검증 및 최종 반환 JSON 규격을 정의하는 Pydantic DTO 모듈입니다.
Base64 문자열과 Multipart UploadFile 양쪽 모두 유연하게 수용할 수 있도록 설계되었습니다.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, Field


# ==============================================================================
# 1. 공통 Enum/Literal 타입 정의
# ==============================================================================
SessionStatusType = Literal["processing", "success", "analysis_unavailable"]
SourceOfMetaType = Literal["html_crawler", "vision_fallback"]


# ==============================================================================
# 2. 요청(Request) DTO
# ==============================================================================
class VisionInitRequest(BaseModel):
    """
    [Phase 1] POST /api/v1/vision/init JSON 요청 바디 스키마
    (Multipart/form-data 요청도 main.py에서 동일 필드로 지원합니다)
    """
    session_id: str = Field(..., description="프론트엔드 스트리밍 세션 고유 식별자")
    product_name: Optional[str] = Field(None, description="HTML 크롤러가 수집한 상품명 (미수신 시 Vision Fallback 동작)")
    price: Optional[int] = Field(None, description="상품 가격 (원)")
    first_frame_image: Optional[str] = Field(
        None,
        description="0초 차 최상단 화면 Base64 인코딩 이미지 (Fallback 스캔용)"
    )


class VisionFrameRequest(BaseModel):
    """
    [Phase 2] POST /api/v1/vision/frame JSON 요청 바디 스키마
    스크롤 중 1초 간격으로 캡처된 프레임을 비동기 수신합니다.
    """
    session_id: str = Field(..., description="세션 고유 식별자")
    frame_index: int = Field(..., ge=0, description="프레임 순번 (0부터 시작)")
    is_last_frame: bool = Field(False, description="사용자 스크롤 종료/이탈(EOF) 여부")
    image: Optional[str] = Field(None, description="캡처된 프레임 Base64 문자열")


# ==============================================================================
# 3. 비동기 접수 응답(202 Accepted) DTO
# ==============================================================================
class AsyncDispatchResponse(BaseModel):
    """비동기 큐 적재 직후 프론트엔드에 즉시 반환하는 Non-blocking 응답"""
    session_id: str
    status: str = "processing"
    queued_task_id: Optional[str] = None
    message: str


# ==============================================================================
# 4. 최종 결과 반환 JSON 규격 (Phase 3 상태 조회 및 최종 산출물)
# ==============================================================================
class VisionAnalysisResultResponse(BaseModel):
    """
    [Phase 3] 최종 반환 JSON 규격
    - 성공 시: status="success", ingredients=[...], message="성분표 추출이 완료되었습니다."
    - 분석 불가 시(EOF / 15프레임 Timeout): status="analysis_unavailable", ingredients=[], message="성분표를 찾지 못해 알레르기 분석이 불가합니다."
    """
    session_id: str = Field(..., description="세션 고유 식별자")
    status: SessionStatusType = Field(..., description="세션 처리 상태 (processing | success | analysis_unavailable)")
    product_name: Optional[str] = Field(None, description="상품명 (크롤링 또는 Vision Fallback 추출)")
    price: Optional[int] = Field(None, description="상품 가격")
    source_of_meta: SourceOfMetaType = Field(
        "html_crawler",
        description="메타데이터 출처 (html_crawler | vision_fallback)"
    )
    ingredients: List[str] = Field(default_factory=list, description="정제된 중복 없는 성분 리스트")
    message: str = Field(..., description="상태 안내 메시지")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "session_id": "sess_kkulpick_001",
                    "status": "success",
                    "product_name": "신라면 120g",
                    "price": 1200,
                    "source_of_meta": "html_crawler",
                    "ingredients": ["소맥분", "팜유", "감자전분", "L-글루탐산나트륨"],
                    "message": "성분표 추출이 완료되었습니다."
                },
                {
                    "session_id": "sess_kkulpick_002",
                    "status": "analysis_unavailable",
                    "product_name": "신라면 120g",
                    "price": 1200,
                    "source_of_meta": "vision_fallback",
                    "ingredients": [],
                    "message": "성분표를 찾지 못해 알레르기 분석이 불가합니다."
                }
            ]
        }
    }

