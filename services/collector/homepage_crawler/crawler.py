"""최적화된 홈페이지/URL 통합 크롤러 (엣지 케이스 검증 완료).

핵심 최적화 및 안전성 수정 사항:
1. 도메인 간 병렬 수집 (ThreadPoolExecutor, 사이트 내부는 순차 + delay 준수)
2. HTTP Keep-Alive 커넥션 풀(HTTPAdapter) + gzip/deflate 응답 압축 활성화
3. 페이지당 BeautifulSoup 4회 중복 파싱 -> 단 1회 파싱 후 soup 객체 공유
   + JSON-LD 정규식 Fast-path (extract_jsonld_fast) 제공
4. 링크/큐 중복 검사 O(N^2) 리스트 탐색 -> O(1) set 해시 탐색
5. 4단계 폴백 통합: JSON-LD -> 숨은 JSON(__NEXT_DATA__) -> Open Graph -> 플랫폼별 CSS
6. [안전성 수정] _num()이 가격 범위('12,900원 ~ 15,000원')나 할인율 혼재 문자열을 합치지 않고 None으로 거부
7. [안전성 수정] 플랫폼 CSS 감지를 엄격화하고, 페이지 내 단일 요소(len == 1)만 매칭될 때만 상세 상품으로 인정(목록 카드 오인 차단)
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

from .allergens import extract_allergen_info, _HTML_PARSER

UA = "Mozilla/5.0 (compatible; KkulpickStudentCrawler/0.2)"
SKIP = re.compile(r"login|member|cart|basket|order|checkout|pay|signin|join|mypage|/api/|logout", re.I)
PRODUCT_HINT = re.compile(r"product|goods|item|/p/|/pd/|prdno|goodsno|itemno|/products?/|/vp/|goodsdetail|productdetail|shop/item", re.I)
PRODUCT_ID = re.compile(
    r"(?:product|goods|item|/p|/pd|/dp)[^?#]*[/=]\w*\d{4,}"
    r"|/product/[^/?#]+/\d+(?:/|$)"
    r"|/shop/item/[^/?#]+/\d+"
    r"|[?&](?:productId|product_no|goodsNo|prdNo|itemId)=\w*\d+",
    re.I,
)
LISTING_PAGE = re.compile(
    r"^https?://[^/]+/(?:category|categories|project|brand|event|plan|search|board|notice)(?:/|$)"
    r"|/product/(?:list|project|search)[^/]*\.html"
    r"|[?&]cate_no=\d+(?!.*product_no=)",
    re.I,
)
CAPTCHA = re.compile(r"captcha|are you a robot|access denied|비정상적인 접근", re.I)

_JSONLD_SCRIPT_RE = re.compile(
    r'<script\b[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)

NAME_KEYS = ("name", "productName", "goodsName", "itemName", "prdNm", "goodsNm", "title")
PRICE_KEYS = ("salePrice", "sellPrice", "finalPrice", "discountPrice", "price", "goodsPrice")
EMBED = re.compile(r"window\.__[A-Z_]+__\s*=\s*(\{.*?\})\s*;?\s*$", re.S)

# 엄격한 단일 가격 패턴 (앞뒤 통화 기호/단위만 허용, 범위 '~' 또는 복수 숫자 거부)
_SINGLE_PRICE_RE = re.compile(
    r"^\s*(?:(?:KRW|USD|EUR|JPY|CNY|GBP)\s*|[₩$€¥£]\s*)?"
    r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,4}))?"
    r"(?:\s*(?:원|KRW|USD|EUR|JPY|CNY|GBP))?\s*$",
    re.I,
)

# unified_live/storefront.py와 동일한 엄격한 플랫폼 시그니처
PLATFORM_CSS = {
    "cafe24": (
        re.compile(r"cafe24|xans-product|ec-base-product", re.I),
        {"name": ".xans-product-detail .headingArea h2", "price": "#span_product_price_text", "image": ".xans-product-image .BigImage"},
    ),
    "godomall": (
        re.compile(r"godomall|godo\.co\.kr|gd_goods_view", re.I),
        {"name": ".item_detail_tit h3", "price": ".item_price dd strong", "image": "#mainImage img"},
    ),
    "makeshop": (
        re.compile(r"makeshop|shopdetail\.html|shopbrand\.html", re.I),
        {"name": ".thumb-info .tit-prd", "price": "#pricevalue", "image": ".thumb-wrap img"},
    ),
    "shopify": (
        re.compile(r'cdn\.shopify\.com|Shopify\.shop|name=["\']generator["\'][^>]+Shopify', re.I),
        {"name": ".product__title h1", "price": ".product__info-container .price-item--regular", "image": ".product__media img"},
    ),
}

USED = {"중고나라", "당근", "번개장터", "후르츠패밀리"}
IMPORT = {"아마존", "알리익스프레스", "테무"}
FOOD_SITES = {"마켓컬리", "동원몰", "풀무원샵", "하림몰", "허닭"}
FOOD_KW = re.compile(
    r"라면|과자|스낵|음료|소스|식품|커피|차$|호지차|녹차|홍차|김치|쌀|고기|우유|간식|젤리|초콜릿|통조림|참치|골뱅이|리챔|햄|만두|두부|유정란|달걀|계란|식빵|베이글|쿠키|스콘|그래놀라|칼국수|우동|소바|스튜|핫도그|닭가슴살|스테이크|황도|백도|과일청|"
    r"비타민|유산균|프로바이오틱|오메가|홍삼|영양제|콜라겐|루테인|건강기능|짭짤|"
    r"food|snack|grocery|vitamin|supplement",
    re.I,
)
SEALED = re.compile(r"미개봉|밀봉|새상품|sealed", re.I)
NOT_SEALED_OK = re.compile(r"냉장|냉동|직접\s*만|(?<!미)개봉|소분", re.I)

FX = {"KRW": 1, "USD": 1400, "CNY": 200, "EUR": 1500, "JPY": 9.5, "GBP": 1800}
FX.update(json.loads(os.environ.get("FX_RATES", "{}")))

_STATE_LOCK = threading.Lock()
_VISITED_URLS: dict[str, set[str]] = {}
_DISCOVERED_URLS: dict[str, list[str]] = {}


def load_sites(md_path=None):
    if md_path:
        target = Path(md_path)
    else:
        target = Path(__file__).with_name("platform-urls.md")
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([\w.-]+\.[\w.-]+(?:/[\w./-]*)?)\s*\|\s*$", target.read_text(encoding="utf-8"), re.M)
    return [(n, "https://" + d) for n, d in rows if n not in ("플랫폼",)]


def rank(u):
    if LISTING_PAGE.search(u):
        return 2
    if PRODUCT_ID.search(u):
        return 0
    return 1 if PRODUCT_HINT.search(u) else 3


def _num(v):
    """단일 숫자 금액만 파싱한다. 범위('12,900 ~ 15,000')나 복수 숫자 문자열은 안전하게 None 반환."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if v >= 0 else None
    m = _SINGLE_PRICE_RE.match(str(v))
    if not m:
        return None
    whole = m.group(1).replace(",", "")
    frac = m.group(2)
    try:
        return float(f"{whole}.{frac}" if frac else whole)
    except ValueError:
        return None


def _from_jsonld(d, url):
    offers = d.get("offers")
    if isinstance(offers, list):
        if len(offers) > 1:
            prices = [_num(o.get("price")) for o in offers if isinstance(o, dict) and _num(o.get("price")) is not None]
            if len(set(prices)) > 1:
                # 옵션별 가격이 다르면 최저가로 뭉개지 않고 범위 가격으로 기록
                offers = {"@type": "AggregateOffer", "lowPrice": min(prices), "highPrice": max(prices),
                          "priceCurrency": offers[0].get("priceCurrency"), "availability": offers[0].get("availability")}
            else:
                offers = offers[0]
        elif offers:
            offers = offers[0]
    offers = offers if isinstance(offers, dict) else {}
    low, high = _num(offers.get("lowPrice")), _num(offers.get("highPrice"))
    agg = offers.get("@type") == "AggregateOffer" or (low is not None and low != high)
    img = d.get("image")
    img = img[0] if isinstance(img, list) and img else img
    if isinstance(img, dict):
        img = img.get("url") or img.get("contentUrl")
    brand = d.get("brand")
    return dict(
        name=d.get("name"),
        price=None if agg else _num(offers.get("price")),
        price_low=low if agg else None,
        price_high=high if agg else None,
        currency=offers.get("priceCurrency"),
        brand=brand.get("name") if isinstance(brand, dict) else brand,
        image=img if isinstance(img, str) else None,
        availability=offers.get("availability"),
        source="jsonld",
        category=str(d.get("category") or ""),
    )


def extract_jsonld_fast(html, url):
    """BeautifulSoup DOM 생성 없이 정규식으로 JSON-LD Product만 즉시 추출."""
    text = html.decode("utf-8", "ignore") if isinstance(html, (bytes, bytearray)) else html
    for match in _JSONLD_SCRIPT_RE.finditer(text):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            d = stack.pop()
            if not isinstance(d, dict):
                continue
            graph = d.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            t = d.get("@type")
            if "Product" in (t if isinstance(t, list) else [t]):
                return _from_jsonld(d, url)
    return None


def _embedded_product(soup):
    blobs = [t.string for t in soup.find_all("script", id="__NEXT_DATA__") if t.string]
    for t in soup.find_all("script"):
        if t.string and "window.__" in t.string:
            m = EMBED.search(t.string.strip())
            if m:
                blobs.append(m.group(1))
    for blob in blobs:
        try:
            stack = [json.loads(blob)]
        except ValueError:
            continue
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                name = next((d[k] for k in NAME_KEYS if isinstance(d.get(k), str) and d[k].strip()), None)
                price = next((_num(d[k]) for k in PRICE_KEYS if _num(d.get(k)) is not None), None)
                if name and price is not None:
                    img = d.get("image") or d.get("imageUrl") or d.get("thumbnail")
                    return dict(
                        name=name,
                        price=price,
                        price_low=None,
                        price_high=None,
                        currency=d.get("currency") or "KRW",
                        brand=d.get("brand") if isinstance(d.get("brand"), str) else None,
                        image=img if isinstance(img, str) else None,
                        availability=d.get("availability"),
                        source="embedded",
                        category=str(d.get("category") or ""),
                    )
                stack.extend(d.values())
    return None


def _css_fallback(soup, html_text=None):
    """단일 플랫폼 시그니처가 명확하고, 이름·가격 선택자가 각각 정확히 1개(상세 페이지)일 때만 추출."""
    raw = html_text if html_text is not None else str(soup)
    matched_plats = [plat for plat, (pat, _) in PLATFORM_CSS.items() if pat.search(raw)]
    if len(matched_plats) != 1:
        return None
    plat = matched_plats[0]
    sel = PLATFORM_CSS[plat][1]
    n_nodes = soup.select(sel["name"])
    p_nodes = soup.select(sel["price"])
    if len(n_nodes) != 1 or len(p_nodes) != 1:
        return None
    i_nodes = soup.select(sel["image"])
    name = n_nodes[0].get_text(" ", strip=True)
    price = _num(p_nodes[0].get_text(" ", strip=True))
    img = (i_nodes[0].get("src") or i_nodes[0].get("data-src")) if len(i_nodes) == 1 else None
    if name and price is not None:
        return dict(
            name=name,
            price=price,
            price_low=None,
            price_high=None,
            currency="KRW",
            brand=None,
            image=img,
            availability=None,
            source=f"css:{plat}",
            category="",
        )
    return None


def parse_product(html, url, soup=None, *, fast_jsonld=True, parser=None):
    """4단계 폴백 추출: JSON-LD -> 숨은 JSON(__NEXT_DATA__) -> Open Graph -> 플랫폼 CSS."""
    if fast_jsonld and soup is None:
        fast = extract_jsonld_fast(html, url)
        if fast:
            return fast

    if soup is None:
        soup = BeautifulSoup(html, parser or _HTML_PARSER)

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
            graph = d.get("@graph")
            if isinstance(graph, list):
                stack.extend(graph)
            t = d.get("@type")
            if "Product" in (t if isinstance(t, list) else [t]):
                return _from_jsonld(d, url)

    emb = _embedded_product(soup)
    if emb:
        return emb

    og = {m.get("property"): m.get("content") for m in soup.find_all("meta") if m.get("property")}
    price = _num(og.get("product:price:amount") or og.get("og:price:amount"))
    if (og.get("og:type", "").startswith("product") and not LISTING_PAGE.search(url)) or price is not None:
        if price is None and LISTING_PAGE.search(url):
            return None
        return dict(
            name=og.get("og:title"),
            price=price,
            price_low=None,
            price_high=None,
            currency=og.get("product:price:currency") or og.get("og:price:currency"),
            brand=og.get("product:brand"),
            image=og.get("og:image"),
            availability=og.get("product:availability") or og.get("og:availability"),
            source="og",
            category=og.get("product:category") or "",
        )

    html_text = html.decode("utf-8", "ignore") if isinstance(html, (bytes, bytearray)) else html
    return _css_fallback(soup, html_text)


COSMETIC_OR_NONFOOD_KW = re.compile(
    r"토너|세럼|앰플|로션|수분크림|선크림|클렌징|폼클렌징|샴푸|린스|트리트먼트|바디워시|마스크팩|화장솜|패드|립밤|틴트|파운데이션|"
    r"키링|파우치|텀블러|머그|컵\s*세트|드리퍼|행주|수세미|화장지|물티슈",
    re.I,
)


def classify(site, p, allergen=None):
    text = f"{p.get('name') or ''} {p.get('category') or ''}"
    channel = "중고" if site in USED else "직구" if site in IMPORT else "일반"
    has_food_allergen = bool(allergen and allergen.get("allergen_status") in ("read", "read_empty"))
    is_food = (site in FOOD_SITES or bool(FOOD_KW.search(text)) or has_food_allergen) and not bool(COSMETIC_OR_NONFOOD_KW.search(text))
    kind = "식품" if is_food else "상품"
    review = None
    if kind == "식품" and channel == "중고" and (not SEALED.search(text) or NOT_SEALED_OK.search(text)):
        review = "식품 중고: 미개봉/밀봉 표기 없음 또는 제외 단어 포함"
    return dict(kind=kind, channel=channel, review=review)


def to_krw(p):
    cur = (p.get("currency") or "KRW").upper()
    rate = FX.get(cur)
    out = dict(orig_currency=cur, orig_price=p.get("price"), fx_rate=rate, currency="KRW")
    for k in ("price", "price_low", "price_high"):
        v = p.get(k)
        out[k] = round(v * rate) if v is not None and rate else None
    if rate is None:
        out["review"] = f"환율 없음: {cur}"
    return out


def canonical_url(html, url, soup=None, *, parser=None):
    if soup is None:
        soup = BeautifulSoup(html, parser or _HTML_PARSER)
    tag = soup.find("link", rel="canonical", href=True)
    if tag:
        c = urljoin(url, tag["href"]).split("#")[0]
        if urlparse(c).netloc.removeprefix("www.") == urlparse(url).netloc.removeprefix("www."):
            return c
    return url


def candidate_links(html, base, soup=None, *, parser=None):
    if soup is None:
        soup = BeautifulSoup(html, parser or _HTML_PARSER)
    host = urlparse(base).netloc.removeprefix("www.")
    out = []
    seen_set = set()
    for a in soup.find_all("a", href=True):
        u = urljoin(base, a["href"]).split("#")[0]
        if u in seen_set or u == base:
            continue
        p = urlparse(u)
        if p.scheme in ("http", "https") and (p.netloc == host or p.netloc.endswith("." + host)) and not SKIP.search(u):
            seen_set.add(u)
            out.append(u)
    return sorted(out, key=rank)


def sitemap_urls(s, sitemaps, limit=1000):
    out, queue = [], list(sitemaps)
    for sm in queue[:10]:
        try:
            locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", s.get(sm, timeout=15).text)
        except requests.RequestException:
            continue
        if sm in sitemaps and any(l.endswith((".xml", ".xml.gz")) or "sitemap" in l for l in locs[:3]):
            queue += locs[:6]
        else:
            out += locs
        if len(out) >= limit:
            break
    return out[:limit]


def build_session(keep_alive=True):
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept-Encoding": "gzip, deflate",
    })
    if keep_alive:
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=16)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
    else:
        s.headers["Connection"] = "close"
    return s


def crawl_site(name, home, max_pages, delay, *, session=None, keep_alive=True, reset_state=False, parser=None):
    owns_session = session is None
    s = session or build_session(keep_alive=keep_alive)
    eng = parser or _HTML_PARSER
    try:
        rp = RobotFileParser(urljoin(home, "/robots.txt"))
        sitemaps = []
        try:
            r = s.get(rp.url, timeout=10)
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
                sitemaps = re.findall(r"(?im)^sitemap:\s*(\S+)", r.text)[:4]
        except requests.RequestException:
            rp = None

        def get(u):
            if rp and not rp.can_fetch(UA, u):
                return "robots_disallowed", None
            if delay > 0:
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
        with _STATE_LOCK:
            if reset_state:
                _VISITED_URLS[name] = set()
                _DISCOVERED_URLS[name] = []
            seen = set(_VISITED_URLS.setdefault(name, set()))
            pool = list(_DISCOVERED_URLS.setdefault(name, []))

        home_soup = BeautifulSoup(html, eng)
        raw_cands = list(dict.fromkeys(pool + candidate_links(html, home, soup=home_soup) + sitemap_urls(s, sitemaps)))
        raw_cands.sort(key=rank)
        unseen = [u for u in raw_cands if u not in seen]
        if not unseen and raw_cands:
            seen.clear()
            unseen = raw_cands

        queue = list(unseen)
        queued_set = set(queue)
        idx = 0
        visited_in_cycle = 0

        while idx < len(queue) and visited_in_cycle < max_pages:
            u = queue[idx]
            idx += 1
            if u in seen:
                continue
            seen.add(u)
            visited_in_cycle += 1
            st, page = get(u)
            visited += 1
            if page is None:
                if st in ("captcha", "blocked_403", "blocked_429"):
                    status = st
                    break
                continue

            page_soup = BeautifulSoup(page, eng)

            for sub in candidate_links(page, u, soup=page_soup):
                if sub not in seen and sub not in queued_set and PRODUCT_HINT.search(sub):
                    queue.append(sub)
                    queued_set.add(sub)

            p = parse_product(page, u, soup=page_soup, fast_jsonld=False)
            if p and p["name"]:
                allergen = extract_allergen_info(page, soup=page_soup)
                c = classify(name, p, allergen=allergen)
                canon = canonical_url(page, u, soup=page_soup)
                krw = {k: v for k, v in to_krw(p).items() if not (k == "review" and c["review"])}
                products.append(dict(p, site=name, url=canon, **allergen, **c, **krw))

        with _STATE_LOCK:
            _VISITED_URLS[name] = seen
            _DISCOVERED_URLS[name] = [u for u in queue[idx:] if u not in seen][:2000]

        return ("ok" if products else (status if status != "ok" else "no_products")), products, visited
    finally:
        if owns_session:
            s.close()


def crawl_sites_parallel(sites, max_pages=12, delay=0.5, workers=4, *, keep_alive=True, reset_state=False, parser=None, raise_on_error=False):
    results = {}
    use_default_sig = keep_alive is True and reset_state is False and parser is None

    def _invoke(nm, hm):
        if use_default_sig:
            return crawl_site(nm, hm, max_pages, delay)
        return crawl_site(nm, hm, max_pages, delay, keep_alive=keep_alive, reset_state=reset_state, parser=parser)

    if workers <= 1:
        for name, home in sites:
            try:
                results[name] = _invoke(name, home)
            except Exception as e:
                if raise_on_error:
                    raise
                results[name] = (f"error:{type(e).__name__}", [], 0)
        return results

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_invoke, name, home): name for name, home in sites}
        for future in as_completed(future_map):
            name = future_map[future]
            try:
                results[name] = future.result()
            except Exception as e:
                if raise_on_error:
                    raise
                results[name] = (f"error:{type(e).__name__}", [], 0)
    return results


def crawl_single_url(url, site_name=None, *, parser=None):
    """단일 실제 쇼핑몰 상품 URL을 robots.txt 준수 하에 즉시 수집·파싱해 검증한다."""
    eng = parser or _HTML_PARSER
    parsed_u = urlparse(url)
    if parsed_u.scheme not in ("http", "https") or not parsed_u.netloc:
        return "invalid_url", None
    host = parsed_u.netloc.removeprefix("www.")
    site = site_name or host
    s = build_session(keep_alive=True)
    try:
        rp = RobotFileParser(f"{parsed_u.scheme}://{parsed_u.netloc}/robots.txt")
        try:
            rr = s.get(rp.url, timeout=8)
            if rr.status_code in (401, 403):
                rp.disallow_all = True
            elif rr.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(rr.text.splitlines())
        except requests.RequestException:
            rp = None
        if rp and not rp.can_fetch(UA, url):
            return "robots_disallowed", None
        r = s.get(url, timeout=15)
        if r.status_code in (403, 429):
            return f"blocked_{r.status_code}", None
        if r.status_code >= 400:
            return f"error:http_{r.status_code}", None
        if CAPTCHA.search(r.text[:5000]):
            return "captcha", None
        soup = BeautifulSoup(r.content, eng)
        p = parse_product(r.content, url, soup=soup, fast_jsonld=False)
        if not p or not p.get("name"):
            return "no_product_metadata", None
        allergen = extract_allergen_info(r.content, soup=soup)
        c = classify(site, p, allergen=allergen)
        canon = canonical_url(r.content, url, soup=soup)
        krw = {k: v for k, v in to_krw(p).items() if not (k == "review" and c["review"])}
        return "ok", dict(p, site=site, url=canon, **allergen, **c, **krw)
    except requests.RequestException as e:
        return f"error:{type(e).__name__}", None
    finally:
        s.close()


def keep(p):
    return p["kind"] != "식품" or p["allergen_status"] in ("read", "read_empty")


SQL_INSERT_PRODUCT = """insert into crawl_products (site,url,name,price,price_low,price_high,currency,brand,image,availability,source,kind,channel,review,orig_currency,fx_rate,ingredient_text,allergen_text,allergens_contains,allergens_trace,ingredient_images,allergen_status)
    values (%(site)s,%(url)s,%(name)s,%(price)s,%(price_low)s,%(price_high)s,%(currency)s,%(brand)s,%(image)s,%(availability)s,%(source)s,%(kind)s,%(channel)s,%(review)s,%(orig_currency)s,%(fx_rate)s,%(ingredient_text)s,%(allergen_text)s,%(allergens_contains)s,%(allergens_trace)s,%(ingredient_images)s,%(allergen_status)s)
    on conflict (site,url) do update set name=excluded.name, price=excluded.price, price_low=excluded.price_low,
    price_high=excluded.price_high, currency=excluded.currency, kind=excluded.kind, channel=excluded.channel, review=excluded.review, orig_currency=excluded.orig_currency, fx_rate=excluded.fx_rate, ingredient_text=excluded.ingredient_text, allergen_text=excluded.allergen_text, allergens_contains=excluded.allergens_contains, allergens_trace=excluded.allergens_trace, ingredient_images=excluded.ingredient_images, allergen_status=excluded.allergen_status, fetched_at=now()"""


def save(conn, name, status, products, visited, skipped=0):
    """기존 baseline/homepage_crawler/schema.sql (crawl_products, crawl_site_log) 100% 호환 저장 함수.

    크롤링만 워커 스레드로 병렬 수행하고, save()는 메인 스레드에서 단일 트랜잭션으로 호출하므로
    psycopg 단일 커넥션에서도 스레드 충돌(Thread-safety 문제)이 전혀 발생하지 않는다.
    """
    with conn.cursor() as c:
        for p in products:
            c.execute(SQL_INSERT_PRODUCT, p)
        c.execute(
            "insert into crawl_site_log (site,status,detail,pages_visited,products_found) values (%s,%s,%s,%s,%s)",
            (name, status, f"성분 못 읽어 제외한 식품 {skipped}건" if skipped else None, visited, len(products)),
        )
    conn.commit()


BATCH, REST = 100, int(os.environ.get("HOMEPAGE_CRAWLER_REST_SECONDS", "600"))


class DBLost(Exception):
    """DB 연결이 끊김. 크롤링 전체를 멈춘다."""


def _db_alive(conn):
    import psycopg
    try:
        conn.execute("select 1")
        conn.commit()
    except psycopg.Error as e:
        raise DBLost(type(e).__name__) from e


def run_cycle(sites, a, conn, saved=0):
    """등록된 전체 사이트를 도메인 병렬(workers)로 수집한 뒤, 메인 스레드에서 안전하게 백엔드 전송 및 DB 저장을 수행한다."""
    workers = max(1, int(getattr(a, "workers", 1)))
    for start in range(0, len(sites), workers):
        if conn is not None:
            _db_alive(conn)
        chunk = sites[start:start + workers]
        batch_results = crawl_sites_parallel(
            chunk,
            max_pages=a.max_pages,
            delay=a.delay,
            workers=len(chunk) if workers > 1 else 1,
            keep_alive=True,
            reset_state=False,
            raise_on_error=not getattr(a, "watch", False),
        )
        for name, _ in chunk:
            status, products, visited = batch_results[name]
            if status.startswith("error:") and not a.watch and not a.dry_run:
                print(f"{name:12} {status}", flush=True)
            kept = [p for p in products if keep(p)]
            skipped = len(products) - len(kept)
            products = kept
            print(f"{name:12} {status:20} pages={visited:3} products={len(products)} (성분 못 읽어 제외한 식품 {skipped})", flush=True)
            if a.dry_run:
                for p in products[:3]:
                    print("   ", p["name"], p["price"] or (p["price_low"], p["price_high"]), p["currency"])
                continue
            sender = getattr(a, "sender", None)
            if sender is not None and products:
                try:
                    print(f"{name:12} backend {sender.deliver(products)}", flush=True)
                except PermissionError as e:
                    sys.exit(f"백엔드 인증 실패로 멈춥니다: {e}")
                except Exception as e:
                    if not a.watch:
                        raise
                    print(f"{name:12} backend_error:{type(e).__name__}", flush=True)
            if conn is None:
                saved += len(products)
                if REST and saved >= BATCH:
                    print(f"백엔드에 {saved}개 전송, {REST // 60}분 쉽니다 ({time.strftime('%H:%M:%S')})", flush=True)
                    time.sleep(REST)
                    saved = 0
                continue
            import psycopg
            try:
                save(conn, name, status, products, visited, skipped)
            except psycopg.OperationalError as e:
                raise DBLost(type(e).__name__) from e
            except psycopg.Error as e:
                if conn.closed:
                    raise DBLost(type(e).__name__) from e
                if not a.watch:
                    raise
                conn.rollback()
                print(f"{name:12} db_error:{type(e).__name__} {str(e)[:200]}", flush=True)
                continue
            saved += len(products)
            if REST and saved >= BATCH:
                print(f"DB에 {saved}개 저장, {REST // 60}분 쉽니다 ({time.strftime('%H:%M:%S')})", flush=True)
                time.sleep(REST)
                saved = 0
    return saved


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="꿀픽 최적화 홈페이지 크롤러 (baseline CLI/Docker 100% 호환)")
    ap.add_argument("--dry-run", action="store_true", help="DB/백엔드 전송 없이 결과만 출력")
    ap.add_argument("--only", help="쉼표로 구분한 플랫폼 이름 (미지정 시 platform-urls.md 전체 수집)")
    ap.add_argument("--max-pages", type=int, default=12)
    ap.add_argument("--delay", type=float, default=0.5, help="동일 사이트 내 요청 간 대기 초")
    ap.add_argument("--workers", type=int, default=int(os.environ.get("HOMEPAGE_CRAWLER_WORKERS", "6")), help="동시 수집 도메인 워커 수")
    ap.add_argument("--watch", action="store_true", help="끝나지 않고 계속 반복 수집")
    ap.add_argument("--backend", action="store_true", help="꿀픽 백엔드 수집 API(Observation v2) 전송")
    ap.add_argument("--interval", type=int, default=0, help="--watch 한 바퀴 완료 후 추가 대기 초")
    a = ap.parse_args()
    sites = load_sites()
    a.only = a.only or os.environ.get("HOMEPAGE_CRAWLER_ONLY", "").strip() or None
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
            print(f"--- {cycle}회차 {time.strftime('%Y-%m-%d %H:%M:%S')} (대상: {len(sites)}개 사이트, W={a.workers})", flush=True)
            saved = run_cycle(sites, a, conn, saved)
            if not a.watch:
                break
            time.sleep(a.interval)
    except DBLost as e:
        sys.exit(f"DB 연결이 끊겨 크롤링을 멈춥니다: {e}")
    finally:
        if conn is not None and not conn.closed:
            conn.close()


if __name__ == "__main__":
    main()
