import json

from services.recommendation import cli
from services.recommendation.adapters.offers_api import fetch_offers, observation_to_product, offer_to_product
from services.recommendation.adapters.local import JsonProfiles
from services.recommendation.contracts import UserProfile

OBS = {"schema_version": 2, "source": "little_bird_electronics", "observed_at": "2026-11-14T15:18:41+00:00",
       "result": "success", "selected_domain": "product", "source_listing_id": "header-2x5", "variant_key": "AF-5327",
       "condition": "new", "name": "Socket Header", "price": "1.1", "currency": "AUD", "availability": "available",
       "url": "https://example.com/p", "field_presence": ["name", "price", "currency", "availability", "url"],
       "observation_key": "jsonld:abc"}


def test_observation_maps_without_ingredients():
    p = observation_to_product(OBS)
    assert p.product_id == "little_bird_electronics:header-2x5#AF-5327"
    assert (p.price, p.currency, p.url, p.category) == ("1.1", "AUD", "https://example.com/p", "product")
    assert p.ingredients_raw is None


def test_observation_with_future_ingredient_field_is_used():
    p = observation_to_product({**OBS, "selected_domain": "food", "ingredients_raw": "밀가루(밀), 버터(우유)"})
    assert p.ingredients_raw == "밀가루(밀), 버터(우유)"


def test_fetch_offers_follows_cursor():
    pages = {None: {"items": [{"id": 1}], "next_cursor": "c1"}, "c1": {"items": [{"id": 2}], "next_cursor": None}}
    seen = []

    def opener(url):
        seen.append(url)
        cur = url.split("after=")[1] if "after=" in url else None
        return pages[cur]

    assert [x["id"] for x in fetch_offers("http://api", "food", opener=opener)] == [1, 2]
    assert "selected_domain=food" in seen[0]


def test_offer_maps():
    p = offer_to_product({"offer_id": "u", "name": "쌀과자", "source": "demo", "variant_key": "",
                          "price": "2800.0000", "currency": "KRW", "current_url": "https://x/y",
                          "source_listing_id": "r1", "price_observed_at": "2026-11-15T00:00:00Z"}, "food")
    assert p.product_id == "demo:r1" and p.price == "2800.0000" and p.category == "food"


def test_imported_products_without_ingredients_are_not_recommended_to_allergic_users(tmp_path, capsys):
    f = tmp_path / "obs.json"
    f.write_text(json.dumps([OBS, {**OBS, "result": "error"}]), encoding="utf-8")
    assert cli.main(["--data", str(tmp_path), "import-observations", str(f)]) == 0
    assert "저장 1건" in capsys.readouterr().out
    JsonProfiles(tmp_path).save(UserProfile("u-milk", allergens=["milk"]))
    JsonProfiles(tmp_path).save(UserProfile("u-none"))
    cli.main(["--data", str(tmp_path), "--ranker", "rule", "recommend", "--user", "u-milk", "--query", "header"])
    assert json.loads(capsys.readouterr().out)["picks"] == []
    cli.main(["--data", str(tmp_path), "--ranker", "rule", "recommend", "--user", "u-none", "--query", "header"])
    assert len(json.loads(capsys.readouterr().out)["picks"]) == 1
