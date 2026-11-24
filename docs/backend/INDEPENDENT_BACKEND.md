# 팀원 코드 없이 구현한 백엔드 사용 안내

이 문서는 미완성 프론트 참고본에 맞춘 개발용 기능이다. 실제 OCR·추천·외부 결제나 프론트 화면 구현 완료를 의미하지 않는다.

## 적용

기존 DB를 백업하고 소병선 브랜치 변경을 받은 다음 실행한다.

```powershell
py tools/workspace.py backup
py tools/workspace.py up --scope core
py tools/workspace.py check --scope core
```

독립 DB 3개를 유지한다. 각 DB에 최신 마이그레이션을 자동 적용한다. 관리자 가입 및 화면 승인에는 `member_0004`까지 필요하다.
회원·상품·고객센터 중 하나의 마이그레이션이 실패하면 API가 정상 시작되지 않게 했다. Swagger: http://127.0.0.1:8000/docs.

## 관리자 계정

어드민 로그인 화면의 **관리자 가입 신청**으로 계정을 만든다. 신청은 기존 회원 DB의 `app.admin_identities`에 저장되며 승인 후 로그인할 수 있다.
관리자 계정으로 로그인하고 **관리자 가입 승인**에서 신청 내용을 확인한 뒤 역할을 지정해 승인한다. 승인한 사람과 부여한 역할은 감사 로그에 기록한다.

승인할 관리자 계정이 아직 없으면 DB 소유자가 처음 한 번 아래 명령으로 계정을 활성화한다. 운영 중 권한 회수에도 같은 명령을 사용한다.

```powershell
py tools/workspace.py admin --scope core --login-id 본인아이디 --role admin
py tools/workspace.py admin --scope core --login-id 상담담당아이디 --role support
py tools/workspace.py admin --scope core --login-id 상담담당아이디 --revoke
```

`admin`은 회원 목록·제휴·상담과 가입 신청 승인을, `support`는 상담을 관리한다. 이미 부여한 역할 변경과 회수는 DB 소유자가 실행한다.
신규 관리자 계정의 권한을 변경하거나 회수하면 해당 계정의 활성 세션이 종료된다. 기존 일반 회원에 연결된 관리자 계정도 계속 로그인할 수 있다.

## 고객센터·제휴상품

고객센터 화면은 최초 목록이 비어 있으면 POST /v2/support/conversations로 방을 만든 후 메시지를 보낸다.
client_message_id는 메시지별 UUID이며 재시도에는 같은 값을 쓴다. 관리자 답변과 상태 변경은 별도 관리자 경로를 사용한다.

제휴는 기존 offer_id에 연결한다. 서버 services/api/.env의 AFFILIATE_URL_HOSTS에 실제 계약된 목적지 도메인을 추가한다.
기본은 가상 테스트 도메인뿐이다. 사용자가 임의 도메인을 허용 목록에 추가하는 API는 없다.
프론트가 제휴 등록 화면을 만들 때 expected_version을 보존해 보내야 한다.

## 분석 작업자 연결 준비

개발 API는 접수·상태·취소·결과 저장과 내부 작업 할당을 제공한다. 실제 분석 작업자는 아직 없다.
services/api/.env에 ANALYSIS_WORKER_TOKEN을 무작위 32자 이상으로 설정하고 up을 재실행한다. 이 토큰은 프론트에 넣지 않는다.

작업자는 claim → 이미지 읽기 → 실제 OCR/추천 → complete 또는 fail 순서로 호출한다.
실제 OCR/추천 담당자가 보낼 결과 형식은 현재 offer_ids 목록을 출발점으로 함께 확정해야 한다.
배포가 한 PC의 Docker를 벗어나면 비공개 이미지 볼륨을 공유 가능한 저장소로 교체해야 한다.
이 구현은 PostgreSQL 작업 대기열을 사용하며 별도 Redis 큐로 같은 작업을 중복 발행하지 않는다.
현재 비회원 분석은 미구현이다. 프론트의 게스트 분석 버튼은 로그인 유도 또는 향후 익명 권한 계약이 필요하다.

## 데이터 정리와 탈퇴

```powershell
py tools/workspace.py maintenance --scope core
py tools/workspace.py maintenance --scope core --apply
```

첫 명령은 조회만, 두 번째는 이번 배치를 실행한다. 자동 작업도 시간마다 실행된다.
회원 탈퇴는 즉시 로그인 불가·개인 프로필 제거, 다른 DB 기록은 재시도 가능한 삭제 작업으로 처리한다.
결제 대기 건이 있으면 먼저 확정해야 탈퇴할 수 있다. 실제 돈을 환불하는 기능은 아니며 과거 모의 결제 내역은 보존한다.

## 검증 범위

services/api/tests/test_independent_features.py에서 실제 DB 3개를 대상으로 본인/타인/관리자 접근,
중복 메시지·순번·상태 충돌, 제휴 기간/품절 필터, 권한 회수, 작업 중복·취소·만료·재시도,
비공개 파일·업로드 크기 제한, 구독별 결과 제한, 탈퇴 및 DB 간 부분 실패 후 재시도를 검증한다.
기존 상품·회원·구독 검사와 실제 HTTP 성능 검사도 같은 CI에서 실행한다.

API 전체 목록과 요청 형태: [독립 구현 API 계약](../../contracts/independent-backend-v2.md).
이전 구독·데이터 관리: [DB 운영 안내](DB_OPERATIONS.md).

남은 연결: 프론트 실제 화면, OCR·추천·임베딩 모델, 성분/알레르기 판정, 실제 결제사, 비밀번호 재설정용 본인 확인 수단.
