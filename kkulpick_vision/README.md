# 꿀픽(KkulPick) 실시간 쇼핑몰 상세페이지 성분표 추출 비전 AI 파이프라인

이커머스 상세페이지 스크롤 스트리밍 중 실시간으로 **원재료명/성분표**를 검출·정제하고, 안티 크롤링 환경에서는 최상단 화면에서 **상품명 메타데이터를 Vision Fallback으로 복구**하는 3-Phase 비동기 비전 AI 백엔드입니다.

---

## 1. 디렉토리 구조

```text
kkulpick_vision/
├── app/
│   ├── __init__.py (및 init.py)
│   ├── main.py            # FastAPI 엔드포인트 및 비동기 라우터
│   ├── config.py          # Redis URL, 15프레임 타임아웃, ROI/CLAHE 상수 설정
│   ├── schemas.py         # Pydantic 요청/응답 DTO 및 최종 반환 JSON 규격
│   ├── celery_app.py      # Celery 인스턴스 및 워커 시작 시 PaddleOCR 싱글톤 프리로드
│   ├── tasks.py           # Celery 비동기 태스크 (Fallback, ROI 분석, Early Exit, Timeout)
│   └── vision/
│       ├── __init__.py (및 init.py)
│       ├── preprocessor.py # OpenCV 가로 타일링, 앵커 하단 ROI 크롭 & 메모리 해제, CLAHE 전처리
│       └── ocr_engine.py   # PaddleOCR 싱글톤 로드, 최대 면적 상품명 추출, 앵커 탐색, 정규식 정제
├── requirements.txt
└── README.md
```

---

## 2. 3-Phase 파이프라인 아키텍처 요약

1. **[Phase 1] 투트랙 비동기 수신 및 메타데이터 Fallback (`POST /api/v1/vision/init`)**
   - 세션 상태를 Redis Hash로 초기화(`status: "processing"`, `frame_count: 0`).
   - `product_name`이 비어 있거나 `null`이면 Celery 워커가 `first_frame_image`를 스캔하여 바운딩 박스 면적(`Width × Height`)이 가장 큰 텍스트를 `product_name`으로 추출하고 `source_of_meta: "vision_fallback"`으로 기록.
2. **[Phase 2] 실시간 스트리밍 프레임 분석 (`POST /api/v1/vision/frame`)**
   - 1초 간격 프레임을 수신 즉시 Celery 큐에 적재하고 **HTTP 202 Accepted** 반환.
   - OpenCV 가로 타일링 후 1차 스캔에서 `["원재료명", "영양정보", "성분명", "원재료 및 함량"]` 등 앵커 발견 시 해당 Y좌표 하단 `500px`만 ROI 크롭 후 원본 배열은 즉시 메모리 해제(`del` + `gc.collect()`).
   - 크롭된 ROI에 Grayscale → CLAHE(`clipLimit=2.0, tileGridSize=(8,8)`) → 샤프닝/적응형 이진화 적용 후 2차 OCR 및 정규표현식(Regex) 정제를 거쳐 중복 없는 성분 리스트(`List[str]`) 도출.
3. **[Phase 3] 조기 종료(Early Exit) 및 생명주기 제어 (`GET /api/v1/vision/status/{session_id}`)**
   - **시나리오 A (Early Exit)**: 성분 추출 성공 시 즉시 `"success"` 기록 및 `early_exit_flag="1"` 설정으로 대기열의 잔여 프레임 작업 스킵.
   - **시나리오 B (EOF)**: `is_last_frame == True`인데도 성분표를 찾지 못하면 `"analysis_unavailable"` 반환.
   - **시나리오 C (Hard Timeout)**: `frame_count`가 **15프레임**에 도달할 때까지 찾지 못하면 서버 보호를 위해 강제 종료 및 `"analysis_unavailable"` 반환.

---

## 3. 실행 방법

### 1) 의존성 설치
```bash
pip install -r requirements.txt
```

### 2) Redis 서버 실행
```bash
redis-server
```

### 3) Celery 비전 워커 실행 (PaddleOCR 싱글톤 자동 로드)
```bash
# Windows 환경에서는 --pool=solo 권장, Linux/macOS 환경에서는 --concurrency 옵션 사용
celery -A app.celery_app.celery_app worker --loglevel=info --pool=solo
```

### 4) FastAPI 서버 실행
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

