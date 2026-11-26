from datetime import UTC, datetime

import pytest

from services.collector.homepage_crawler.backend import Backend, extension, extensions, observation, source_for

AT = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
ITEM = dict(site="올리브영", url="https://www.oliveyoung.co.kr/store/goods/1", name="수분 크림", price=12000,
            orig_price=12000, orig_currency="KRW", currency="KRW", availability="https://schema.org/InStock",
            kind="상품", channel="일반", brand="꿀픽", image="https://img.example.test/1.jpg", category="스킨케어")
FOOD = dict(ITEM, url="https://www.kurly.com/goods/2", name="땅콩 쿠키", kind="식품", allergen_status="read",
            ingredient_text="밀가루, 땅콩, 아몬드", allergen_text="땅콩, 밀, 아몬드 함유",
            allergens_contains=["땅콩", "밀", "견과류*"], allergens_trace=["우유"])


def test_observation_matches_backend_contract():
    obs, reason = observation(ITEM, AT)
    assert reason is None
    assert obs["source"] == "homepage_oliveyoung_co_kr" and obs["selected_domain"] == "product"
    assert obs["condition"] == "unknown" and obs["availability"] == "available"
    assert obs["price"] == "12000" and obs["currency"] == "KRW"
    assert sorted(obs["field_presence"]) == ["availability", "currency", "name", "price", "url"]
    # Same body (retry) -> same key; a later crawl or a changed price -> new key (no 409 on the next cycle)
    assert observation(ITEM, AT)[0]["observation_key"] == obs["observation_key"]
    assert observation(dict(ITEM, price=13000, orig_price=13000), AT)[0]["observation_key"] != obs["observation_key"]
    assert observation(ITEM, AT.replace(hour=4))[0]["observation_key"] != obs["observation_key"]


def test_overseas_keeps_original_currency_and_used_food_is_skipped():
    obs, _ = observation(dict(ITEM, url="https://www.amazon.com/dp/X", orig_price=19.99, orig_currency="USD",
                              price=27986, channel="직구"), AT)
    assert (obs["price"], obs["currency"]) == ("19.99", "USD")
    assert observation(dict(FOOD, channel="중고"), AT) == (None, "used_food_unsupported")
    assert observation(dict(ITEM, price=None, orig_price=None), AT) == (None, "no_single_price")
    assert observation(dict(ITEM, availability="https://schema.org/OutOfStock"), AT)[0]["availability"] == "out_of_stock"


def test_food_extension_sends_codes_and_keeps_group_words_as_text():
    obs, _ = observation(FOOD, AT)
    ext = extension(FOOD, obs)
    food = ext["food_evidence"]
    assert food["allergens_declared"] == ["peanut", "wheat"]  # 견과류(묶음)는 코드로 보내지 않는다
    assert "아몬드" in food["allergen_notice_raw"]            # 원문은 그대로 -> 백엔드가 글자로 대조
    assert food["cross_contact_raw"] == "우유" and ext["matching_profile"]["brand"] == "꿀픽"
    unread = dict(FOOD, allergen_status="image_only")
    assert "food_evidence" not in extension(unread, observation(unread, AT)[0])


class Response:
    def __init__(self, code, state="applied"):
        self.status_code, self._state = code, state

    def json(self):
        return {"state": self._state}


class Session:
    def __init__(self, code=201):
        self.code, self.calls = code, []

    def post(self, url, json, headers):
        self.calls.append((url, json, headers))
        return Response(self.code)


def test_deliver_posts_observation_then_extension_with_one_run_per_source():
    session = Session()
    counts = Backend("http://api:8000", "t" * 32, session).deliver([ITEM, FOOD, dict(ITEM, price=None, orig_price=None)], AT)
    assert counts == {"applied": 2, "extension_profile:applied": 2, "extension_food:applied": 1,
                      "skipped:no_single_price": 1}
    paths = [c[0] for c in session.calls]
    assert paths[0].endswith("/observations") and paths[1].endswith("/extensions")
    assert paths[0].split("/")[-2] != paths[2].split("/")[-2]  # 수집처가 다르면 실행 ID도 다르다
    assert session.calls[0][2]["Authorization"] == "Bearer " + "t" * 32


def test_food_evidence_is_sent_apart_from_profile():
    # #76: 이미지가 거부돼도 알레르기 근거가 함께 버려지지 않도록 두 요청으로 나눈다(식품 근거 먼저)
    obs, _ = observation(FOOD, AT)
    food, profile = extensions(FOOD, obs)
    assert "food_evidence" in food and "matching_profile" not in food
    assert "matching_profile" in profile and "food_evidence" not in profile
    assert food["observation_key"] != profile["observation_key"]
    assert extensions(dict(ITEM, brand=None, image=None, category=None), observation(ITEM, AT)[0]) == []


def test_rejected_token_stops_and_settings_are_validated(monkeypatch):
    with pytest.raises(PermissionError):
        Backend("http://api:8000", "t" * 32, Session(401)).deliver([ITEM], AT)
    with pytest.raises(ValueError):
        Backend("http://api:8000", "short", Session())
    monkeypatch.setenv("COLLECTOR_BACKEND_BASE_URL", "http://api:8000/internal")
    with pytest.raises(ValueError):
        Backend(token="t" * 32)
    assert source_for("https://zigzag.kr/catalog/products/1") == "homepage_zigzag_kr"
