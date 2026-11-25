"""백엔드(소병선) API 와 수집기(최준서) Observation v2 를 추천 계약으로 바꾸는 어댑터.

- fetch_offers(): `GET {API_BASE}/v2/offers` 를 끝까지 넘겨가며 읽음 (인증 없음, 읽기 전용).
- observation_to_product(): 수집기 Observation v2 한 건 -> CollectedProduct.

지금 수집 데이터에는 성분 필드가 없어서, 들어온 상품은 저장·검색은 되지만
알레르기가 있는 사용자에게는 추천되지 않습니다 (성분 정보 없음 = 안전 확인 불가).
수집기가 성분을 보내기 시작하면 아래 _INGREDIENT_KEYS 에 필드 이름만 맞추면 됩니다.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Iterator

from ..contracts import ContractError, CollectedProduct

# 수집기/백엔드가 성분을 보내게 되면 쓸 필드 이름 후보 (Observation 에는 아직 없음).
_INGREDIENT_KEYS = {"ingredients_raw": ("ingredients_raw", "raw_ingredients"),
                    "allergen_notice_raw": ("allergen_notice_raw", "allergen_notice"),
                    "cross_contact_raw": ("cross_contact_raw",)}
_SOURCE_OK = re.compile(r"[^a-z0-9_-]")


def _source_code(s: str) -> str:
    code = _SOURCE_OK.sub("_", s.strip().lower())[:64]
    return code if code[:1].isalpha() else f"s_{code}"[:64]


def _common(d: dict[str, Any], *, source: str, listing: str, url: str | None,
            collected_at: str | None, category: str | None, checked_at: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"source": _source_code(source), "source_listing_id": listing,
                           "name": d["name"], "category": d.get("category") or category,
                           "brand": d.get("brand"), "image_url": d.get("image_url"),
                           "description": d.get("description"),
                           "condition": d.get("condition"), "availability": d.get("availability"),
                           "checked_at": checked_at}
    if isinstance(d.get("ingredients"), list) and d["ingredients"]:
        out["ingredients"] = [str(x) for x in d["ingredients"] if str(x).strip()]
    if d.get("price") is not None and d.get("currency"):
        out["price"], out["currency"] = str(d["price"]), d["currency"]
    if url:
        out["url"] = url
    if collected_at:
        out["collected_at"] = collected_at
    for target, keys in _INGREDIENT_KEYS.items():
        for k in keys:
            if d.get(k):
                out[target] = d[k]
                break
    return {k: v for k, v in out.items() if v is not None}


def observation_to_product(obs: dict[str, Any]) -> CollectedProduct:
    """수집기 Observation v2 -> CollectedProduct. variant 마다 다른 상품으로 봄."""
    if obs.get("result") != "success" or not obs.get("name"):
        raise ContractError(["성공한 관측이 아니거나 name 없음"])
    listing = obs["source_listing_id"]
    if obs.get("variant_key"):
        listing = f"{listing}#{obs['variant_key']}"
    return CollectedProduct.from_dict(_common(
        obs, source=obs["source"], listing=listing, url=obs.get("url"),
        collected_at=obs.get("observed_at"), category=obs.get("selected_domain"),
        checked_at=obs.get("observed_at") if obs.get("availability") else None))


def offer_to_product(offer: dict[str, Any], domain: str) -> CollectedProduct:
    """`GET /v2/offers` 응답의 items[] 한 건 -> CollectedProduct."""
    listing = offer["source_listing_id"]
    if offer.get("variant_key"):
        listing = f"{listing}#{offer['variant_key']}"
    return CollectedProduct.from_dict(_common(
        offer, source=offer["source"], listing=listing, url=offer.get("current_url"),
        collected_at=offer.get("price_observed_at") or offer.get("last_seen_at"), category=domain,
        checked_at=offer.get("last_checked_at")))


def fetch_offers(api_base: str, domain: str = "food", *, page_size: int = 100,
                 max_pages: int = 1000, timeout: float = 15.0, opener=None) -> Iterator[dict[str, Any]]:
    """`/v2/offers` 를 next_cursor 따라 끝까지 읽음. opener 는 테스트용 (url -> dict)."""
    if domain not in ("product", "food"):
        raise ValueError("domain 은 product | food")
    base = api_base.rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError("API_BASE 는 http(s):// 로 시작해야 함")
    fetch = opener or (lambda u: json.loads(urllib.request.urlopen(u, timeout=timeout).read()))
    after = None
    for _ in range(max_pages):
        # 중고·품절도 받아서 추천 쪽에서 판단 (API 기본값은 new + available 만)
        q = {"selected_domain": domain, "limit": page_size, "condition": "all", "availability": "all"}
        if after:
            q["after"] = after
        page = fetch(f"{base}/v2/offers?{urllib.parse.urlencode(q)}")
        yield from page.get("items", [])
        after = page.get("next_cursor")
        if not after:
            return
    raise RuntimeError(f"{max_pages} 페이지를 넘음: next_cursor 가 끝나지 않음")
