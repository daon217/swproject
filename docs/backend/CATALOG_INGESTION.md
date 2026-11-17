# 상품 DB · 수집 데이터 도착 시 갱신

소병선 백엔드 / 2026-11-16. 회원 `kkulpick_member`, 상품 `kkulpick_catalog`, 상담 `kkulpick_support`의 독립 DB 3개를 유지한다. 이번 변경은 상품 DB와 수집 API에만 적용한다. 상세 설명은 선택 필드이며 이미지·브랜드·모델·식품별 속성은 실제 상세 데이터 계약을 받은 다음 별도 마이그레이션으로 확장한다.

## Windows에서 실행

저장소 루트 PowerShell에서 실행한다. Docker Desktop은 켜져 있어야 한다. `py` 대신 `python`도 가능하다. 아래 파일 경로는 실제 받은 JSON 위치로 바꾼다. 원본 데이터와 `.env`는 공개 GitHub에 올리지 않는다.

```powershell
py tools/workspace.py init
py tools/catalog.py inspect --file "C:\Users\user\Downloads\observations_v2_REAL_300.json"
py tools/catalog.py configure-hosts --file "C:\Users\user\Downloads\observations_v2_REAL_300.json"
py tools/workspace.py up --scope core
py tools/catalog.py import --file "C:\Users\user\Downloads\observations_v2_REAL_300.json"
```

`configure-hosts`는 파일의 상품 URL 호스트를 로컬 허용 목록에 명시적으로 추가한다. 외부 사이트를 호출하거나 수집 권한을 부여하는 명령이 아니다. 나중에 다른 수집처를 추가할 때도 검토 후 이 명령과 `up`을 실행한다. 기존 수집처 파일은 바로 `import`하면 된다. `up`은 기존 Docker 데이터 볼륨을 유지하고 Alembic 마이그레이션을 적용한다. 중요 데이터가 있는 기존 DB는 먼저 `py tools/workspace.py backup`으로 백업한다.

- API 문서: http://127.0.0.1:8000/docs
- 판매 중 신품: http://127.0.0.1:8000/v2/offers?selected_domain=product
- 판매 중 중고: http://127.0.0.1:8000/v2/offers?selected_domain=product&condition=used
- 품절/종료 포함: http://127.0.0.1:8000/v2/offers?selected_domain=product&condition=all&availability=all&limit=100
- 필터: `source=adafruit`, `currency=USD` 등. 다른 통화 가격끼리 최저가 순위를 계산하지 않는다.
- 100건 초과: `next_cursor`를 다음 요청의 `after`에 전달한다. 전체 300건은 페이지를 넘겨 확인한다.
- 종료: `py tools/workspace.py stop --scope core`. 볼륨을 삭제하는 `down -v`는 사용하지 않는다.

이미 설정된 API_PORT가 8000이 아니면 조회 주소의 포트도 변경한다. `import`는 `.env`의 토큰을 읽어 로컬 API에 한 건씩 전송한다. 300건 전체 파일을 단일 관측 API에 보내지 않는다. 각 요청은 트랜잭션이며 한 행이 거부되어도 다른 행은 적재된다. 결과의 failures를 반드시 확인한다. 통신 실패 시 같은 파일을 다시 실행할 수 있다. 응답을 받기 전에 끊기면 저장 여부가 불확실하므로 키를 바꾸지 않고 재전송한다.

## 동일 상품 판단과 갱신 규칙

동일 매물의 기준은 `(source, source_listing_id, variant_key)`다. 같은 조합에는 UNIQUE 제약이 있다. URL과 이름은 변경 가능하므로 식별 기준으로 쓰지 않는다. 다른 판매처/옵션을 임의로 합치지 않는다.

| 상황 | 처리 |
|---|---|
| 처음 보는 상품 식별 조합 | 상품 기본정보 + 상품/식품 하위 테이블 + 판매정보 생성 |
| 동일 관측 키, 동일 내용 재전송 | 기존 결과 반환(HTTP 200), 상품/변경 이력 중복 생성 안 함 |
| 동일 관측 키, 다른 내용 | HTTP 409 충돌. 원본 보존 |
| 새 관측 키, 더 최신 시각, 값 변경 | 해당 필드 갱신 + 변경 전후 이력 저장 |
| 새 관측 키, 더 최신 시각, 값 동일 | 관측 시각만 갱신. 변경 이력 추가 안 함 |
| 늦게 도착한 과거 데이터 | 해당 필드 최신값 유지. 관측은 기록 |
| 같은 시각인데 값 상충 | 전체 관측 격리(quarantine), 현재 상품값 미변경 |
| 일시적 timeout/blocked/error | 실패 기록. 기존 상품을 판매 종료로 바꾸지 않음 |
| not_found | 기존 상품을 확인 필요(suspect)로 변경. 기본 목록에서 제외 |
| 이후 최신 성공 관측 도착 | 새 판매 상태로 복구 가능 |
| 파일에 기존 상품이 빠짐 | 삭제/종료로 간주하지 않음 |

마지막 도착 순서가 아니라 **observed_at(실제 수집 시각)**으로 비교한다. 타임존을 포함한다. 현재 시각으로 덮어쓰지 않는다. 원본 JSON 그대로 보관하고 그 일부를 임의로 수정해 같은 observation_key로 재전송하지 않는다. 새 수집은 새로운 observation_key, 네트워크 재전송은 기존 키를 사용한다.

**수집기 필수 조건:** URL이 바뀌어도 source_listing_id와 variant_key가 유지되어야 한다. URL 슬러그를 상품 ID로 쓸 때 슬러그까지 바뀌면 이 구조만으로 동일 상품을 확정할 수 없다. 이 경우 판매처의 안정적인 ID를 제공하거나 신뢰할 수 있는 이전/새 ID 매핑 계약을 추가해야 한다. 이름 유사도만으로 자동 병합하지 않는다.

## 시각, 부분 갱신, 조회 정책

- 고정 24시간 만료를 제거했다. 새 데이터가 도착할 때 갱신하며 수집 스케줄러는 이번 범위에 없다.
- 기본 목록은 마지막으로 확인된 판매 가능 신품이다. `last_seen_at`(성공 관측), `last_checked_at`(실패 포함 시도), `price_observed_at`을 화면에 표시해야 한다. 실시간 가격/재고라고 표시하지 않는다.
- 가격+통화는 한 쌍으로 받는다. 배송비 누락은 무료가 아니며 기존 값을 보존한다. 통화가 바뀌고 새 배송비가 없으면 기존 통화의 배송비를 지우고 미확인(NULL)으로 둔다.
- `field_presence`가 실제 제공 필드와 일치해야 한다. 미제공 설명은 기존 설명을 유지한다. `description: null`을 명시하면 설명을 지운다.
- 이름과 설명은 별도 시각을 갖는다. 설명 없는 최신 가격 관측 때문에 나중에 도착한 설명이 누락되지 않는다.
- 새 상품은 신품이 기본값이다. 기존 상품에 condition이 생략되면 기존 신품/중고 값을 유지한다. 명시된 최신 condition은 갱신 가능하다.
- 이름/설명이 바뀔 때만 content_version을 한 번 올린다. 이전 내용의 임베딩은 기존 벡터 조회 규칙에 따라 제외된다. 자동 재임베딩 워커는 아직 구현하지 않았다.

## 테이블 역할

| 테이블 | 저장 내용 |
|---|---|
| catalog_items | 상품명·선택 설명·내용 버전 |
| products / foods | 상품/식품 구분과 이후 상세 확장 |
| offers | 판매처별 현재 가격·통화·배송비·URL·판매 상태·신품/중고·필드별 수집 시각 |
| crawl_runs / crawl_observations | 수집 실행·원본 관측·중복 방지·적용 결과·격리 사유 |
| price_history | 최초 가격 및 가격/통화/배송비가 바뀐 시점의 상태 |
| offer_url_history | 최초 및 변경 URL, 유효 시작/종료 시각 |
| offer_changes | 최초 생성 및 실제 변경 필드의 before_data/after_data |

상태·설명·신품/중고 변경도 offer_changes에 남는다. 동일 값 반복 수신에는 이력을 늘리지 않는다. 재수집 관측 기록은 쌓이므로 장기 보존/정리 정책은 추후 데이터량에 맞춰 결정한다. 자동 삭제는 이번 변경에 포함하지 않는다.

## 수집 API 결과

`POST /internal/v2/crawl-runs/{run_id}/observations`, Bearer 수집 토큰 필요. run_id는 수집처별로 분리한다. 한 실행에 여러 source를 섞으면 409다.

응답의 state는 `applied / recorded / quarantine`, change_kind는 `created / updated / unchanged / stale / failed / not_found / quarantined`다. changed_fields는 실제 변경된 필드 목록이다. 201은 수신 기록 생성이지 모든 필드가 적용됐다는 뜻이 아니다. 재전송 200은 최초 처리 결과를 반환한다.

## 검증 방법

CI `Catalog API integration`은 격리된 PostgreSQL+pgvector에서 기존 DB/벡터 테스트와 새 도착 순서·경쟁 요청·부분 갱신 테스트를 실행한다. PostgreSQL 애플리케이션 권한으로 실제 SQL을 검증한다.

로컬 통합 테스트는 전용 테스트 DB에서만 실행한다. 테스트가 행을 추가하므로 팀 공용 DB나 실제 서비스 DB에 실행하지 않는다. `CATALOG_INTEGRATION=1`, DB 접속 환경변수, `COLLECTOR_TOKEN`을 지정하고 services/api에서 `python -m pytest -q`를 실행한다. 실제 300건 파일의 검증은 빈 테스트 DB에 `CATALOG_REAL_DATA=<파일 절대경로>`를 추가한다. 파일은 공개 저장소에 포함되지 않는다.

## 이번 작업의 실제 검증 결과

- 로컬 격리 PostgreSQL 17.11 + pgvector 0.8.0: API/DB/벡터 회귀 테스트 **26개 통과**. 기존 Docker 설정은 PostgreSQL 17 + pgvector 0.8.7을 유지한다.
- 실제 파일 300건 신규 저장, 같은 파일 300건 재전송 후 상품/가격/URL/변경 이력 중복 없음.
- 실제 HTTP 서버에서도 파일 적재 도구의 생성·갱신·중복 재전송 동작 확인.
- 이전 마이그레이션(0001)에 넣은 상품이 0002 적용 후 가격·식별값을 유지하는 것 확인.
- 원본 300건은 로컬 테스트에만 사용했으며 공개 GitHub에는 업로드하지 않았다.
- 사용자 PC Docker와 팀 공용 서버에는 이 작업에서 직접 접속하거나 데이터를 적재하지 않았다. 각 PC에서 위 명령으로 적용한다.
- 실제 판매처 페이지 호출·가격/재고 진위 검증·상세정보 수집·실제 임베딩 생성은 이번 검증에 포함되지 않는다.
