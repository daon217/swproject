"""DB에 관련 추천 상품이 전혀 없을 때만(0건) 실행되는 실시간 쇼핑몰 검색·적재 폴백.

원칙:
1. 기존 DB 카탈로그 추천 결과가 1건이라도 있으면 절대 호출하지 않는다.
2. 사용자가 UI 설정에서 '추천 상품 없을 시 AI 추천(ai_fallback)'을 켰을 때만 실행한다.
3. LLM은 짧은 핵심 검색어(1~2개) 추출과 최종 후보(5~8개) 선택·이유 작성만 담당하여
   1회당 추가 토큰을 ~200토큰 이내(전체 합산 ~1,000토큰)로 억제한다.
4. 실시간 검색으로 찾은 상품은 즉시 app.catalog_items / app.offers / 임베딩 인덱스에 적재하여
   화면에서 바로 클릭·가격 비교가 가능하고 다음 검색부터는 DB에서 즉시 추천되게 한다.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime

from .adapters.postgres import PgCatalog, PgVectorIndex, join_product_id
from .embedders import document_text
from .pipeline import modifier_keywords, name_keywords
from .rankers import FALLBACK_MODEL

log = logging.getLogger("recommendation.live_fallback")
UA = "Mozilla/5.0 (compatible; KkulpickLiveSearch/1.0)"


# 단독 검색어로 쓰면 안 되는 수식어·원료 일부('무가당 땅콩 버터' -> '무가당' 단독 검색 방지, '제로 카카오 초콜릿' -> '제로'/'카카오' 단독 검색 방지)
_MODIFIER_ONLY = {
    "무가당", "저당", "무설탕", "제로", "슈가프리", "저칼로리", "무첨가", "유기농", "프리미엄", "고단백", "비건",
    "글루텐프리", "친환경", "대용량", "소용량", "미니", "초경량", "경량", "휴대용", "무소음", "저소음", "방수", "고속",
    "국내산", "미국산", "국산", "수제", "전통", "오리지널", "클래식", "스페셜", "에디션", "단독", "기획", "공식",
    "볶은", "구운", "삶은", "카카오", "다크", "밀크", "화이트", "블랙", "그레이", "브라운", "실버", "골드",
}

_FOOD_CATEGORY_CHECK = re.compile(
    r"식품|간식|과자|스낵|초콜릿|초코|캔디|사탕|젤리|견과|땅콩|버터|잼|스프레드|음료|커피|차|티|우유|두유|요거트|"
    r"치즈|라면|면|파스타|국|탕|찌개|만두|돈까스|까스|갈비|고기|정육|과일|영양제|비타민|홍삼|프로틴|꿀|시럽|소스|오일|"
    r"메밀|보리|귀리|오트|현미|잡곡|원두|대두|콩|두부",
    re.I,
)
_NON_FOOD_CHECK = re.compile(
    r"가방|백|숄더백|토트백|클러치|파우치|지갑|신발|스니커즈|부츠|로퍼|샌들|슬리퍼|자켓|재킷|코트|패딩|점퍼|가디건|"
    r"니트|스웨터|셔츠|블라우스|티셔츠|맨투맨|후드|바지|팬츠|데님|스커트|원피스|모자|비니|캡|양말|주얼리|목걸이|반지|"
    r"귀걸이|시계|안경|선글라스|케이스|키링|인형|쿠션|침구|이불|커튼|러그|조명|의자|테이블|화장품|립|향수|퍼퓸|핸드크림|바디",
    re.I,
)


def extract_search_keywords(query: str) -> list[str]:
    """상품명/검색어에서 쇼핑몰 검색용 키워드를 순서대로 추출한다.
    1순위: '선호 수식어(무가당·제로 등) + 핵심 품목 명사' (예: '무가당 땅콩버터', '제로 초콜릿')
    2순위: 1순위 검색 결과가 없을 때를 대비한 '핵심 품목 명사' (예: '땅콩버터', '초콜릿')
    수식어('무가당', '제로') 단독 검색어는 절대 반환하지 않는다."""
    out: list[str] = []
    words = [w for w in name_keywords(query) if w.lower() not in _MODIFIER_ONLY]
    mods = modifier_keywords(query)

    core_phrase = f"{words[-2]} {words[-1]}" if len(words) >= 2 else (words[-1] if words else "")
    core_head = words[-1] if words else ""

    # 1순위: 수식어(무가당/제로) + 핵심 품목 조합을 맨 앞에 배치
    if mods and core_head:
        mod_phrase = f"{mods[0]} {core_phrase}" if len(words) >= 2 else f"{mods[0]} {core_head}"
        out.append(mod_phrase)
        if core_phrase != core_head:
            out.append(f"{mods[0]} {core_head}")

    # 2순위: 수식어+품목 일치 상품이 없을 때 일반 관련 상품을 찾기 위한 핵심 품목 키워드
    if core_phrase and core_phrase not in out:
        out.append(core_phrase)
    if core_head and core_head not in out:
        out.append(core_head)
    for kw in reversed(words):
        if kw not in out:
            out.append(kw)
    if out:
        return out[:3]

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key, timeout=8.0, max_retries=0)
            resp = client.messages.create(
                model=FALLBACK_MODEL,
                # 최신 모델은 생각 토큰도 max_tokens에 포함한다. 45면 답이 비었다. 과금은 실제 생성분만.
                max_tokens=1024,
                output_config={"effort": "low"},
                system=(
                    "상품명에서 쇼핑몰에 검색할 '완전한 핵심 품목명' 1~2개만 한 줄에 하나씩 출력해.\n"
                    "규칙:\n"
                    "- '무가당', '제로', '카카오', '유기농' 같은 수식어나 재료 앞단어만 단독으로 출력하지 말고 반드시 뒤에 오는 최종 품목 명사(예: '땅콩버터', '다크 초콜릿', '무선 키보드')를 포함해 출력해.\n"
                    "- 수량·용량·광고문구·설명 금지."
                ),
                messages=[{"role": "user", "content": query[:150]}],
            )
            for block in resp.content:
                txt = getattr(block, "text", "") or ""
                for line in txt.splitlines():
                    cleaned = re.sub(r"^[\d\-\*\.\)\s]+", "", line).strip()
                    if 2 <= len(cleaned) <= 30 and cleaned.lower() not in _MODIFIER_ONLY and cleaned not in out:
                        out.append(cleaned)
        except Exception as e:
            log.warning("LLM 검색어 추출 실패, 규칙 키워드로 대체: %s", e)

    return out[:2]


def _search_hnsmall(keyword: str, limit: int = 5, domain: str = "product") -> list[dict]:
    """홈앤쇼핑(hnsmall.com, CATALOG_URL_HOSTS 허용 도메인) 검색 결과에서 식품·일반 상품을 가져온다."""
    q = urllib.parse.quote(keyword)
    url = f"https://www.hnsmall.com/search/search.do?query={q}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    results: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            html = r.read().decode("utf-8", errors="ignore")
        pattern = re.compile(
            r'<a\s+href="https?://www\.hnsmall\.com/display/goods\.do\?goods_code=(\d+)[^"]*"\s+class="tit">\s*(.*?)\s*</a>'
            r'(.*?)(?:</li>|</ul>|<a\s+href="https?://www\.hnsmall\.com/display/goods\.do)',
            re.S,
        )
        for m in pattern.finditer(html):
            code = m.group(1)
            name = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            tail = m.group(3)[:800]
            pm = re.search(r'class="price"[^>]*>.*?([\d,]{3,})', tail, re.S)
            if not code or not name or not pm:
                continue
            if domain == "food" and _NON_FOOD_CHECK.search(name):
                continue
            price_str = pm.group(1).replace(",", "")
            p_url = f"https://www.hnsmall.com/display/goods.do?goods_code={code}"
            results.append({
                "source": "homepage_hnsmall_com",
                "source_listing_id": hashlib.sha256(p_url.encode()).hexdigest()[:40],
                "variant_key": "default",
                "name": name[:500],
                "price": str(int(float(price_str))),
                "currency": "KRW",
                "condition": "unknown",
                "availability": "available",
                "url": p_url,
                "brand": None,
                "image_url": None,
            })
            if len(results) >= limit:
                break
    except Exception as e:
        log.warning("홈앤쇼핑 실시간 검색 실패 (%s): %s", keyword, e)
    return results


def _search_29cm(keyword: str, limit: int = 5, domain: str = "product") -> list[dict]:
    """29CM 공개 검색 API에서 판매 중인 상품을 가져온다(CATALOG_URL_HOSTS 허용 도메인)."""
    q = urllib.parse.quote(keyword)
    fetch_limit = limit * 3 if domain == "food" else limit
    url = f"https://search-api.29cm.co.kr/api/v4/products?keyword={q}&limit={fetch_limit}&offset=0"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    results: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            payload = json.loads(r.read().decode("utf-8", errors="ignore"))
        items = payload.get("data") or []
        if not isinstance(items, list):
            return []
        for it in items:
            if not isinstance(it, dict) or it.get("isSoldOut"):
                continue
            item_no = it.get("itemNo")
            name = (it.get("itemName") or "").strip()
            price = it.get("lastSalePrice") or it.get("consumerPrice")
            if not item_no or not name or not price:
                continue
            cat_info = json.dumps(it.get("frontCategoryInfo") or {}, ensure_ascii=False)
            combined_text = f"{name} {cat_info}"
            if domain == "food":
                # 29CM는 패션·잡화 비중이 높으므로 '버터'·'카카오' 색상의 의류/화장품이 식품으로 들어오지 않게 차단
                if _NON_FOOD_CHECK.search(combined_text) or not _FOOD_CATEGORY_CHECK.search(combined_text):
                    continue
            p_url = f"https://www.29cm.co.kr/products/{item_no}"
            brand = (it.get("frontBrandNameKor") or it.get("frontBrandNameEng") or "").strip() or None
            img = (it.get("imageUrl") or "").strip()
            if img and img.startswith("//"):
                img = "https:" + img
            elif img and not img.startswith("http"):
                img = "https://img.29cm.co.kr" + (img if img.startswith("/") else "/" + img)
            results.append({
                "source": "homepage_29cm_co_kr",
                "source_listing_id": hashlib.sha256(p_url.encode()).hexdigest()[:40],
                "variant_key": "default",
                "name": name[:500],
                "price": str(int(float(price))),
                "currency": "KRW",
                "condition": "unknown",
                "availability": "available",
                "url": p_url,
                "brand": brand,
                "image_url": img if img and img.startswith("http") else None,
            })
            if len(results) >= limit:
                break
    except Exception as e:
        log.warning("29CM 실시간 검색 실패 (%s): %s", keyword, e)
    return results


def _search_joongna(keyword: str, limit: int = 3) -> list[dict]:
    """중고나라 검색 결과에서 상품 상세 JSON-LD를 파싱해 가져온다(중고 포함 설정이 켜진 경우)."""
    q = urllib.parse.quote(keyword)
    search_url = f"https://web.joongna.com/search/{q}"
    req = urllib.request.Request(search_url, headers={"User-Agent": UA})
    results: list[dict] = []
    try:
        with urllib.request.urlopen(req, timeout=4) as r:
            html = r.read().decode("utf-8", errors="ignore")
        paths = list(dict.fromkeys(re.findall(r'href="(/product/\d+)"', html)))[:limit]
        for path in paths:
            p_url = "https://web.joongna.com" + path
            try:
                preq = urllib.request.Request(p_url, headers={"User-Agent": UA})
                with urllib.request.urlopen(preq, timeout=3) as pr:
                    phtml = pr.read().decode("utf-8", errors="ignore")
                for m in re.finditer(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', phtml, re.S):
                    d = json.loads(m.group(1))
                    if isinstance(d, dict) and d.get("@type") == "Product":
                        name = (d.get("name") or "").strip()
                        offers = d.get("offers")
                        offers = offers[0] if isinstance(offers, list) and offers else (offers if isinstance(offers, dict) else {})
                        price = offers.get("price")
                        if not name or not price:
                            continue
                        brand = d.get("brand")
                        brand_name = brand.get("name") if isinstance(brand, dict) else (str(brand) if brand else None)
                        img = d.get("image")
                        img_url = img[0] if isinstance(img, list) and img else (img if isinstance(img, str) else None)
                        results.append({
                            "source": "homepage_web_joongna_com",
                            "source_listing_id": hashlib.sha256(p_url.encode()).hexdigest()[:40],
                            "variant_key": "default",
                            "name": name[:500],
                            "price": str(int(float(str(price).replace(",", "")))),
                            "currency": "KRW",
                            "condition": "used",
                            "availability": "available",
                            "url": p_url,
                            "brand": brand_name,
                            "image_url": img_url if img_url and img_url.startswith("http") else None,
                        })
                        break
            except Exception:
                continue
    except Exception as e:
        log.warning("중고나라 실시간 검색 실패 (%s): %s", keyword, e)
    return results


def _post(url: str, body: dict, token: str) -> int:
    req = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # 환경 프록시로 토큰이 새지 않게
    try:
        with opener.open(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def deliver(items: list[dict], domain: str, post=_post) -> list[dict]:
    """찾은 상품을 수집기와 같은 백엔드 수집 API(Observation v2)로 보낸다. DB에 직접 쓰지 않는다.
    URL 허용 목록·중복 제거·검증은 백엔드가 맡고, 식품 성분은 비워 두어 알레르기 사용자에게는
    '성분 정보 없음'으로 제외된다(상품명을 성분으로 넣으면 안전 확인 없이 통과했다). -> 받아들여진 상품."""
    base = os.getenv("COLLECTOR_BACKEND_BASE_URL", "").strip().rstrip("/")
    token = os.getenv("KKULPICK_BACKEND_TOKEN", "").strip()
    if not base or len(token) < 32:
        log.warning("실시간 폴백: COLLECTOR_BACKEND_BASE_URL/KKULPICK_BACKEND_TOKEN 미설정이라 적재하지 않음")
        return []
    runs: dict[str, str] = {}
    accepted = []
    for it in items:
        if domain == "food" and it["condition"] == "used":
            continue  # 백엔드가 중고 식품을 받지 않는다
        observed_at = datetime.now(UTC).isoformat()
        obs = {
            "schema_version": 2, "source": it["source"], "observed_at": observed_at, "result": "success",
            "selected_domain": domain, "source_listing_id": it["source_listing_id"],
            "variant_key": it["variant_key"], "condition": it["condition"], "name": it["name"],
            "price": it["price"], "currency": it["currency"], "availability": it["availability"], "url": it["url"],
            "field_presence": ["name", "price", "currency", "availability", "url"],
            "observation_key": f"live:{it['source_listing_id']}:{observed_at}"[:180],
        }
        run = runs.setdefault(it["source"], str(uuid.uuid4()))
        if post(f"{base}/internal/v2/crawl-runs/{run}/observations", obs, token) not in (200, 201):
            continue
        accepted.append(it)
        profile = {k: it[k] for k in ("brand", "image_url") if it.get(k)}
        if profile:  # 이미지 호스트가 허용 목록 밖이면 422지만 상품 자체는 이미 들어갔다
            post(f"{base}/internal/v2/crawl-runs/{run}/extensions", {
                "schema_version": "listing-extension-v1", "source": it["source"],
                "source_listing_id": it["source_listing_id"], "variant_key": it["variant_key"],
                "observation_key": obs["observation_key"] + ":profile", "observed_at": observed_at,
                "matching_profile": profile}, token)
    return accepted


def discover_and_ingest(domain: str, query: str, include_used: bool,
                        catalog: PgCatalog, index: PgVectorIndex, embedder) -> list[str]:
    """외부 쇼핑몰을 실시간 검색해 신규 상품을 DB 및 벡터 인덱스에 적재하고 product_id 목록을 돌려준다."""
    keywords = extract_search_keywords(query)
    if not keywords:
        return []
    log.info("DB 추천 0건 → AI 실시간 검색 폴백 실행 (query=%r, keywords=%r)", query, keywords)

    discovered: list[dict] = []
    seen_urls: set[str] = set()
    core_words = [w.lower() for w in name_keywords(query) if w.lower() not in _MODIFIER_ONLY]

    def _matches_core(item_name: str) -> bool:
        """수식어('무가당', '제로')만 겹치고 핵심 품목('땅콩버터', '초콜릿')이 없는 무관 상품은 제외한다."""
        if not core_words:
            return True
        low_name = item_name.lower().replace(" ", "")
        return any(cw.replace(" ", "") in low_name for cw in core_words)

    for kw in keywords[:3]:
        # 식품은 식품·생필품 풀(홈앤쇼핑)을 먼저 찾고, 일반 상품은 29CM·홈앤쇼핑을 함께 찾는다.
        sources = (
            (_search_hnsmall(kw, limit=5, domain=domain), _search_29cm(kw, limit=3, domain=domain))
            if domain == "food"
            else (_search_29cm(kw, limit=4, domain=domain), _search_hnsmall(kw, limit=4, domain=domain))
        )
        for batch in sources:
            for item in batch:
                if item["url"] not in seen_urls and _matches_core(item["name"]):
                    seen_urls.add(item["url"])
                    discovered.append(item)
        if include_used and domain == "product":
            for item in _search_joongna(kw, limit=2):
                if item["url"] not in seen_urls and _matches_core(item["name"]):
                    seen_urls.add(item["url"])
                    discovered.append(item)
        if len(discovered) >= 6:
            break

    if not discovered:
        return []

    ingested_pids = [join_product_id(it["source"], it["source_listing_id"], it["variant_key"])
                     for it in deliver(discovered, domain)]
    products = list(catalog.get_many(ingested_pids).values())
    if products:
        vecs = embedder.embed_documents([document_text(p) for p in products])
        index.upsert([(p.product_id, v) for p, v in zip(products, vecs)])
    return ingested_pids
