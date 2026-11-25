# 임베딩·성분 매칭·추천

담당: 박정우 · 브랜치: `part/박정우-recommendation`

## DB 없이 추천 테스트하기 (지금 단계)

DB 스키마가 확정되기 전까지 JSON 파일로 저장하는 로컬 구현으로 전체 흐름을 돌립니다.
추천 흐름은 **벡터 후보 → 알레르기 규칙 제외(코드) → 최종 선별·이유(LLM 또는 유사도 순)** 입니다.
LLM 은 알레르기 검사를 통과한 후보만 보고, 후보 밖 상품을 고르면 코드에서 버립니다.

저장소 루트에서 (Python 3.12, `pydantic` 필요):

```bash
python -m services.recommendation.cli validate services/recommendation/samples/products.sample.jsonl
python -m services.recommendation.cli ingest   services/recommendation/samples/products.sample.jsonl
python -m services.recommendation.cli profile  services/recommendation/samples/profiles.sample.json
python -m services.recommendation.cli recommend --user u-milk --query "아이 간식"
```

- 데이터는 `.reco-data/` 에 저장됩니다 (`--data` 로 변경). 폴더째 주고받으면 같은 데이터로 테스트할 수 있습니다.
- `--embedder hash`(기본): 모델 다운로드 없는 테스트용. `--embedder st` 는 sentence-transformers 다국어 모델.
- `--ranker auto`(기본): `ANTHROPIC_API_KEY` 가 있으면 Claude, 없으면 유사도 순. 모델은 `RECO_LLM_MODEL` 로 변경.
- 테스트: `python -m pytest -q services/recommendation/tests`

### 최준서(수집)와 같이 테스트

1. 수집기 출력을 [수집 상품 계약](../../contracts/collected-product.v1.md) 형식의 `.jsonl` 로 저장
2. `validate` 로 형식 확인 → 오류 줄 번호가 나오면 수정
3. `ingest` → `recommend` 로 결과 확인

## 소병선 DB 확정 후 붙이는 방법

| 파일 | 역할 |
| --- | --- |
| `contracts.py` | 고정 데이터 형식 (수집 상품, 프로필, 추천 결과) |
| `ports.py` | 저장소 인터페이스: `CatalogRepository`, `ProfileRepository`, `VectorIndex` |
| `adapters/local.py` | 지금 쓰는 JSON 구현 |
| `adapters/postgres.py` | DB 확정 후 채울 자리 (`vectors.candidates()` 감싸기 등) |
| `tests/contract_suite.py` | 새 어댑터가 통과해야 하는 동작 테스트 |

DB 어댑터를 만들고 `contract_suite` 를 통과하면 `Recommender(catalog, index, embedder, ranker)` 에 넘기는 객체만 바뀌고, 알레르기 규칙·LLM·수집 형식은 그대로입니다.

## 아직 안 된 것

- `devapp.py` 의 HTTP `/internal/process` 연결 (아직 501, `business_ready=false`)
- 알레르기 판정은 키워드 사전 기반입니다 (`allergens.py`). 애매하면 제외하는 쪽이라 '땅콩버터'가 우유로 잡히는 식의 과잉 제외가 있을 수 있습니다.
- Claude 랭커는 실제 API 로 호출해 보지 않았습니다 (가짜 클라이언트로 응답 처리만 테스트).

## 수집 데이터 연결 (2026-11-18)

수집기 데이터가 준비되면 아래 둘 중 하나로 바로 넣습니다. 둘 다 키가 필요 없습니다 (`COLLECTOR_TOKEN`은 수집기가 백엔드에 올릴 때만 씀).

```powershell
# 1) 최준서 Observation v2 파일을 바로 넣기 (JSON 배열 또는 JSONL)
py -m services.recommendation.cli import-observations observations_v2.json --domain food

# 2) 백엔드 DB에 들어간 상품을 읽어오기
#    로컬 워크스페이스: http://127.0.0.1:3000/backend  /  팀 터널: http://127.0.0.1:18000
py -m services.recommendation.cli pull-offers --api-base http://127.0.0.1:3000/backend --domain food
```

- 변환 코드: `adapters/offers_api.py`. variant 가 있으면 `source:listing_id#variant` 를 상품 id 로 씁니다.
- **성분 필드는 아직 없습니다.** 백엔드 `Observation`(services/api/kkulpick/models.py)은 `extra=forbid` 이고 성분 필드가 없어서,
  성분이 들어오려면 백엔드에 필드가 추가돼야 합니다. 필드가 생기면 `_INGREDIENT_KEYS` 의 이름만 맞추면 알레르기 판정에 바로 쓰입니다.
- 성분 정보가 없는 상품은 저장·검색은 되지만 알레르기가 있는 사용자에게는 추천되지 않습니다 (안전 확인 불가).

## catalog DB + pgvector 로 돌리기 (`--store pg`)

상품은 DB(app.offers + catalog_items)에서 읽고, 임베딩은 `food_embeddings` 에 저장·HNSW 검색합니다.
내부에서 백엔드의 `services/api/kkulpick/vectors.py` (`register`/`put`/`candidates`) 를 그대로 씁니다.

```powershell
$env:KKULPICK_CATALOG_OWNER_DSN="host=127.0.0.1 port=5433 dbname=kkulpick_catalog user=kkulpick_catalog_owner password=..."
$env:KKULPICK_CATALOG_DSN="host=127.0.0.1 port=5433 dbname=kkulpick_catalog user=kkulpick_catalog_app password=..."

# 1) 모델 계약 + HNSW 인덱스 등록 (모델마다 한 번, owner 계정). 계약은 못 바꾸니 모델이 바뀌면 새 id.
py -m services.recommendation.cli --embedder st --model-id food-minilm-v1 register-model
# 2) DB 상품 전체 임베딩 → pgvector
py -m services.recommendation.cli --store pg --embedder st --model-id food-minilm-v1 reindex
# 3) 추천 (프로필은 아직 로컬 JSON)
py -m services.recommendation.cli --store pg --embedder st --model-id food-minilm-v1 recommend --user u-none --query "단백질 간식"
```

- 상품 id 는 `source:listing_id#variant_key` (DB 는 variant_key 필수, 없으면 `default` 로 봄).
- item 하나에 판매처가 여럿이면 판매 중인 것 중 가장 싼 offer 로 대표합니다.
- pg 모드에서 `ingest`/`import-observations` 는 막혀 있습니다. 상품은 수집기 → API 경로로만 넣습니다.
- 통합 테스트: `KKULPICK_TEST_PG_DSN`, `KKULPICK_TEST_PG_OWNER_DSN` 설정 후 `tests/test_postgres_adapter.py`.
  pgvector 0.8 이상 필요 (팀 Docker 이미지 0.8.7 은 OK. 0.6 에서는 `hnsw.iterative_scan` 설정 때문에 실패).
