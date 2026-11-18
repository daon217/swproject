# Synology NAS(Container Manager)에서 core 실행

DS918+ 같은 **x86_64 Synology + DSM 7.2 Container Manager**에서 DB·API(core 범위)를 상시 실행하는 선택 구성입니다. 기본 개발 방식(각자 PC)은 그대로이며, NAS의 DB는 PC의 DB와 별개로 **빈 상태에서 시작**합니다.

## 구성
- `infra/db/compose.yaml` + `infra/db/api.compose.yaml` + `infra/nas/compose.yaml`
- NAS 전용 override는 API 포트만 **지정한 NAS LAN IP**에 추가로 엽니다. DB(5433)는 NAS 내부 127.0.0.1에만 남습니다.
- 소스 자동 재시작(`local.compose.yaml`의 `--reload`)은 사용하지 않습니다. 코드 갱신 후에는 `up`을 다시 실행합니다.
- DS918+ 기본 메모리 4GB에서 core는 충분합니다. full 범위(Redis·Celery·UI)는 메모리 증설 후 별도로 검토하세요.

## 1. DSM 준비
1. 패키지 센터에서 **Container Manager** 설치. 설치 시 `docker` 공유 폴더가 생깁니다.
2. 제어판 → 터미널 및 SNMP → **SSH 서비스 활성화**. (작업 후 꺼도 됩니다)
3. 제어판 → 네트워크 → 네트워크 인터페이스에서 NAS의 사설 IPv4(예: 192.168.0.10) 확인. 공유기에서 이 주소를 고정(DHCP 예약)하는 것을 권장합니다.

## 2. 코드와 비밀 파일 복사
NAS에 SSH로 접속해 저장소를 받습니다.
```bash
cd /volume1/docker && git clone https://github.com/daon217/swproject.git && cd swproject
```
git이 없으면 PC에서 저장소 폴더를 File Station으로 `/volume1/docker/swproject`에 업로드합니다.

비밀 파일은 **Git이 아닌 File Station 등 비공개 경로로** 복사합니다. PC에서 `py tools/workspace.py init`으로 만든 파일을 같은 위치에 둡니다.
- `infra/db/.env`
- `services/api/.env`

`infra/nas/.env.example`을 `infra/nas/.env`로 복사하고 `NAS_LAN_IP`를 실제 NAS 주소로 바꿉니다.
```bash
cp infra/nas/.env.example infra/nas/.env && vi infra/nas/.env
```

## 3. 실행 (NAS SSH, 저장소 루트)
```bash
sudo sh infra/nas/nas.sh up
```
```bash
sudo sh infra/nas/nas.sh seed
```
첫 빌드는 수 분 걸립니다. 실행 후 Container Manager의 **컨테이너** 화면에서 `kkulpick-nas-*` 컨테이너를 확인·재시작할 수 있습니다. NAS 재부팅 후에도 자동으로 다시 올라옵니다(`restart: unless-stopped`).

| 명령 | 동작 |
| --- | --- |
| `sudo sh infra/nas/nas.sh ps` | 상태 확인 |
| `sudo sh infra/nas/nas.sh logs` | 최근 로그 |
| `sudo sh infra/nas/nas.sh stop` | 중지 (데이터 유지) |
| `sudo sh infra/nas/nas.sh down` | 컨테이너 제거 (DB 볼륨 유지) |

코드 갱신: `git pull` 후 `sudo sh infra/nas/nas.sh up`.

## 4. 팀원 접속
같은 네트워크의 PC에서 `http://NAS주소:8000/health`, `http://NAS주소:8000/docs`를 엽니다.
웹을 다른 PC에서 개발하면 NAS의 `services/api/.env`에 `DEV_ORIGINS=http://localhost:3000`처럼 허용 origin을 정확히 적고 `up`을 다시 실행합니다.

## 지키는 것
- **공유기 포트포워딩으로 인터넷에 공개하지 않습니다.** 집 밖 접속이 필요하면 패키지 센터의 Tailscale을 NAS에 설치하고 `NAS_LAN_IP`에 NAS의 100.x 주소를 넣습니다.
- DSM 방화벽을 쓰는 경우 팀 네트워크에서 TCP 8000만 허용합니다. DB 포트는 열지 않습니다.
- `.env` 파일과 DB 백업은 커밋하지 않습니다. 실제 회원·결제 데이터는 넣지 않습니다.
- NAS는 상시 서버일 뿐 백업이 아닙니다. 필요하면 Hyper Backup으로 `docker` 폴더와 별도 DB 덤프를 보관하세요.
