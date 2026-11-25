"""platform-urls.md의 쇼핑몰을 직접 방문해 상품을 Supabase(Postgres)에 저장.

사용: python -m services.collector.homepage_crawler.crawler [--dry-run] [--only 올리브영,교보문고] [--max-pages 12]
DB:   환경변수 DATABASE_URL (Supabase > Settings > Database > Connection string)
shortcut: requests만 사용, JS 렌더링 사이트는 no_products로 기록, 필요하면 Playwright로 교체.
"""
import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from services.collector.food_evidence.allergens import extract_allergen_info
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; KkulpickStudentCrawler/0.1)"
SKIP = re.compile(r"login|member|cart|basket|order|checkout|pay|signin|join|mypage|/api/|logout", re.I)
PRODUCT_HINT = re.compile(r"product|goods|item|/p/|/pd/|prdno|goodsno|itemno|/products?/|/vp/|/pd/|goodsdetail|productdetail", re.I)
CAPTCHA = re.compile(r"captcha|are you a robot|access denied|비정상적인 접근", re.I)


def load_sites(md="platform-urls.md"):
    """표의 '| 이름 | 도메인 |' 행을 읽는다."""
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([\w.-]+\.[\w.-]+)\s*\|\s*$", Path(__file__).with_name(md).read_text(encoding="utf-8"), re.M)
    return [(n, "https://" + d) for n, d in rows if n not in ("플랫폼",)]


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_product(html, url):
    """JSON-LD Product 우선, 없으면 OG. 상품이 아니면 None."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if not isinstance(d, dict):
                continue
            stack += d.get("@graph", []) if isinstance(d.get("@graph"), list) else []
            t = d.get("@type")
            if "Product" in (t if isinstance(t, list) else [t]):
                return _from_jsonld(d, url)
    og = {m.get("property"): m.get("content") for m in soup.find_all("meta") if m.get("property")}
    price = _num(og.get("product:price:amount") or og.get("og:price:amount"))
    if og.get("og:type", "").startswith("product") or price is not None:
        return dict(name=og.get("og:title"), price=price, price_low=None, price_high=None,
                    currency=og.get("product:price:currency") or og.get("og:price:currency"),
                    brand=None, image=og.get("og:image"), availability=None, source="og", category=og.get("product:category") or "")
    return None


def _from_jsonld(d, url):
    offers = d.get("offers")
    offers = offers[0] if isinstance(offers, list) and offers else offers
    offers = offers if isinstance(offers, dict) else {}
    low, high = _num(offers.get("lowPrice")), _num(offers.get("highPrice"))
    agg = offers.get("@type") == "AggregateOffer" or (low is not None and low != high)
    img = d.get("image")
    img = img[0] if isinstance(img, list) and img else img
    brand = d.get("brand")
    return dict(name=d.get("name"), price=None if agg else _num(offers.get("price")),
                price_low=low if agg else None, price_high=high if agg else None,  # 최저가로 뭉개지 않음
                currency=offers.get("priceCurrency"),
                brand=brand.get("name") if isinstance(brand, dict) else brand,
                image=img if isinstance(img, str) else None,
                availability=offers.get("availability"), source="jsonld",
                category=str(d.get("category") or ""))


USED = {"중고나라", "당근", "번개장터"}
IMPORT = {"아마존", "알리익스프레스", "테무"}
FOOD_SITES = {"마켓컬리"}
FOOD_KW = re.compile(r"라면|과자|스낵|음료|소스|식품|커피|차$|김치|쌀|고기|우유|간식|젤리|초콜릿|통조림|비타민|유산균|프로바이오틱|오메가|홍삼|영양제|콜라겐|루테인|건강기능|스낵|짭짤|food|snack|grocery|vitamin|supplement", re.I)
SEALED = re.compile(r"미개봉|밀봉|새상품|sealed", re.I)
NOT_SEALED_OK = re.compile(r"냉장|냉동|직접\s*만|(?<!미)개봉|소분", re.I)


def classify(site, p):
    """channel(일반/중고/직구)은 사이트 기본값, kind(상품/식품)는 카테고리·키워드. 못 정하면 미분류. 근거 없는 식품 중고는 review에 사유."""
    text = f"{p.get('name') or ''} {p.get('category') or ''}"
    channel = "중고" if site in USED else "직구" if site in IMPORT else "일반"
    kind = "식품" if site in FOOD_SITES or FOOD_KW.search(text) else "상품"
    review = None
    if kind == "식품" and channel == "중고" and (not SEALED.search(text) or NOT_SEALED_OK.search(text)):
        review = "식품 중고: 미개봉/밀봉 표기 없음 또는 제외 단어 포함"
    return dict(kind=kind, channel=channel, review=review)


# shortcut: 고정 환율(대략값), 정확한 환율이 필요하면 FX_RATES 환경변수(JSON)로 덮어쓰기
FX = {"KRW": 1, "USD": 1400, "CNY": 200, "EUR": 1500, "JPY": 9.5, "GBP": 1800}
FX.update(json.loads(os.environ.get("FX_RATES", "{}")))


def to_krw(p):
    """가격을 원화로 고정. 원래 통화와 환율은 남기고, 환율을 모르면 가격을 비우고 보류."""
    cur = (p.get("currency") or "KRW").upper()
    rate = FX.get(cur)
    out = dict(orig_currency=cur, orig_price=p.get("price"), fx_rate=rate, currency="KRW")
    for k in ("price", "price_low", "price_high"):
        v = p.get(k)
        out[k] = round(v * rate) if v is not None and rate else None
    if rate is None:
        out["review"] = f"환율 없음: {cur}"
    return out


def candidate_links(html, base):
    host = urlparse(base).netloc.removeprefix("www.")  # 하위 도메인(product.xxx)까지 같은 출처로 본다
    out = []
    for a in BeautifulSoup(html, "lxml").find_all("a", href=True):
        u = urljoin(base, a["href"]).split("#")[0]
        p = urlparse(u)
        if p.scheme in ("http", "https") and (p.netloc == host or p.netloc.endswith("." + host)) and not SKIP.search(u) and u != base and u not in out:
            out.append(u)
    return sorted(out, key=lambda u: not PRODUCT_HINT.search(u))  # 상품처럼 보이는 링크 먼저


def sitemap_urls(s, sitemaps, limit=200):
    """robots.txt에 공개된 사이트맵의 loc. 인덱스면 하위 1단계만."""
    out, queue = [], list(sitemaps)
    for sm in queue[:4]:
        try:
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", s.get(sm, timeout=15).text)
        except requests.RequestException:
            continue
        if sm in sitemaps and any(l.endswith((".xml", ".xml.gz")) or "sitemap" in l for l in locs[:3]):
            queue += locs[:2]
        else:
            out += locs
        if len(out) >= limit:
            break
    return out[:limit]


def crawl_site(name, home, max_pages, delay):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    rp = RobotFileParser(urljoin(home, "/robots.txt"))
    sitemaps = []
    try:
        txt = s.get(rp.url, timeout=10).text
        rp.parse(txt.splitlines())
        sitemaps = re.findall(r"(?im)^sitemap:\s*(\S+)", txt)[:2]
    except requests.RequestException:
        rp = None  # robots 못 읽으면 허용으로 간주

    def get(u):
        if rp and not rp.can_fetch(UA, u):
            return "robots_disallowed", None
        time.sleep(delay)
        try:
            r = s.get(u, timeout=15)
        except requests.RequestException as e:
            return "error:" + type(e).__name__, None
        if r.status_code in (403, 429):
            return f"blocked_{r.status_code}", None
        if r.status_code >= 400:
            return f"error:http_{r.status_code}", None
        if CAPTCHA.search(r.text[:5000]):
            return "captcha", None
        return "ok", r.content

    status, html = get(home)
    if html is None:
        return status, [], 0
    products, visited = [], 1
    cands = candidate_links(html, home) + sitemap_urls(s, sitemaps)
    cands.sort(key=lambda u: not PRODUCT_HINT.search(u))
    for u in cands[:max_pages]:
        st, page = get(u)
        visited += 1
        if page is None:
            if st in ("captcha", "blocked_403", "blocked_429"):
                status = st
                break  # 우회하지 않고 해당 사이트 중단
            continue
        p = parse_product(page, u)
        if p and p["name"]:
            c = classify(name, p)
            products.append(dict(p, site=name, url=u, **extract_allergen_info(page), **c, **{k: v for k, v in to_krw(p).items() if not (k == 'review' and c['review'])}))
    return ("ok" if products else (status if status != "ok" else "no_products")), products, visited


def keep(p):
    """식품은 성분/알레르기 표를 읽는 데 성공했을 때만 저장. 상품은 성분표와 무관하게 저장."""
    return p["kind"] != "식품" or p["allergen_status"] in ("read", "read_empty")


def save(conn, name, status, products, visited, skipped=0):
    with conn.cursor() as c:
        for p in products:
            c.execute("""insert into crawl_products (site,url,name,price,price_low,price_high,currency,brand,image,availability,source,kind,channel,review,orig_currency,fx_rate,ingredient_text,allergen_text,allergens_contains,allergens_trace,ingredient_images,allergen_status)
                values (%(site)s,%(url)s,%(name)s,%(price)s,%(price_low)s,%(price_high)s,%(currency)s,%(brand)s,%(image)s,%(availability)s,%(source)s,%(kind)s,%(channel)s,%(review)s,%(orig_currency)s,%(fx_rate)s,%(ingredient_text)s,%(allergen_text)s,%(allergens_contains)s,%(allergens_trace)s,%(ingredient_images)s,%(allergen_status)s)
                on conflict (site,url) do update set name=excluded.name, price=excluded.price, price_low=excluded.price_low,
                price_high=excluded.price_high, currency=excluded.currency, kind=excluded.kind, channel=excluded.channel, review=excluded.review, orig_currency=excluded.orig_currency, fx_rate=excluded.fx_rate, ingredient_text=excluded.ingredient_text, allergen_text=excluded.allergen_text, allergens_contains=excluded.allergens_contains, allergens_trace=excluded.allergens_trace, ingredient_images=excluded.ingredient_images, allergen_status=excluded.allergen_status, fetched_at=now()""", p)
        c.execute("insert into crawl_site_log (site,status,detail,pages_visited,products_found) values (%s,%s,%s,%s,%s)",
                  (name, status, f"성분 못 읽어 제외한 식품 {skipped}건" if skipped else None, visited, len(products)))
    conn.commit()


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="DB 없이 결과만 출력")
    ap.add_argument("--only", help="쉼표로 구분한 플랫폼 이름")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.5, help="페이지 요청 사이 쉬는 초")
    ap.add_argument("--watch", action="store_true", help="끝나지 않고 계속 반복 (Ctrl+C로 종료)")
    ap.add_argument("--backend", action="store_true",
                    help="꿀픽 백엔드 수집 API로 전송 (COLLECTOR_BACKEND_BASE_URL, KKULPICK_BACKEND_TOKEN_FILE). DATABASE_URL이 있으면 Supabase에도 저장")
    ap.add_argument("--interval", type=int, default=0, help="--watch에서 한 바퀴 끝난 뒤 추가로 쉬는 초 (기본 0, 쉬는 건 100개마다 10분)")
    a = ap.parse_args()
    sites = load_sites()
    if a.only:
        want = set(a.only.split(","))
        sites = [s for s in sites if s[0] in want]
    conn = None
    a.sender = None
    if not a.dry_run and a.backend:
        from .backend import Backend
        try:
            a.sender = Backend()
        except (ValueError, OSError) as e:
            sys.exit(f"백엔드 전송 설정 오류: {e}")
    if not a.dry_run and (os.environ.get("DATABASE_URL") or not a.backend):
        import psycopg
        if not os.environ.get("DATABASE_URL"):
            sys.exit("DATABASE_URL 환경변수가 필요합니다 (또는 --dry-run, --backend)")
        conn = psycopg.connect(os.environ["DATABASE_URL"])
    cycle, saved = 0, 0
    try:
        while True:
            cycle += 1
            print(f"--- {cycle}회차 {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
            saved = run_cycle(sites, a, conn, saved)
            if not a.watch:
                break
            time.sleep(a.interval)
    except DBLost as e:
        sys.exit(f"DB 연결이 끊겨 크롤링을 멈춥니다: {e}")


BATCH, REST = 100, 600  # DB에 100개를 쌓을 때마다 10분(600초) 쉰다


class DBLost(Exception):
    """DB 연결이 끊김. 크롤링 전체를 멈춘다(결과를 저장할 곳이 없으므로)."""


def _db_alive(conn):
    import psycopg
    try:
        conn.execute("select 1")
        conn.commit()
    except psycopg.Error as e:
        raise DBLost(type(e).__name__) from e


def run_cycle(sites, a, conn, saved=0):
    """사이트를 한 바퀴 돌고 누적 저장 수를 돌려준다. --watch면 사이트 오류는 건너뛰고, DB가 끊기면 DBLost로 전체를 멈춘다."""
    for name, home in sites:
        if conn is not None:
            _db_alive(conn)  # 끊긴 상태로 크롤링해서 결과를 버리지 않도록 사이트마다 먼저 확인
        try:
            status, products, visited = crawl_site(name, home, a.max_pages, a.delay)
        except Exception as e:
            if not a.watch:
                raise
            print(f"{name:12} error:{type(e).__name__} {str(e)[:200]}", flush=True)
            continue
        kept = [p for p in products if keep(p)]
        skipped = len(products) - len(kept)
        products = kept
        print(f"{name:12} {status:20} pages={visited:3} products={len(products)} (성분 못 읽어 제외한 식품 {skipped})", flush=True)
        if a.dry_run:
            for p in products[:3]:
                print("   ", p["name"], p["price"] or (p["price_low"], p["price_high"]), p["currency"])
            continue
        sender = getattr(a, "sender", None)
        if sender is not None:
            try:
                print(f"{name:12} backend {sender.deliver(products)}", flush=True)
            except PermissionError as e:
                sys.exit(f"백엔드 인증 실패로 멈춥니다: {e}")
            except Exception as e:  # 네트워크 등: 이 사이트만 건너뛴다(--watch가 아니면 중단)
                if not a.watch:
                    raise
                print(f"{name:12} backend_error:{type(e).__name__}", flush=True)
        if conn is None:  # 백엔드만 전송: 저장 수와 쉬는 규칙은 같게
            saved += len(products)
            if saved >= BATCH:
                print(f"백엔드에 {saved}개 전송, {REST // 60}분 쉽니다 ({time.strftime('%H:%M:%S')})", flush=True)
                time.sleep(REST)
                saved = 0
            continue
        import psycopg
        try:
            save(conn, name, status, products, visited, skipped)
        except psycopg.OperationalError as e:
            raise DBLost(type(e).__name__) from e
        except psycopg.Error as e:  # 데이터 문제 등 연결은 살아 있는 오류: 이 사이트만 버리고 계속
            if conn.closed:
                raise DBLost(type(e).__name__) from e
            if not a.watch:
                raise
            conn.rollback()
            print(f"{name:12} db_error:{type(e).__name__} {str(e)[:200]}", flush=True)
            continue
        saved += len(products)
        if saved >= BATCH:
            print(f"DB에 {saved}개 저장, {REST // 60}분 쉽니다 ({time.strftime('%H:%M:%S')})", flush=True)
            time.sleep(REST)
            saved = 0
    return saved


if __name__ == "__main__":
    main()
