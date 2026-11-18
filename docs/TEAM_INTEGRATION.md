# 팀 통합 개발 실행

각 PC의 Docker Desktop Linux 엔진에서 실행합니다. 클라우드나 개인 PC 상시 실행은 필요하지 않습니다. PC별 DB 데이터는 서로 독립적입니다.

```powershell
git switch main
git pull --ff-only origin main
py tools/workspace.py init
py tools/workspace.py up --scope integrated
py tools/workspace.py seed
py tools/workspace.py check --scope integrated
```

처음에는 Vision CPU 이미지 빌드와 한국어 OCR 모델 다운로드 때문에 시간이 필요합니다. 모델은 Docker 볼륨에 보관됩니다. OCR 워커는 CPU 2스레드·동시 작업 1개로 시작합니다. GPU, 유료 AI 키는 필요하지 않습니다.

| 역할 | 주소 / 동작 |
|---|---|
| 백엔드 API | http://localhost:8000/docs |
| 비전 API | http://localhost:8100/docs (실제 분석 경로는 내부 서비스 인증 필요) |
| 확장 미리보기 | http://localhost:5174/preview.html |
| 모바일 웹 미리보기 | http://localhost:8081 |
| 김호진 관리자 웹 | http://localhost:3000 |
| 기존 개발 상태 대시보드 | http://localhost:3001 |
| PostgreSQL | localhost:5433, 회원·상품·고객지원 독립 DB 3개 |

## 연결 흐름

프론트가 백엔드 `/analyses`에 사진/페이지 URL과 상품·식품 구분을 보냅니다. 분석 워커는 인증된 작업 임대를 받아 이미지를 비전 8100에 전달합니다. 비전은 Redis와 PaddleOCR CPU 워커로 상품명/성분을 추출합니다. 추천 서비스는 DB 카탈로그와 서버가 읽은 회원 설정을 이용해 후보를 고르고, 백엔드는 판매 상태·작업 임대를 재검사한 뒤 결과를 저장합니다. 프론트는 상태를 폴링해 보여줍니다.

사이트 URL을 무작정 서버에서 열지 않습니다. DB에 URL이 정확하게 일치하는 상품은 수집된 상품명으로 추천할 수 있습니다. URL 쿼리가 다른 상품을 같은 상품으로 취급하지 않습니다. 매칭도 이미지도 없으면 분석 실패로 안내합니다.

추천 기본값은 무료 `HashEmbedder` + `RuleRanker`입니다. 이는 연결 검증용 기준이며 의미 검색 정확도를 보장하는 학습 모델이 아닙니다. 팀원의 Claude/로컬 모델 코드는 유지되지만 키·모델 설치 없이 자동 유료 호출을 하지 않습니다. 도메인당 최초 1,000개 판매 중 상품을 후보 풀로 사용합니다. 더 큰 카탈로그는 PostgreSQL 벡터 어댑터로 전환한 뒤 검색 품질·응답 시간을 따로 검증해야 합니다.

식품 성분이 없는 후보는 알레르기 사용자의 안전 후보로 취급하지 않습니다. OCR 성분과 경고는 참고 자료이며 상품 표시 확인이 필요합니다. 현재 지원 밖의 비식품 알레르기는 자동 검증 미지원으로 알립니다. 수집 상품의 상세 성분은 별도 수집·저장 계약이 추가되어야 합니다.

## UI와 관리자

- 확장 사이드바가 닫혔을 때 플로팅을 표시하고, 클릭해 사이드바가 열리면 플로팅을 숨깁니다. 미리보기의 사이드바 닫기/열기로도 확인할 수 있습니다.
- 비회원은 최신 수집 상품·식품을 기본 추천으로 볼 수 있습니다. 개인 맞춤 분석과 개인 기록은 로그인 후 이용합니다.
- 최근 방문 사이트 UI는 제거했으며, 사용자별 저장 바로가기는 유지했습니다.
- 관리자 회원 목록, 제휴상품 저장/종료, 상담 답변/완료, 상담 설정, 수집 현황은 실제 API·DB를 사용합니다. 회원은 최근 100명, 제휴/상담 목록은 최대 1,000건을 보여줍니다.
- 결제는 기존 개발용 mock 모드입니다. 통계의 모의 결제 합계를 실제 매출로 표시하지 않습니다.
- 상담 설정은 DB에 보관하지만 고객 화면의 운영시간 자동 안내, 이메일을 통한 비밀번호 초기화 발송은 아직 연결되지 않았습니다.

관리자 웹에서 회원가입한 뒤 저장소 루트에서 역할을 부여합니다.

```powershell
py tools/workspace.py admin --login-id 가입한아이디 --role admin --scope integrated
# 상담 담당자만 부여하려면 --role support
```

관리자 승격 API를 일반 회원에게 공개하지 않습니다. API 인증키는 로컬 `.env`에 자동 생성하며 GitHub에 올리지 않습니다. 제휴 URL은 `services/api/.env`의 `AFFILIATE_URL_HOSTS`에 명시된 HTTPS 호스트만 허용합니다.

## 최준서 수집 코드

`services/collector/domeggook_live/`의 최신 수집·전달 코드를 포함합니다. 수집 결과는 인증된 `/internal/v2/crawl-runs/{run_id}/observations`를 통해 업서트됩니다. 같은 출처·상품 ID·옵션을 기준으로 최신 가격/URL/판매 상태만 반영하고 관측 재전송은 중복 반영하지 않습니다.

이미 받은 Observation v2 JSON 배열은 다음 명령으로 반영합니다.

```powershell
py tools/catalog.py --help
```

실제 외부 수집은 도매꾹 API 키, 수집 필드 저장·재사용 범위, MOQ/가격 표시 의미, 수집 담당자의 설정이 필요합니다. 해당 승인 조건을 임의로 해제하지 않았습니다. `domeggook_live/README.md` 및 `backend_delivery.example.json`을 기준으로 로컬 설정을 작성하세요. DB를 직접 수정하지 않고 기존 전달 어댑터의 Collector 토큰을 사용합니다.

## 테스트와 종료

```powershell
py tools/integration_smoke.py
py tools/workspace.py status --scope integrated
py tools/workspace.py logs --scope integrated
py tools/workspace.py stop --scope integrated
```

통합 smoke는 별도 시험 회원/분석을 만들고 회원 탈퇴를 요청합니다. GitHub CI는 실제 PostgreSQL, 관리자 브라우저 CRUD, 추천 연결, 한국어 합성 이미지의 실제 PaddleOCR 추출을 검사합니다. 실제 쇼핑몰별 화면에서의 OCR 품질과 네이티브 Expo/Chrome 확장 호환성은 별도로 확인해야 합니다.

`stop`은 컨테이너를 멈추고 DB 볼륨을 보존합니다. `down -v` 또는 Docker 볼륨 삭제는 데이터를 지우므로 개발 종료 명령으로 사용하지 마세요. 기존 데이터가 있으면 `py tools/workspace.py backup` 후 업데이트하세요.
