from services.recommendation.allergens import focus_query


def test_focus_on_rest_of_query():
    assert focus_query("새우튀김", ["shrimp"]) == ("튀김", ["새우"])
    assert focus_query("[비비고] 바삭 새우튀김 300g", ["shrimp"]) == ("[비비고] 바삭 튀김 300g", ["새우"])
    assert focus_query("100% 무가당 땅콩버터", ["peanut"]) == ("100% 무가당 버터", ["땅콩"])
    assert focus_query("쉬림프 튀김", ["shrimp"]) == ("튀김", ["새우"])


def test_keeps_query_when_unsafe_to_strip():
    assert focus_query("새우깡 90g", ["shrimp"]) == ("새우깡 90g", [])     # '깡' 만 남으면 뜻이 바뀜
    assert focus_query("땅콩버터", ["milk"]) == ("땅콩버터", [])           # 땅콩버터의 버터는 우유 아님
    assert focus_query("새우튀김", []) == ("새우튀김", [])
    assert focus_query("새우", ["shrimp"]) == ("", ["새우"])               # 남는 말이 없으면 빈 검색어 -> 추천 안 함


def test_shrimp_allergy_on_shrimp_tempura_recommends_other_tempura():
    from services.recommendation.contracts import UserProfile
    from services.recommendation.pipeline import Recommender
    from services.recommendation.tests.test_food_types import Fake, food

    seen = {}

    class Spy:  # LLM 랭커 자리: 받은 검색어를 기록하고 후보 순서대로 고름
        name = "spy"
        def rank(self, profile, query, items, top_k):
            seen["q"] = query
            return [(p.product_id, "") for p, _ in items][:top_k]

    rows = [food(1, "비비고 바삭 새우튀김 300g", 0.9, allergens_declared=["shrimp"]),
            food(2, "사옹원 오징어튀김 500g", 0.6, ingredients_raw="오징어, 밀가루"),
            food(3, "[태우한우] 1+ 한우 채끝", 0.6, allergens_declared=["beef"])]
    fake = Fake(rows)
    r = Recommender(fake, fake, fake, Spy()).recommend(
        UserProfile("u", allergens=["shrimp"]), "비비고 바삭 새우튀김 300g", min_score=0.5, score_margin=0.4, domain="food")
    assert [p.name for p in r.picks] == ["사옹원 오징어튀김 500g"]
    assert r.query == "비비고 바삭 새우튀김 300g"            # 결과에는 원래 검색어
    assert seen["q"] == "비비고 바삭 새우튀김 300g (새우 없는 대체품)"
    assert any("새우 알레르기" in n for n in r.notes)
