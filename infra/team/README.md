# 꿀픽 팀 공용 개발 API (Windows PowerShell)
대표 PC 한 대에서 기존 개발용 catalog를 공유합니다. 별도 클라우드 계정이나 과금 서비스는 만들지 않습니다. GitHub는 코드 공유용이며 상품 데이터는 호스트 PC의 Docker 볼륨에 남습니다. **본인의 기존 가상 상품을 팀에 보여주는 방식**이므로 실제 회원·결제·상담·운영 데이터를 넣지 마세요.

## 집에서 접속하는 팀: Tailscale 사설망 사용
1. 호스트·팀원 모두 Windows에 Tailscale을 설치하여 각자 계정으로 로그인합니다. [설치](https://tailscale.com/download/windows). 호스트 계정/비밀번호를 공유하지 않습니다.
2. 호스트의 Tailscale 관리자 화면에서 **호스트 장치만** 필요한 팀원에게 공유하고, 각 팀원은 초대를 자기 계정으로 수락합니다. [장치 공유 안내](https://tailscale.com/kb/1084/sharing). 이미 학교가 제공하는 팀 VPN이 있다면 Tailscale 없이 아래 up 명령에 학교 VPN 주소를 사용할 수 있습니다. 계정 정책으로 공유가 금지된 경우 관리자 승인이 필요합니다. 사용하는 플랜에서 장치 공유와 팀 인원이 허용되는지 확인하세요. 유료 가입이나 자동 결제 설정은 이 프로젝트에 필요하지 않습니다.
3. 아래 1단계처럼 각자 .pub만 전달하고, 호스트가 enroll한 뒤 **LAN용 up 명령 대신** 저장소 루트에서 `py infra/team/team.py home`을 실행합니다. 호스트 Tailscale IPv4 주소(100.x.x.x)를 자동으로 찾아 SSH 포트 하나만 그 주소에 바인딩합니다. 개인 공유기 관리자 페이지나 포트포워딩 설정은 필요 없습니다.
4. 팀원의 PowerShell에서 `Test-NetConnection 호스트의100.x주소 -Port 2222` 결과가 True인지 확인합니다. 아래 3단계 터널 명령에서 192.168.0.25를 **호스트의 100.x 주소**로 꼭 바꾸세요. 각자 localhost:18000을 열면 같은 호스트 DB를 API를 통해 조회합니다.
5. 연결이 안 되면 양쪽 `tailscale status`, 장치 공유 수락, 호스트가 켜져 있는지, VPN 정책·호스트 방화벽의 TCP 2222 허용 순서로 확인합니다. VPN 정책은 다른 장치/서비스 접근까지 허용할 필요 없습니다. 장치 공유를 해제하거나 SSH 키를 revoke하면 권한을 회수할 수 있습니다.
6. 이 설정은 호스트가 켜져 있을 때만 사용 가능합니다. 학교 서버가 아닌 개인 PC를 공유하는 경우 기존에 해당 VPN 장치에 노출한 다른 서비스와 접근 정책도 확인하세요. 인터넷에서 누구나 보는 공개 URL을 만들지 않습니다.

## 전제
- 호스트(소병선): 기존 Docker 환경에서 init → up → seed 완료. Windows의 사설 IPv4 주소를 사용합니다.
- 팀원: Git이나 Docker 설치 없이 OpenSSH 클라이언트(ssh와 ssh-keygen)와 브라우저만 있어도 조회할 수 있습니다.
- 두 PC 사이에 네트워크 경로가 필요합니다. 같은 LAN, 이미 구성된 팀 전용 VPN, 또는 접근 가능한 학교 개발 서버를 사용하세요. 같은 학교 Wi-Fi도 단말 간 연결을 막을 수 있습니다. 이 설정만으로 각자 집에서 다른 PC의 192.168.x.x에 연결되지는 않습니다. 외부 인터넷 공유기 포트 포워딩은 구성하지 않습니다.
- 호스트에서 추가로 여는 포트는 지정한 사설 IP의 TCP 2222 하나입니다. 8000과 5433은 기존처럼 호스트 localhost에만 바인딩됩니다. SSH는 등록 키와 API 포워딩만 허용하고 셸, 명령 실행, DB 포워딩은 허용하지 않습니다.

## 1. 팀원: 키 한 번 생성
PowerShell에서 아래 두 명령을 실행합니다. 이미 같은 파일이 있다면 덮어쓰지 말고 기존 .pub를 사용합니다.
```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.ssh" | Out-Null
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\kkulpick_team"
```
개인키 암호를 설정할 수 있습니다. 생성된 **kkulpick_team.pub 파일만** 호스트에게 전달합니다. 확장자가 없는 kkulpick_team은 개인키로 본인 PC에만 둡니다.

## 2. 호스트: 등록 후 실행
새 코드를 가져온 뒤 swproject 폴더에서 실행합니다. 각 팀원의 공개키를 Downloads에 junseo.pub 등의 구별되는 이름으로 저장합니다.
```powershell
py infra/team/team.py enroll junseo "$env:USERPROFILE\Downloads\junseo.pub"
ipconfig
```
현재 사용하는 Wi-Fi/이더넷(또는 팀 VPN) 어댑터의 IPv4 주소를 확인합니다. 아래 192.168.0.25를 **호스트의 실제 주소로 교체**합니다.
```powershell
py infra/team/team.py up 192.168.0.25
```
기존 프로젝트의 API와 DB를 재사용하고 SSH 게이트웨이를 시작합니다. 처음 출력되는 **서버 SHA256 지문**, 호스트 IP, 포트 2222를 팀원에게 전달합니다. enroll의 지문은 팀원 키 지문이라 서버 지문과 다릅니다. 서버 지문은 `py infra/team/team.py fingerprint`로 다시 확인할 수 있습니다. 공개키를 추가·교체한 후 up을 다시 실행하면 기존 터널도 종료되므로 팀원은 재접속합니다.

## 3. 팀원: 터널 접속 및 동일 데이터 확인
아래 IP를 전달받은 주소로 교체합니다.
```powershell
ssh -p 2222 -i "$env:USERPROFILE\.ssh\kkulpick_team" -o IdentitiesOnly=yes -o ExitOnForwardFailure=yes -N -L 127.0.0.1:18000:api:8000 tunnel@192.168.0.25
```
첫 연결에서 서버 SHA256 지문이 호스트가 준 값과 일치할 때만 yes를 입력합니다. 접속 후 터미널에 아무 메시지가 없어도 정상이며 **창을 열어 둡니다**. 팀원이 자기 PC의 브라우저에서 아래 주소를 엽니다.
- http://127.0.0.1:18000/health — status: ok
- http://127.0.0.1:18000/v2/offers?selected_domain=product — 대표 PC의 상품 목록
- http://127.0.0.1:18000/docs — API 요청 확인

대표 PC에서 `py services/api/dev.py seed` 후 양쪽 상품 조회의 **offer_id와 11,500원 가격**을 비교하면 실제 같은 DB인지 확인할 수 있습니다. 개발 샘플은 신선도가 24시간을 넘으면 목록에 안 보일 수 있습니다. 포트 18000이 사용 중이면 팀원의 -L에서 첫 포트만 18001 등으로 바꾸고 브라우저 URL도 맞추세요. 웹 개발자는 API 기본 주소를 이 터널 주소로 잡습니다. 현재 허용 웹 origin은 기본 http://localhost:3000입니다. 다른 origin은 대표 PC의 services/api/.env에서 DEV_ORIGINS에 정확히 기재하고 up으로 재적용합니다.

## 수집기 쓰기·종료
조회에는 수집 토큰이 필요 없습니다. 수집 담당 서버만 기존 내부 적재 API에 호스트의 COLLECTOR_TOKEN을 Bearer로 사용합니다. 토큰은 개별 비공개 경로로 전달하고 웹/확장 코드나 GitHub에는 넣지 마세요. 실제 판매처 URL은 호스트에서 CATALOG_URL_HOSTS에 허용해야 합니다.
- 팀원 연결 종료: 터널 창에서 Ctrl+C.
- 호스트 공유만 중단: `py infra/team/team.py stop` (API·DB·볼륨 유지).
- 키 회수: `py infra/team/team.py revoke junseo`는 게이트웨이를 중단해 기존 연결까지 끊습니다. 나머지 키가 있으면 `py infra/team/team.py up`으로 재개합니다.
- 집/다른 네트워크에서 접속이 안 되면 먼저 팀 전용 네트워크 경로를 마련해야 합니다. 같은 LAN에서 타임아웃이면 팀원 PC에서 `Test-NetConnection 실제호스트IP -Port 2222`로 확인합니다. 호스트 방화벽이 막는 경우 권한 있는 담당자가 팀 네트워크/팀원 IP에 한해 TCP 2222만 허용합니다. DB 포트나 전체 방화벽을 열지 마세요.
- 호스트가 절전·종료하면 팀 접속도 종료됩니다. 이 구성은 상시 운영 서버나 백업을 제공하지 않습니다. 서버 키는 별도 named volume에 저장합니다. 지문이 갑자기 달라지면 접속 전에 호스트와 확인하세요.
