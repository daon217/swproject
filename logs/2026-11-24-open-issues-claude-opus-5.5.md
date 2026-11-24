# [Claude Opus 5.5] 2026-11-24 미해결 / 확인 필요 이슈

발견했지만 아직 고치지 않은 것. 고치면 상태와 커밋을 INDEX.md에 갱신하고 이 항목에 "해결" 섹션을 추가한다.

---

## <a id="16"></a>#16 애드픽 API 무인증 → 할당량 남용 — 미해결
- 문제: `POST /v2/links/convert`가 로그인 없이 임의 URL을 받는다. 누구나 분당 60회 예산을 소진해 실제 사용자의 변환을 막을 수 있다.
- 해결 방안 후보: (A) `offer_id`를 받아 우리 카탈로그의 상품 URL만 변환(권장) / (B) 로그인 회원만 허용 / (C) 둘 다.
- 고려: 비회원도 추천 상품을 보므로 (A)가 사용자 경험을 해치지 않으면서 남용을 막는다.

## <a id="17"></a>#17 프록시 뒤에서 IP별 제한이 전체 제한이 됨 — 미해결
- 문제: `infra/ui/nginx.conf`가 `/backend` → API 전달 시 `X-Forwarded-For`를 붙이지 않고, uvicorn도 `--proxy-headers` 없이 실행. 미리보기 경유 사용자가 모두 같은 IP로 보여 로그인(분당 30)·가입·분석·애드픽(분당 10) 제한을 함께 나눠 쓴다.
- 해결 방안: nginx에 `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`, uvicorn `--proxy-headers --forwarded-allow-ips=<프록시 주소>`. 신뢰하지 않는 주소의 헤더는 무시해야 위조를 막는다.

## <a id="18"></a>#18 분석 워커 동시 4 vs OCR 1 — 미해결
- 문제: NAS 구성에서 워커 `ANALYSIS_WORKER_CONCURRENCY` 기본 4, Vision 워커 `--concurrency=1`. 대기열 뒤쪽 작업이 워커의 Vision 대기 90초를 넘겨 `OCR_FAILED`가 될 수 있다.
- 해결 방안: 워커 동시성을 Vision 처리 능력에 맞추거나, Vision 대기 시간을 대기열 길이에 비례해 늘리거나, Vision 큐 길이를 보고 claim을 멈춘다.

## <a id="19"></a>#19 식품/상품 키워드 판별 범위 — 미해결
- 문제: `NON_FOOD`의 '스킨', '쿠션' 등이 넓어서 식품명에 섞이면 상품으로 판정(예: 브랜드명에 '스킨'). `FOOD_TITLE`의 '사과', '쌀' 등도 비식품 상품명에 섞일 수 있다.
- 현재 완화: #04로 알레르기 사용자에게 '검사 안 됨' 경고.
- 해결 방안: 카탈로그 매칭 결과 우선, 단어 경계 매칭, 실제 오판 사례 수집 후 테스트로 고정.

## <a id="20"></a>#20 김호진 웹의 관리자 토큰 위임 fallback — 미해결 (보안, apps/web)
- 문제: 관리자 API가 404일 때 웹이 `local-demo.cjs`의 `/__admin-approval`로 우회. 관리자 로그인 시 **관리자 본인 토큰**을 파일에 저장하고, 인증 없는 `/status?login_id=`로 승인된 사용자에게 그 토큰을 넘긴다. support 역할 승인자도 관리자 권한을 얻는다. 승인 실패도 `.catch(() => ({status:'approved'}))`로 성공처럼 표시. 상품 삭제 우회는 DB가 아닌 로컬에서만 숨김.
- 해결 방안: #08로 백엔드가 생겼으므로 웹 병합 시 404 우회 코드를 제거하거나 데모 모드(`?demo=1`)에서만 동작하게 제한. 토큰 위임 경로는 완전히 삭제 권장.

## <a id="21"></a>#21 Vision 캐시 키가 이미지 앞 4KB만 비교 — 미해결 (kkulpick_vision)
- 문제: `tasks.py`의 init↔frame 중복 OCR 캐시가 base64 앞 4096자의 md5로 같은 이미지를 판단. 같은 세션 안에서만 쓰여 현재 영향은 작지만, 상단이 같은 다른 캡처면 잘못된 성분을 재사용할 수 있다.
- 해결 방안: 전체 바이트 해시(sha256) 사용.

## <a id="22"></a>#22 추천 서비스 DB 연결 풀 없음 — 미해결
- 문제: `embedding_config.connect()`가 요청마다 psycopg 연결을 새로 연다.
- 해결 방안: `psycopg_pool.ConnectionPool` 도입(의존성 추가 필요).

## <a id="23"></a>#23 실제 수집 원본 300건 커밋 — 확인 필요
- `services/collector/handoffs/real_db_test_300_20261115/observations_v2_REAL_300.json`(약 220KB). 저장소가 공개라면 수집 데이터 저장·재배포 범위 확인 필요.

## 로컬 환경 메모 (이슈 아님)
- `apps/mobile/.env.example`이 로컬에서 `EXPO_PUBLIC_API_BASE_URL=http://10.20.66.31:8000`으로 수정되어 있어 `tools/test_workspace.py` 1개가 실패한다. 커밋하지 않은 로컬 변경.
