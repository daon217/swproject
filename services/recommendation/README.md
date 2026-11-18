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
