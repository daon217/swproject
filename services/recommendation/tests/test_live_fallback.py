from services.api.kkulpick.models import Observation
from services.recommendation.allergens import assess
from services.recommendation.contracts import CollectedProduct, UserProfile
from services.recommendation.live_fallback import deliver

ITEM = {"source": "homepage_hnsmall_com", "source_listing_id": "a" * 40, "variant_key": "default",
        "name": "버터쿠키", "price": "5900", "currency": "KRW", "condition": "new", "availability": "available",
        "url": "https://www.hnsmall.com/display/goods.do?goods_code=1", "brand": "꿀", "image_url": None}


def _env(monkeypatch):
    monkeypatch.setenv("COLLECTOR_BACKEND_BASE_URL", "http://api:8000")
    monkeypatch.setenv("KKULPICK_BACKEND_TOKEN", "t" * 32)
    monkeypatch.setenv("CATALOG_URL_HOSTS", "www.hnsmall.com")


def test_delivers_backend_valid_observation_without_ingredients(monkeypatch):
    _env(monkeypatch)
    sent = []
    accepted = deliver([ITEM], "food", post=lambda url, body, token: sent.append((url, body)) or 201)
    assert accepted == [ITEM]
    url, body = sent[0]
    assert url.startswith("http://api:8000/internal/v2/crawl-runs/") and url.endswith("/observations")
    Observation.model_validate(body)  # 백엔드가 받는 형식 그대로
    assert not any("ingredient" in k or "allergen" in k for k in body)
    assert sent[1][1]["matching_profile"] == {"brand": "꿀"}


def test_unknown_ingredients_stay_excluded_for_allergic_user():
    # 백엔드가 만든 식품 행에는 성분이 없다 -> 알레르기 사용자에게 '확인 불가'로 제외돼야 한다.
    food = CollectedProduct.from_dict({k: ITEM[k] for k in ("source", "source_listing_id", "name")})
    assert not assess(food, UserProfile("u", allergens=["milk"])).safe


def test_rejected_or_unconfigured_delivery_is_not_used(monkeypatch):
    _env(monkeypatch)
    assert deliver([ITEM], "food", post=lambda *a: 422) == []
    assert deliver([ITEM | {"condition": "used"}], "food", post=lambda *a: 201) == []
    monkeypatch.delenv("KKULPICK_BACKEND_TOKEN")
    assert deliver([ITEM], "food", post=lambda *a: 201) == []
