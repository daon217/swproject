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

unified_live의 URL/홈페이지 수집과 역할이 겹친다. 이 모듈은 Observation v2·Outbox를 거치지 않고 DB에 직접 쓴다.
설계 결정 기록은 [DECISIONS.md](DECISIONS.md).
