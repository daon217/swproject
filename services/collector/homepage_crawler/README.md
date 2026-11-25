# homepage_crawler

`platform-urls.md`의 쇼핑몰 홈페이지를 직접 방문해 상품을 Supabase(Postgres)에 저장하는 독립 크롤러.
requests + BeautifulSoup, JSON-LD Product 우선 / OG 보조, robots.txt 사이트맵 활용.

- 분류: (상품·식품) x (일반·중고·직구) 6칸, 가격은 원화 고정(원래 통화·환율 별도 보존)
- 성분·알러지: `food_evidence/allergens.py` 공용 사전 사용. 식품은 성분표를 읽었을 때(read/read_empty)만 저장
- 차단(403/429/CAPTCHA)·robots 거부는 우회하지 않고 `crawl_site_log`에 기록

```powershell
# 저장소 루트에서
python -m services.collector.homepage_crawler.crawler --dry-run --only 올리브영
$env:DATABASE_URL = '<Supabase connection string>'   # schema.sql을 먼저 한 번 실행
python -m services.collector.homepage_crawler.crawler                              # 한 바퀴
python -m services.collector.homepage_crawler.crawler --watch                      # 계속 반복: DB에 100개 쌓을 때마다 10분 쉼, 사이트 오류는 건너뜀, DB가 끊기면 멈춤
python -m pytest services/collector/homepage_crawler
```

## 꿀픽 백엔드로 보내기 (`--backend`)

```powershell
$env:COLLECTOR_BACKEND_BASE_URL = 'http://<백엔드 주소>:8000'      # scheme+host+port만
$env:KKULPICK_BACKEND_TOKEN_FILE = '<백엔드 COLLECTOR_TOKEN이 든 파일>'  # 값은 Git·로그에 남기지 않는다
python -m services.collector.homepage_crawler.crawler --backend --watch
```

- 상품은 Observation v2(`/internal/v2/crawl-runs/{run}/observations`), 브랜드·이미지·식품 성분/알레르기는 확장(`.../extensions`)으로 보낸다. 수집처 이름은 `homepage_<도메인>`.
- 상태는 `unknown`(홈페이지는 새 상품이라고 밝히지 않음), 중고 사이트는 `used`. 중고 식품은 백엔드가 받지 않으므로 보내지 않는다.
- 가격은 **원래 통화**로 보낸다(해외 상품 구분·'해외 상품 포함' 설정이 원화가 아닌 통화로 동작). 가격 범위만 있는 상품은 보내지 않는다.
- 알레르기는 백엔드 코드(peanut, wheat …)로, 견과류·생선처럼 묶음 이름은 코드로 바꾸지 않고 원문(`allergen_notice_raw`)으로 판정하게 둔다(아몬드·연어 등 개별 코드 판정).
- 백엔드에 수집할 쇼핑몰 도메인을 `CATALOG_URL_HOSTS`에 넣어야 한다(없으면 422).
- `DATABASE_URL`도 있으면 Supabase에도 함께 저장한다.

unified_live의 URL/홈페이지 수집과 역할이 겹친다. 이 모듈은 Observation v2·Outbox를 거치지 않고 DB에 직접 쓴다.
설계 결정 기록은 [DECISIONS.md](DECISIONS.md).
