"""최적화된 백엔드 전송기 (SHA-256 콘텐츠 해시 기반 중복 전송 억제).

주요 기능:
- 직전 전송 성공한 (source, source_listing_id)의 핵심 본문 SHA-256 해시를 캐싱하여,
  가격/재고/상품명 등 내용 변동이 없는 상품은 불필요한 Observation + Extension POST 전송을 생략(unchanged_skipped).
"""
import hashlib
import os
import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

SUPPORTED_CURRENCIES = set(os.getenv("CATALOG_CURRENCIES", "KRW,USD,AUD,EUR,INR,GBP,JPY,CNY").split(","))
AVAILABILITY = {
    "instock": "available", "limitedavailability": "available", "onlineonly": "available",
    "instoreonly": "available", "preorder": "available", "presale": "available",
    "outofstock": "out_of_stock", "soldout": "out_of_stock", "backorder": "out_of_stock",
    "discontinued": "ended",
}
CODES = {
    "알류": "egg", "우유": "milk", "메밀": "buckwheat", "땅콩": "peanut", "대두": "soy",
    "밀": "wheat", "고등어": "mackerel", "게": "crab", "새우": "shrimp", "돼지고기": "pork",
    "복숭아": "peach", "토마토": "tomato", "아황산류": "sulfites", "호두": "walnut",
    "닭고기": "chicken", "쇠고기": "beef", "오징어": "squid", "조개류": "shellfish",
    "잣": "pine_nut", "참깨*": "sesame",
}
GROUPS = {"견과류*", "생선*"}


def source_for(url):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    return ("homepage_" + re.sub(r"[^a-z0-9]+", "_", host)).strip("_")[:64]


def _availability(value):
    if not value:
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
    cur = (p.get("orig_currency") or p.get("currency") or "KRW").upper()
    if cur in SUPPORTED_CURRENCIES and p.get("orig_price") is not None:
        return _money(p["orig_price"]), cur
    if p.get("price") is not None:
        return _money(p["price"]), "KRW"
    return None, None


def observation(p, observed_at=None):
    domain = "food" if p.get("kind") == "식품" else "product"
    condition = "used" if p.get("channel") == "중고" else "unknown"
    if domain == "food" and condition == "used":
        return None, "used_food_unsupported"
    if not p.get("name") or not p.get("url"):
        return None, "missing_name_or_url"
    price, currency = _price(p)
    if price is None:
        return None, "no_single_price"
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
        "field_presence": ["name", "price", "currency", "availability", "url"],
    }
    digest = hashlib.sha256(repr(sorted(body.items())).encode()).hexdigest()
    body["observation_key"] = f"{body['source']}:{body['source_listing_id']}:{digest[:16]}"[:180]
    return body, None


def _codes(names):
    out = []
    for n in names or []:
        code = CODES.get(n)
        if code and n not in GROUPS and code not in out:
            out.append(code)
    return out


def extension(p, obs):
    """식품 성분·알레르기(성분표를 읽은 경우), 브랜드·대표 이미지 -> 리스팅 확장 하나. 보낼 내용이 없으면 None."""
    body = {
        "schema_version": "listing-extension-v1",
        "source": obs["source"],
        "source_listing_id": obs["source_listing_id"],
        "variant_key": "default",
        "observation_key": obs["observation_key"] + ":ext",
        "observed_at": obs["observed_at"],
    }
    profile = {}
    brand_val = str(p.get("brand") or "").strip()[:200]
    if brand_val:
        profile["brand"] = brand_val
    img_val = str(p.get("image") or "").strip()
    if img_val.startswith("https://"):
        profile["image_url"] = img_val
    cat_val = str(p.get("category") or "").strip()[:200]
    if cat_val:
        profile["category"] = cat_val
    if profile:
        body["matching_profile"] = profile
    if obs["selected_domain"] == "food" and p.get("allergen_status") in ("read", "read_empty"):
        food = {"evidence_status": "reported"}
        ing_val = str(p.get("ingredient_text") or "").strip()[:4000]
        if ing_val:
            food["ingredients_raw"] = ing_val
        alg_val = str(p.get("allergen_text") or "").strip()[:1000]
        if alg_val:
            food["allergen_notice_raw"] = alg_val
        if p.get("allergens_trace"):
            trace_val = ", ".join(n.rstrip("*") for n in p["allergens_trace"]).strip()[:1000]
            if trace_val:
                food["cross_contact_raw"] = trace_val
        food["allergens_declared"] = _codes(p.get("allergens_contains"))[:32]
        body["food_evidence"] = food
    return body if ("matching_profile" in body or "food_evidence" in body) else None


def extensions(p, obs):
    out = []
    ext = extension(p, obs)
    if ext and "food_evidence" in ext:
        out.append({k: v for k, v in ext.items() if k != "matching_profile"} | {"observation_key": obs["observation_key"] + ":food"})
    if ext and "matching_profile" in ext:
        out.append({k: v for k, v in ext.items() if k != "food_evidence"} | {"observation_key": obs["observation_key"] + ":profile"})
    return out


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


class OptimizedBackend:
    """SHA-256 콘텐츠 해시 비교로 미변경 상품 중복 POST를 억제하는 백엔드 전송기."""

    def __init__(self, base_url=None, token=None, session=None, *, enable_dedup=True):
        self.base = base_url.rstrip("/") if base_url is not None else _base_url()
        token = token if token is not None else _token()
        if len(token) < 16:
            raise ValueError("backend token missing")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.enable_dedup = enable_dedup
        self._sent_signatures: dict[tuple[str, str], str] = {}
        if session is None:
            import requests
            session = requests.Session()
            session.trust_env = False
            self._kw = {"timeout": 15, "allow_redirects": False}
        else:
            self._kw = {}
        self.session = session

    @staticmethod
    def _content_signature(obs):
        core = {k: v for k, v in obs.items() if k not in ("observed_at", "observation_key")}
        return hashlib.sha256(repr(sorted(core.items())).encode()).hexdigest()

    def _post(self, path, body):
        r = self.session.post(self.base + path, json=body, headers=self.headers, **self._kw)
        if r.status_code in (200, 201):
            return r.json().get("state") or "applied"
        if r.status_code == 401:
            raise PermissionError("backend rejected the collector token")
        return f"http_{r.status_code}"

    def deliver(self, products, observed_at=None):
        counts = {}
        runs = {}
        for p in products:
            obs, reason = observation(p, observed_at)
            if obs is None:
                counts["skipped:" + reason] = counts.get("skipped:" + reason, 0) + 1
                continue
            ident = (obs["source"], obs["source_listing_id"])
            sig = self._content_signature(obs)
            if self.enable_dedup and self._sent_signatures.get(ident) == sig:
                counts["unchanged_skipped"] = counts.get("unchanged_skipped", 0) + 1
                continue
            run = runs.setdefault(obs["source"], str(uuid.uuid4()))
            state = self._post(f"/internal/v2/crawl-runs/{run}/observations", obs)
            counts[state] = counts.get(state, 0) + 1
            if state in ("applied", "recorded"):
                self._sent_signatures[ident] = sig
            for ext in (extensions(p, obs) if state in ("applied", "recorded") else []):
                kind = "food" if "food_evidence" in ext else "profile"
                ext_state = self._post(f"/internal/v2/crawl-runs/{run}/extensions", ext)
                counts[f"extension_{kind}:" + ext_state] = counts.get(f"extension_{kind}:" + ext_state, 0) + 1
        return counts


# 기존 homepage_crawler/backend.py의 Backend 클래스명과 100% 드롭인 호환 별칭
Backend = OptimizedBackend
