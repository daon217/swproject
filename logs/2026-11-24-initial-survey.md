# 2026-11-24 현황 조사 (코드 변경 없음)

- 작성: Claude (Opus 5.5), 사용자 요청 "GitHub 진행상황·Actions·브랜치·구조·문제점·성능 파악"
- 기준: `origin/main` 32f08ba, `origin/maintest` 2c65ccd

## 저장소 구조
- `apps/`: extension(Chrome, Vite), mobile(Expo), web(관리자 콘솔, :3000), admin(개발 대시보드)
- `services/api`: FastAPI 백엔드. PostgreSQL DB 3개(member / catalog / support), alembic 마이그레이션 3갈래
- `services/recommendation`: pgvector + MiniLM 임베딩(테스트는 hash), RuleRanker, HTTP 서비스, 임베딩 워커
- `services/dev_runtime/analysis_worker.py`: 분석 작업 임대 → URL 매칭 → Vision OCR → 추천 → 결과 저장
- `kkulpick_vision/`: Celery + Redis + PaddleOCR CPU (:8100)
- `services/collector`: 도매꾹·11번가 등 수집기, Observation v2로 백엔드에 업서트

## 분석 흐름
앱 `/analyses` 접수 → 워커 claim(임대) → `/internal/catalog-context`로 URL 매칭 → Vision init/frame/status 폴링 → 식품 여부 판별 → `/internal/process` 추천 → `/complete` → 앱이 700ms 간격 폴링.

## 브랜치 (조사 시점)
| 브랜치 | 상태 |
| --- | --- |
| maintest (PR #15) | main 위 8커밋, CI 7개 중 2개 실패 (UI 테스트) |
| codex/separate-admin-signup | 관리자 가입·승인·상품 삭제 백엔드, 미병합 |
| part/김호진-web | 관리자 웹, 위 백엔드 API 필요, login/index.js 충돌 |
| part/최준서-collector | 수집기 다수 추가(약 197파일), 충돌 없음 |
| 나머지 | 이미 병합된 오래된 브랜치 |

## GitHub Actions
워크플로 8개. 반복 실패 2개(둘 다 Playwright):
- Team connected runtime: `console.spec.js:23` '답변 추가' 버튼 시간 초과 (main에서도 11/19부터)
- Frontend backend integration: `guest-floating.spec.js:28` '식품' 버튼 (e7f7007에서 제거됨)
- 로그의 `permission denied for schema app`은 DB 권한 격리 검사의 정상 출력

## 성능 참고
- API+DB: 1만 건/동시 16 기준 조회 p95 62ms, 저장 p95 178ms (docs/reviews/BACKEND_EFFICIENCY_2026-11-17.md)
- 병목은 OCR(동시 1, CPU 2스레드)과 폴링(앱 700ms, 워커 0.5s)
