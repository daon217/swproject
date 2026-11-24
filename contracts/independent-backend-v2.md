# 고객센터·제휴·관리자·탈퇴·분석 작업 임시 API

회원 세션 또는 관리자 세션과 `{data,request_id}` / `{error:{code,message,retryable},request_id}` 형태를 사용한다.
서지웅 프론트 참고본의 경로를 가능한 유지했지만 프론트는 미완성이며 확정 계약이 아니다. 다른 팀원 브랜치는 수정하지 않는다.
실제 OCR·추천·임베딩·외부 결제 호출 없이 작업 상태와 DB 연결을 먼저 구현했다.

## 관리자

관리자 화면에서 신청한 신규 계정은 회원 DB의 `app.admin_identities`에 승인 대기로 생성한다. 일반 회원 정보는 `app.members`에 저장한다.
활성 `admin` 계정은 관리자 화면에서 대기 중인 신청에 `admin` 또는 `support` 역할을 부여한다. 승인한 계정과 역할을 감사 로그에 기록한다. 최초 관리자 설정과 기존 권한 변경·회수는 DB 소유자용 CLI가 담당한다. 기존 회원 기반 관리자 계정도 관리자 로그인과 화면 승인을 지원한다.
신규 관리자 계정의 세션은 `app.admin_sessions`에 저장한다. 승인 전 로그인은 `403 ADMIN_APPROVAL_REQUIRED`, 이미 사용 중인 아이디는 가입 시 `409 LOGIN_ID_TAKEN`이다. 권한 변경 및 취소는 해당 신규 계정의 기존 세션을 무효화한다.

| 경로 | 역할 / 설명 |
|---|---|
| POST `/v2/admin/auth/signup` | 신청. `{login_id,password,password_confirmation,consent_version,consent_accepted:true}` → `201 {data:{user_id,status:"pending_approval"},request_id}` |
| POST `/v2/admin/auth/login` | 승인된 관리자 또는 상담 담당자 로그인. `{login_id,password}` → `{data:{token,expires_in},request_id}` |
| POST `/v2/admin/auth/logout` | 관리자 로그인 세션 종료. Bearer 토큰 → 204 |
| GET `/v2/admin/auth/requests` | admin, 승인 대기 목록. 신청 시각 오름차순, 최대 100건 |
| POST `/v2/admin/auth/requests/{user_id}/approve` | admin, `{role:"admin"}` 또는 `{role:"support"}`로 대기 신청 승인. 이미 처리된 신청은 409 |
| POST `/v2/admin/catalog/offers/delete` | admin, `{offer_ids:[UUID]}`로 최대 50개 카탈로그 판매 정보를 삭제. `deleted_offer_ids`, `protected_offer_ids`, `missing_offer_ids` 반환 |
| GET `/v2/admin/me` | admin/support, 본인 역할 |
| GET `/v2/admin/members?limit=20` | admin, 활성 회원 ID·로그인 ID·가입 시각만 최대 100명 |
| GET `/v2/admin/support/conversations` | admin/support, 상담방 목록. limit, after(UUID) |
| GET/POST `/v2/admin/support/conversations/{id}/messages` | admin/support, 메시지 읽기/답변 |
| PATCH `/v2/admin/support/conversations/{id}` | admin/support, `{status,expected_version}` |
| GET `/v2/admin/affiliate-offers` | admin, 제휴 정보·버전. limit, after(UUID) |
| PUT `/v2/admin/affiliate-offers/{offer_id}` | admin, 제휴 정보 생성/수정 |
| DELETE `/v2/admin/affiliate-offers/{offer_id}?expected_version=N` | admin, 제휴 비활성화 |

지원 역할은 상담만 관리하고 회원 목록이나 제휴 편집은 할 수 없다. 탈퇴 회원은 관리자 역할 기록이 있어도 인증되지 않는다.
전체 회원 검색·정지·복구·운영 대시보드는 이번 범위에 포함되지 않는다. 관리자 페이지 화면은 별도 연결해야 한다.

## 고객센터

독립 support DB에 conversations/messages를 저장하고 owner_id는 회원 UUID 논리 참조다. DB 간 FK는 생성하지 않는다.
실제 요청 시 회원 DB의 세션과 탈퇴 여부를 검사한다. 활성 상담방은 회원당 1개다.

- POST `/v2/support/conversations`: 활성 방 생성 또는 기존 방 반환.
- GET `/v2/support/conversations?limit=1`: 활성 방 우선, 이후 최근 방. 최초에는 빈 목록이므로 프론트에서 POST를 호출해야 한다.
- GET `/v2/support/conversations/{id}/messages?limit=50`: 최근 50개를 sequence_no 오름차순으로 반환.
- `after_sequence=N`을 주면 N 이후 메시지를 오름차순으로 반환(최대 100개).
- POST 메시지 입력 `{body,client_message_id(UUID)}`. 공백만 있는 본문 거부, 최대 10000자.
- 동일 방/동일 client_message_id/동일 작성자·본문은 같은 메시지 반환. 내용이 다르면 409.
- 동시 전송은 상담방 행 잠금으로 순번을 부여한다. 회원 전송 시 pending_agent, 답변 시 pending_customer.
- resolved/closed에는 새 메시지를 받지 않는다. closed는 다시 열지 않는다. 새 상담방을 생성할 수 있다.
- 관리자 상태 변경은 expected_version 필수. 버전 충돌 409. 타인의 상담은 404.
- 실시간 WebSocket, 이메일/푸시, 자동 상담 답변은 구현하지 않았다. 프론트는 필요 시 폴링할 수 있다.

## 제휴상품

상품 복사본을 만들지 않고 affiliate_offers.offer_id로 기존 판매 상품에 연결한다.
입력은 partner_name, affiliate_url(HTTPS), starts_at(시간대 포함), ends_at(선택), enabled, expected_version.
신규 생성은 expected_version=0, 수정은 마지막 반환 버전. 기간 충돌·잘못된 링크는 422, 버전 충돌은 409.
AFFILIATE_URL_HOSTS에 서버가 명시한 도메인만 허용한다. 로그인 URL이나 임의 리다이렉트 프록시를 만들지 않는다.

GET `/v2/recommendations/featured?limit=10&selected_domain=product`는 현재 기간의 활성 제휴이면서 판매 중인 상품만 반환한다.
OfferCard 형태의 제휴 목록이며 AI가 산출한 추천 순위가 아니다. affiliate=true 표시가 포함된다.
제휴상품 표시·비활성화는 가능하지만 클릭 추적, 수수료 정산, 제휴사 API는 미연결이다.

## 회원 탈퇴

POST `/v2/me/withdrawal`, 입력 `{current_password}`. 현재 비밀번호 검증, 결과 미확인 결제는 409 PAYMENT_PENDING.
성공 시 202 `{request_id,state:pending}`. 한 회원 DB 트랜잭션에서 아래를 처리한다.

1. 로그인 ID를 무작위 탈퇴 식별자로 변경하고 비밀번호·생년월일·성별·선호 정보를 제거한다.
2. 모든 세션을 폐기하고 권한을 종료한다. 실제 환불을 발생시키지 않는다.
3. account_deletions에 다른 DB 삭제 요청을 저장한다.

정리 작업은 support 상담과 catalog 분석 기록·이미지를 지운다. 일부 DB 장애 시 pending으로 남아 재시도된다.
회원 UUID와 청구·결제·구독 및 감사 기록은 자동 삭제하지 않는다. 개인정보 전체 삭제나 법적 보관 의무 충족을 주장하지 않는다.
로그인 ID 재사용 가능 여부·복구 기간·실제 결제 환불·운영 보관 정책은 출시 전에 확정해야 한다.
비밀번호 재설정은 신원 확인용 이메일/전화/소셜 로그인 방식이 정해지지 않아 구현하지 않았다.

## 분석 접수·작업자 연결

회원 전용이다. 비회원 분석은 정책/익명 토큰 범위 미확정으로 401을 반환한다.

- POST `/analyses`: JSON 또는 multipart/form-data. 필드 page_session_id, page_revision, request_key, selected_domain(선택), page_url(선택).
- 기본은 **캡처 전용**: 확장 프로그램은 page_url(열람 기록)을 보내지 않고 image와 selected_domain만 보낸다. image와 page_url이 모두 없으면 422 `INPUT_REQUIRED`.
- page_url이 없으면 작업자는 카탈로그 URL 매칭 없이 클라이언트 selected_domain과 OCR 상품명으로 추천한다.
- multipart에서만 image 파일 1개 선택 가능. 파일 최대 2 MiB, 요청 전체 최대 3 MiB, 문자열 필드 최대 5개.
- PNG/JPEG/WebP 헤더 확인만 수행하며 실제 이미지 디코딩·픽셀 수 검증은 하지 않는다. 작업자는 디코딩 시 형식·픽셀 수·메모리를 다시 제한해야 한다.
- 파일명은 UUID로 생성, 비공개 디렉터리에 저장. 사용자 파일명은 경로에 사용하지 않는다. page_url을 받은 경우 메타데이터로만 저장하고 서버가 직접 접속하지 않는다.
- 동일 회원/동일 request_key/동일 데이터는 같은 작업을 반환한다. 본문·이미지가 다르면 409.
- 회원당 진행 중 작업 최대 3개. 생성 시 202 queued, 중복 요청은 200. 작업자 미연결 시 완료 결과를 조작하지 않는다.
- GET `/analyses/{id}`: 본인 작업 상태·결과. 다른 회원은 404.
- POST `/analyses/{id}/cancel`: queued/running만 취소, 재취소는 동일 결과. 이미 완료/실패한 작업은 409.
- GET `/v2/me/analyses?limit=20`: 완료된 본인 분석의 최근 첫 상품 카드. 현재 삭제·품절된 상품은 제외.
- POST `/v2/me/data-deletions`, `{scope:history}`: 본인 분석·이미지 삭제. 진행 중 작업도 삭제하여 늦게 도착한 결과를 차단.

ANALYSIS_WORKER_TOKEN(무작위 32자 이상)은 작업자 서버만 사용한다. 회원 토큰·수집 토큰으로 대체 불가.

| 작업자 경로 | 요청 |
|---|---|
| POST `/internal/v2/analyses/claim` | `{worker_id}` → 작업 또는 null, lease_token, lease_until, image_url |
| POST `/{id}/heartbeat` | `{lease_token}` → 작업 점유 시간 연장 |
| GET `/{id}/image` | Authorization + `X-Worker-Lease` 헤더, 비공개 바이너리 |
| POST `/{id}/complete` | `{lease_token,selected_domain,offer_ids:[UUID...]}` |
| POST `/{id}/fail` | `{lease_token,code,retryable}` |

위 축약 경로의 접두사는 `/internal/v2/analyses`이다. 점유 시간 2분, 총 처리 기한 10분, 최대 시도 3회.
만료된 점유는 재배정하며 이전 lease_token으로 결과를 쓸 수 없다. 완료 재전송은 동일 결과만 허용한다.
DB에 존재하고 판매 중이며 선택 도메인이 맞는 상품 ID만 완료 결과로 받는다. 임의 URL이나 HTML 결과를 그대로 저장·노출하지 않는다.
조회 시 DB의 최신 가격/URL/상태를 사용하며 일반 회원은 첫 1개, 활성 구독자는 최대 3개만 반환한다. 잠긴 상품 ID·URL은 응답에서 제외한다.
실제 모델 점수·추천 근거·성분/알레르기 분석은 아직 미연결이다. 식품 ingredient_status=not_found와 '성분 분석 미연결' 안내를 반환하며 안전성을 보증하지 않는다.

## 임시 보관

분석 이미지 1시간 뒤 정리 대상(완료/취소/최종 실패 시 우선 삭제), 완료·실패·취소 작업 30일, resolved/closed 상담 90일.
정리 배치는 1시간 간격이므로 물리 삭제는 만료 시각 직후가 아닐 수 있다. 파일을 공개 정적 경로로 제공하지 않는다.
삭제할 회원 요청은 매 배치 최대 100건. 고객센터/분석은 최대 500건. 실패는 로그 후 다음 배치 재시도.
감사·결제 기록은 보존한다. 운영 환경에서는 실제 보관 정책과 복구·백업 정책을 별도 확정해야 한다.
