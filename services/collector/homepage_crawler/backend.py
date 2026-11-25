"""홈페이지 크롤러 결과를 꿀픽 백엔드 수집 API로 보낸다.

Supabase에 직접 쓰는 대신(또는 함께) 백엔드 계약을 그대로 따른다:
- 상품: POST /internal/v2/crawl-runs/{run_id}/observations  (Observation v2)
- 식품 성분·알레르기, 브랜드·이미지: POST /internal/v2/crawl-runs/{run_id}/extensions

설정(환경변수, 값은 로그·Git에 남기지 않는다)
- COLLECTOR_BACKEND_BASE_URL: 예) http://api:8000  (scheme+host+port만, 경로 없음)
- KKULPICK_BACKEND_TOKEN_FILE 또는 KKULPICK_BACKEND_TOKEN: 백엔드 COLLECTOR_TOKEN과 같은 값

백엔드 쪽 준비: 수집할 쇼핑몰 도메인을 CATALOG_URL_HOSTS에 넣어야 한다(없으면 422 URL host).
"""
import hashlib
import os
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from services.collector.food_evidence.extract import CODES, GROUPS

SUPPORTED_CURRENCIES = set(os.getenv("CATALOG_CURRENCIES", "KRW,USD,AUD,EUR,INR,GBP,JPY,CNY").split(","))
# schema.org availability 마지막 단어 -> 백엔드 판매 상태
AVAILABILITY = {
    "instock": "available", "limitedavailability": "available", "onlineonly": "available",
    "instoreonly": "available", "preorder": "available", "presale": "available",
    "outofstock": "out_of_stock", "soldout": "out_of_stock", "backorder": "out_of_stock",
    "discontinued": "ended",
}


def source_for(url):
    """수집처 이름: 도메인 기준(백엔드 규칙 ^[a-z][a-z0-9_-]{0,63}$). 한 실행(run)은 수집처 하나만 담는다."""
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return ("homepage_" + re.sub(r"[^a-z0-9]+", "_", host)).strip("_")[:64]


def _availability(value):
    if not value:
        # 상품 페이지가 열리고 가격이 보이면 판매 중으로 본다(JSON-LD/OG에 상태가 없는 쇼핑몰이 많다).
        return "available"
    return AVAILABILITY.get(str(value).rstrip("/").rsplit("/", 1)[-1].lower(), "available")


def _money(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not d.is_finite() or d < 0:
        return None
    return str(d.quantize(Decimal("0.0001")).normalize()) if d != d.to_integral() else str(int(d))


def _price(p):
    """원래 통화·원래 가격을 보낸다(해외 상품 구분·해외 포함 설정이 원화가 아닌 통화로 동작). 모르는 통화면 원화 환산값."""
    cur = (p.get("orig_currency") or p.get("currency") or "KRW").upper()
    if cur in SUPPORTED_CURRENCIES and p.get("orig_price") is not None:
        return _money(p["orig_price"]), cur
    if p.get("price") is not None:
        return _money(p["price"]), "KRW"
    return None, None


def observation(p, observed_at=None):
    """크롤러 상품 1건 -> Observation v2. 보낼 수 없으면 (None, 사유)."""
    domain = "food" if p.get("kind") == "식품" else "product"
    condition = "used" if p.get("channel") == "중고" else "unknown"  # 홈페이지는 새 상품이라고 명시하지 않는다
    if domain == "food" and condition == "used":
        return None, "used_food_unsupported"
    if not p.get("name") or not p.get("url"):
        return None, "missing_name_or_url"
    price, currency = _price(p)
    if price is None:
        return None, "no_single_price"  # 가격 범위(AggregateOffer)만 있는 상품은 보내지 않는다
    body = {
        "schema_version": 2,
        "source": source_for(p["url"]),
        "observed_at": (observed_at or datetime.now(UTC)).isoformat(),
        "result": "success",
        "selected_domain": domain,
        "source_listing_id": hashlib.sha256(p["url"].encode()).hexdigest()[:40],
        "variant_key": "default",
        "condition": condition,
        "name": str(p["name"])[:500],
        "price": price,
        "currency": currency,
        "availability": _availability(p.get("availability")),
        "url": p["url"],
    }
    body["field_presence"] = ["name", "price", "currency", "availability", "url"]
    # 관측마다 새 키(관측 시각 포함). 같은 본문을 다시 보내면(재시도) 같은 키라 백엔드가 중복으로 처리하고,
    # 다음 회차의 같은 상품은 새 관측으로 받아 '변경 없음'으로 기록한다(같은 키에 다른 본문이면 409).
    digest = hashlib.sha256(repr(sorted(body.items())).encode()).hexdigest()
    body["observation_key"] = f"{body['source']}:{body['source_listing_id']}:{digest[:16]}"[:180]
    return body, None


def _codes(names):
    """크롤러 사전의 정규 이름(우유, 참깨* ...) -> 백엔드 코드. 묶음(견과류·생선)은 코드가 없어 빼고 원문으로 판정한다."""
    out = []
    for n in names or []:
        code = CODES.get(n)
        if code and n not in GROUPS and code not in out:
            out.append(code)
    return out


def extension(p, obs):
    """식품 성분·알레르기(성분표를 읽은 경우), 브랜드·대표 이미지 -> 리스팅 확장. 보낼 내용이 없으면 None."""
    body = {
        "schema_version": "listing-extension-v1",
        "source": obs["source"],
        "source_listing_id": obs["source_listing_id"],
        "variant_key": "default",
        "observation_key": obs["observation_key"] + ":ext",
        "observed_at": obs["observed_at"],
    }
    profile = {}
    if p.get("brand"):
        profile["brand"] = str(p["brand"])[:200]
    if p.get("image") and str(p["image"]).startswith(("http://", "https://")):
        profile["image_url"] = p["image"]
    if p.get("category"):
        profile["category"] = str(p["category"])[:200]
    if profile:
        body["matching_profile"] = profile
    if obs["selected_domain"] == "food" and p.get("allergen_status") in ("read", "read_empty"):
        food = {"evidence_status": "reported"}
        if p.get("ingredient_text"):
            food["ingredients_raw"] = str(p["ingredient_text"])[:4000]
        if p.get("allergen_text"):
            food["allergen_notice_raw"] = str(p["allergen_text"])[:1000]
        if p.get("allergens_trace"):
            food["cross_contact_raw"] = ", ".join(n.rstrip("*") for n in p["allergens_trace"])[:1000]
        food["allergens_declared"] = _codes(p.get("allergens_contains"))[:32]
        body["food_evidence"] = food
    return body if ("matching_profile" in body or "food_evidence" in body) else None


def _token():
    path = os.getenv("KKULPICK_BACKEND_TOKEN_FILE")
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return os.getenv("KKULPICK_BACKEND_TOKEN", "").strip()


def _base_url():
    base = os.getenv("COLLECTOR_BACKEND_BASE_URL", "").strip().rstrip("/")
    u = urlparse(base)
    if u.scheme not in ("http", "https") or not u.hostname or u.path or u.query or u.username:
        raise ValueError("COLLECTOR_BACKEND_BASE_URL must be scheme://host[:port] only")
    return base


class Backend:
    """백엔드 전송기. session을 넘기면(테스트) 그대로 쓰고, 아니면 리다이렉트·환경 프록시를 따르지 않는 세션을 만든다."""

    def __init__(self, base_url=None, token=None, session=None):
        self.base = base_url if base_url is not None else _base_url()
        token = token if token is not None else _token()
        if len(token) < 16:
            raise ValueError("backend token missing")
        self.headers = {"Authorization": f"Bearer {token}"}
        if session is None:
            import requests
            session = requests.Session()
            session.trust_env = False
            self._kw = {"timeout": 15, "allow_redirects": False}
        else:
            self._kw = {}
        self.session = session

    def _post(self, path, body):
        r = self.session.post(self.base + path, json=body, headers=self.headers, **self._kw)
        if r.status_code in (200, 201):
            return r.json().get("state") or "applied"
        if r.status_code == 401:
            raise PermissionError("backend rejected the collector token")
        return f"http_{r.status_code}"

    def deliver(self, products, observed_at=None):
        """상품 목록 전송. 수집처(도메인)마다 실행 ID를 따로 쓴다. -> 결과별 개수."""
        counts = {}
        runs = {}
        for p in products:
            obs, reason = observation(p, observed_at)
            if obs is None:
                counts["skipped:" + reason] = counts.get("skipped:" + reason, 0) + 1
                continue
            run = runs.setdefault(obs["source"], str(uuid.uuid4()))
            state = self._post(f"/internal/v2/crawl-runs/{run}/observations", obs)
            counts[state] = counts.get(state, 0) + 1
            ext = extension(p, obs) if state in ("applied", "recorded") else None
            if ext:
                ext_state = self._post(f"/internal/v2/crawl-runs/{run}/extensions", ext)
                counts["extension:" + ext_state] = counts.get("extension:" + ext_state, 0) + 1
        return counts
