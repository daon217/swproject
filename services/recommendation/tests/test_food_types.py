import pytest

from services.recommendation.contracts import Candidate, CollectedProduct, SafetyVerdict, UserProfile
from services.recommendation.food_types import food_type
from services.recommendation.pipeline import Recommender
from services.recommendation.rankers import RuleRanker


@pytest.mark.parametrize("name,kind", [
    ("매일두유 고단백 190ml 24팩", "마시는 우유류"),
    ("아몬드브리즈 오리지널 190ml", "마시는 우유류"),
    ("서울우유 1L", "마시는 우유류"),
    ("[사미헌] 갈비탕", "국·탕·찌개"),          # '갈비'(정육)가 아니라 국·탕
    ("[차려낸] 강릉식 짬뽕순두부찌개", "국·탕·찌개"),  # '두부'가 아니라 국·탕
    ("[종가] 포기김치 4kg", "김치·반찬"),
    ("[태우한우] 1+ 한우 채끝 구이용 200g", "정육"),
    ("무사시 하이 프로틴 피넛 버터 바 90g", "간식바"),  # 땅콩버터가 아니라 바
    ("스키피 땅콩버터 청크 462g", "스프레드·잼"),
    ("레인코스트 크리스프 450g", "과자·간식"),        # '스프'(수프) 아님
    ("츄파춥스 사탕", "과자·간식"),                   # '탕' 아님
    ("빈크런치 프로틴 땅콩버터 오리지널", "스프레드·잼"),  # '오리'(정육) 아님
    ("국산 아카시아 벌꿀 1kg", "꿀·시럽"),
    ("바삭한 왕새우튀김 500g", "튀김·까스"),  # 수산물이 아니라 튀김, 파스타·떡볶이와도 다른 품목
    ("[KF365] 에어프라이어용 생선까스", "튀김·까스"),
    ("[올마레] 춘천 국물 닭갈비 떡볶이", "떡·떡볶이"),
])
def test_food_type(name, kind):
    assert food_type(name) == kind


def test_name_wins_over_category():
    assert food_type("[h541] 치즈오븐파스타 2종(택1)", "델리 > 도시락 > 일반 도시락") == "면"
    assert food_type("이름으로는 모름", "냉장/냉동 식품 > 튀김 > 새우/생선튀김") == "튀김·까스"


def food(i, name, score, **evidence):
    return CollectedProduct.from_dict({"source": "t", "source_listing_id": str(i), "name": name, **evidence}), score


class Fake:
    """벡터 점수를 직접 정하는 카탈로그·인덱스·임베더(실제 DB와 같은 메서드)."""
    def __init__(self, rows):
        self.items = {p.product_id: p for p, _ in rows}
        self.scores = {p.product_id: s for p, s in rows}

    def get_many(self, ids):
        return {i: self.items[i] for i in ids if i in self.items}

    def name_matches(self, keywords, limit, modifiers=()):
        return [i for i, p in self.items.items() if any(k in p.name for k in keywords)][:limit]

    def search(self, vector, limit):
        return [Candidate(i, s) for i, s in sorted(self.scores.items(), key=lambda x: -x[1])][:limit]

    def embed_query(self, text):
        return [0.0]


# 실제 DB에서 재현한 점수: '매일두유'와 무관한 상품이 0.5~0.6, 진짜 비슷한 상품은 대두가 들어 있다.
SOY_MILK_PAGE = [
    food(1, "[태우한우] 1+ 한우 채끝 구이용 200g", 0.57, allergens_declared=["beef"]),
    food(2, "오늘좋은 크래커 통밀 250g", 0.60),
    food(3, "[차려낸] 짬뽕순두부찌개", 0.71, allergens_declared=["soybean"]),
    food(4, "베지밀 검은콩 두유 190ml", 0.55, allergens_declared=["soybean"]),
    food(5, "[종가] 포기김치 4kg", 0.52, allergens_declared=["shrimp"]),
]
SOY = UserProfile("u", allergens=["soy"])


def recommend(rows, profile=SOY, domain="food"):
    fake = Fake(rows)
    return Recommender(fake, fake, fake, RuleRanker()).recommend(
        profile, "매일두유 고단백 190ml 24팩", top_k=8, min_score=0.5, score_margin=0.25, domain=domain)


def test_soy_allergy_on_soy_milk_never_recommends_other_kinds():
    r = recommend(SOY_MILK_PAGE)
    assert r.picks == []  # 예전: 한우 채끝·포기김치
    assert [v.product_id for v in r.excluded] == ["t:4"]  # 같은 품목(두유)만 알레르기로 빠졌다고 기록


def test_llm_picking_nothing_still_shows_same_kind_safe_food():
    class PicksNothing:  # 학교 LLM이 '왕새우튀김과 다르다'며 {"picks": []}를 돌려준 경우
        name = "local"
        def rank(self, *a):
            return []
    rows = [food(1, "[KF365] 에어프라이어용 생선까스", 0.45, allergens_declared=["wheat"]),
            food(2, "[태우한우] 1+ 한우 채끝", 0.6, allergens_declared=["beef"])]
    fake = Fake(rows)
    r = Recommender(fake, fake, fake, PicksNothing()).recommend(
        UserProfile("u", allergens=["shrimp"]), "바삭한 왕새우튀김 500g", min_score=0.5, score_margin=0.25, domain="food")
    assert [p.name for p in r.picks] == ["[KF365] 에어프라이어용 생선까스"] and r.ranker == "rule-fallback"


def test_soy_allergy_gets_safe_substitute_even_below_vector_cutoff():
    almond = food(6, "아몬드브리즈 오리지널 190ml", 0.30, ingredients_raw="정제수, 아몬드, 탄산칼슘")
    r = recommend(SOY_MILK_PAGE + [almond])
    assert [p.name for p in r.picks] == ["아몬드브리즈 오리지널 190ml"]


def test_unknown_kind_falls_back_to_shared_name_word():
    assert food_type("말린 무화과 슬라이스") is None  # 분류표에 없는 품목
    rows = [food(1, "터키산 건조 무화과 1kg", 0.6, ingredients_raw="무화과"), food(2, "한우 채끝", 0.6, allergens_declared=["beef"])]
    fake = Fake(rows)
    r = Recommender(fake, fake, fake, RuleRanker()).recommend(UserProfile("u"), "말린 무화과 슬라이스", min_score=0.5, domain="food")
    assert [p.name for p in r.picks] == ["터키산 건조 무화과 1kg"]


def test_products_keep_previous_behaviour():
    # 상품(노트북·외장하드 등)에는 품목 확인을 적용하지 않는다.
    assert "[태우한우] 1+ 한우 채끝 구이용 200g" in [p.name for p in recommend(SOY_MILK_PAGE, domain=None).picks]


def test_allergy_exclusion_counts_for_screen():
    from services.recommendation.http_service import allergy_exclusions
    excluded = [SafetyVerdict("a", False, ["대두(soy): 알레르기 신고 코드 'soybean'"], ["soy"]),
                SafetyVerdict("b", False, ["성분 정보 없음: 알레르기 안전 확인 불가"], []),
                SafetyVerdict("c", False, ["판매 상태 ended"], [])]
    assert allergy_exclusions(excluded) == {"allergen": 1, "unknown_ingredients": 1}
