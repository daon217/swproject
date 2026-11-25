# 수집 상품 계약 `kkulpick.collected-product/1` (초안)

- 제공: 수집기(최준서) · 소비: 추천(박정우) · 상태: **초안, DB 확정 전 로컬 테스트용**
- 전송 형식: JSON Lines (`.jsonl`, 한 줄에 상품 1건, UTF-8)
- 검증 코드: `services/recommendation/contracts.py` 의 `CollectedProduct.from_dict`
- 확인 명령: `python -m services.recommendation.cli validate 파일.jsonl`

DB 스키마가 확정되면 이 JSON 을 DB 행으로 바꾸는 어댑터만 추가합니다. 수집기 출력 형식은 그대로 둡니다.
가격·URL 이력 적재는 기존 API 경로(`/internal/v2/crawl-runs/{run_id}/observations`)를 그대로 씁니다. 이 계약은 거기에 없는 **성분·알레르기 정보**를 위한 것입니다.

| 필드 | 필수 | 형식 | 설명 |
| --- | --- | --- | --- |
| `source` | ✅ | `^[a-z][a-z0-9_-]{0,63}$` | 수집처 코드 (API Observation 과 같음) |
| `source_listing_id` | ✅ | 문자열 | 수집처 안의 상품 id. `source:source_listing_id` 가 상품 키 |
| `name` | ✅ | 문자열 | 상품명 |
| `category`, `brand`, `description` | | 문자열 | |
| `price` + `currency` | 함께 | `"12000"` 소수 문자열 + `KRW` | 숫자 대신 문자열 (API 규칙과 같음) |
| `url`, `image_url` | | 문자열 | |
| `ingredients_raw` | 권장 | 문자열 | 성분표 원문. 괄호·% 그대로 둬도 됨 |
| `ingredients` | | 문자열 목록 | 이미 나눈 성분이 있으면 |
| `allergen_notice_raw` | 권장 | 문자열 | "우유, 대두 함유" 같은 알레르기 표시 원문 |
| `cross_contact_raw` | 권장 | 문자열 | "같은 제조시설에서 땅콩 … 제조" 원문 |
| `collected_at` | | ISO-8601 | |
| `schema` | | `kkulpick.collected-product/1` | 생략 가능 |

- 정의되지 않은 필드는 거부합니다 (오타 방지).
- `ingredients_raw` · `ingredients` · `allergen_notice_raw` 가 모두 없으면 저장은 되지만, **알레르기가 있는 사용자에게는 추천되지 않습니다** (안전 확인 불가).

예시: `services/recommendation/samples/products.sample.jsonl`

```json
{"source":"demo","source_listing_id":"cookie-001","name":"버터 쿠키","category":"과자","price":"3500","currency":"KRW","ingredients_raw":"밀가루(밀), 버터(우유), 설탕, 계란","allergen_notice_raw":"밀, 우유, 알류 함유"}
```
