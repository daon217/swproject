from services.recommendation.allergens import focus_query
from services.recommendation.contracts import Candidate, CollectedProduct, UserProfile
from services.recommendation.pipeline import Recommender


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


class Fake:
    """카탈로그·인덱스·임베더 겸용. 임베더가 받은 검색 문장을 기록한다."""
    def __init__(self, rows):
        self.items = {p.product_id: p for p, _ in rows}
        self.scores = {p.product_id: s for p, s in rows}

    def get_many(self, ids):
        return {i: self.items[i] for i in ids if i in self.items}

    def search(self, vector, limit):
        return [Candidate(i, s) for i, s in sorted(self.scores.items(), key=lambda x: -x[1])][:limit]

    def embed_query(self, text):
        self.text = text
        return [0.0]


def test_shrimp_allergy_on_shrimp_tempura_searches_other_tempura():
    seen = {}

    class Spy:  # LLM 랭커 자리: 받은 검색어를 기록하고 후보 순서대로 고름
        name = "spy"
        def rank(self, profile, query, items, top_k):
            seen["q"] = query
            return [(p.product_id, "") for p, _ in items][:top_k]

    def food(i, name, score, **evidence):
        return CollectedProduct.from_dict({"source": "t", "source_listing_id": str(i), "name": name, **evidence}), score

    fake = Fake([food(1, "비비고 바삭 새우튀김 300g", 0.9, allergens_declared=["shrimp"]),
                 food(2, "사옹원 오징어튀김 500g", 0.6, ingredients_raw="오징어, 밀가루")])
    r = Recommender(fake, fake, fake, Spy()).recommend(UserProfile("u", allergens=["shrimp"]), "비비고 바삭 새우튀김 300g")
    assert fake.text == "비비고 바삭 튀김 300g"                          # 검색은 알레르기 단어를 뺀 말로
    assert seen["q"] == "비비고 바삭 새우튀김 300g (새우 없는 대체품)"   # LLM 에는 원래 이름 + 대체품
    assert [p.name for p in r.picks] == ["사옹원 오징어튀김 500g"]
    assert r.query == "비비고 바삭 새우튀김 300g"
