# 로컬 백엔드 운영 도구

팀원 코드·외부 API·유료 서버 없이 백업, 설정 오류, 기동 장애를 점검한다. Python 3.11 이상과 기존 Docker 환경을 사용한다. 명령은 저장소 루트 PowerShell 기준이다.

## 명령어

| 목적 | 명령 |
| --- | --- |
| 실행 전 설정 검증 | `py tools/workspace.py validate` |
| DB/API·컨테이너·백업·디스크 진단 | `py tools/workspace.py monitor` |
| 백업 주기가 됐으면 1회 생성 | `py tools/operations.py backup-auto` |
| 자동 백업 실행기 유지 | `py tools/operations.py backup-auto --loop` |
| 가장 최근 완료 백업의 SHA-256·크기 검사 | `py tools/operations.py verify-backup` |
| 가장 최근 완료 백업을 임시 DB에 복원·검사·정리 | `py tools/operations.py restore-check` |
| 지정 백업 검사 | `py tools/operations.py verify-backup --directory "infra/team/local/backups/백업폴더"` |

진단 성공은 종료 코드 0, 실패는 1이다. 세부 검사는 JSON의 check/ok/code로 확인한다. code는 검사 기준/실패 이유를 나타내며 ok=true인 경우 오류가 아니다. 비밀번호·토큰·원본 Docker 설정·DB 사용자 행은 출력하지 않는다.

## 설정 검증

Docker Compose가 해석한 실제 설정을 검사한다. 여러 env 파일과 PowerShell 환경변수의 우선순위가 반영된다.

- DB·수집 비밀값 길이, DB owner/runtime 분리, API의 DB 실행 계정 비밀번호 일치.
- 모의 결제는 development에서만 허용. 현재 실제 결제 모드는 지원하지 않는다.
- 선택 작업자/모의 결제 토큰은 설정할 경우 충분한 길이와 수집 토큰과의 분리를 검사한다. 설정 여부가 실제 모델/PG 연결을 뜻하지 않는다.
- 명시적 CORS 출처, 판매처·제휴 호스트 형식, 가격 비율의 유효성.
- 로컬 포트 바인딩과 충돌. full은 별도 비밀값과 LLM 비활성 설정도 확인한다.

이 명령은 로컬 모드 기준이다. 선택 VPN 공유 설정이나 공개 운영 배포의 보안 심사를 대신하지 않는다. 저장된 비밀번호를 자동 변경하지 않는다. 기존 DB 볼륨이 있는 상태에서 env 비밀번호만 바꾸면 접속이 끊길 수 있다.

## 자동 백업

기본은 마지막 완료 백업 기준 **24시간 간격**이다. 없으면 즉시 생성하고, 최근 완료 백업이 있으면 재실행해도 중복 생성하지 않는다. `--interval-hours 12`처럼 1~168시간 범위로 바꿀 수 있다.

실행기 중복 실행은 OS 파일 잠금으로 막는다. 비정상 종료 후 잠금은 OS가 해제한다. 실패 시 완료 manifest를 만들지 않으며 loop는 60초 뒤 재시도한다. 정상 완료 후 다음 주기까지 대기하므로 큰 백업을 매분 다시 해시하지 않는다.

각 DB dump를 생성·목록 검사·SHA-256 계산한 뒤 3개가 모두 성공해야 manifest.json을 원자적으로 게시한다. 실패한 .partial 파일은 완료 백업으로 보지 않는다. 손상된 최신 완료 백업이 발견되면 실패를 알리고 과거 백업으로 조용히 대체하지 않는다.

저장 위치는 기존 `infra/team/local/backups`이다. Git에는 올라가지 않으며 기존 백업을 자동 삭제하지 않는다. 불완전 백업과 오래된 백업의 공간은 확인 후 수동 정리한다.

**자동 실행기는 PC·Docker·해당 프로세스가 켜져 있어야 동작한다.** 현재 코드는 OS 자동 시작에 등록하지 않는다. 직접 시작한 터미널을 닫으면 멈춘다. PC를 끈 동안 백업은 불가능하며 다음 실행 시 누락된 주기를 한 번 보충한다. 각 PC의 데이터는 서로 자동 공유되지 않는다.

DB 3개는 각각의 스냅샷이며 DB 간 동일 시점을 보장하지 않는다. 이미지 볼륨·환경변수·인증서·역할 비밀번호·Docker 이미지·Git 코드는 이 DB 백업에 포함되지 않는다. 현재는 암호화/오프사이트 전송이 없으므로 접근 제한된 개인 저장소에 보관하고 중요한 백업은 별도 디스크에 복사한다.

## 복원 검증과 장애 확인

restore-check는 manifest의 파일명·3개 DB 구성·크기·해시를 먼저 검증한다. 현재 서버 안에 무작위 이름의 `kkulpick_verify_*` DB를 생성하고 pg_restore --exit-on-error를 수행한다. 주요 테이블 접근과 마이그레이션 이력을 검사한 뒤 성공/실패와 무관하게 생성한 임시 DB만 제거한다. 이미 존재하는 업무 DB에 덮어쓰는 옵션은 제공하지 않는다.

복원 검사는 백업만큼의 추가 디스크/실행 시간이 필요하다. 본인이 생성한 신뢰할 수 있는 백업에만 사용한다. 장애로 임시 DB 제거에 실패하면 cleanup_required에 생성된 DB 이름만 표시한다. DBA가 확인 후 해당 이름만 정리한다. 모든 업무 데이터의 논리적 정합성을 증명하는 검사는 아니며 실제 사고 복구는 별도 절차다.

monitor는 API가 DB 3개를 읽을 수 있는지, core 컨테이너가 실행 중인지, 최근 백업이 손상되지 않았고 48시간 이내인지, 작업 폴더 디스크에 2GiB 이상 남았는지 확인한다. full은 해당 컨테이너들의 실행/health 상태까지 확인하며 실제 AI 추론 성공을 뜻하지 않는다.

Docker Desktop VM의 가상 디스크 잔여량은 호스트 작업 폴더의 디스크 검사로 보장할 수 없다. Docker Desktop에서도 확인한다. 이메일·메신저 알림, 외부 모니터링 서버, 자동 장애 복구는 아직 없다.

문제 발생 시 `py tools/workspace.py status`와 `py tools/workspace.py logs`를 확인한다. 파일/로그를 팀에 전달할 때 원본 수집 내용·개인정보·인증값을 제거한다.

## 검증

- 도구 단위 검사: `py -m unittest discover -s tools -p "test_*.py" -v`.
- Windows/Linux에서 백업 손상·불완전 manifest·경로 이탈·동시 실행 잠금·재시작 후 중복 방지·실패한 복원 정리 검증.
- Full development workspace CI의 local-core에서 실제 DB 3개 자동 백업·해시 검사·임시 복원·기존 데이터 보존·기동 중단 감지·재기동 정상화를 검증한다.
- 원격 CI 실행 결과는 [PR #3](https://github.com/daon217/swproject/pull/3)에 기록한다. 실제 팀원 PC의 OS 자동 시작/장시간 운영 검증은 별도다.
