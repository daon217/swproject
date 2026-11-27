import pytest

from services.recommendation.contracts import UserProfile
from services.recommendation.pipeline import Recommender
from services.recommendation.product_types import ACCESSORY, product_same_kind, product_type
from services.recommendation.tests.test_food_types import Fake, food


@pytest.mark.parametrize("name,kind", [  # 실제 수집된 상품명
    ("삼성전자 NT200B5C i5 4G SSD128G Win10삼성전자", "노트북·PC"),      # '노트북' 없이 사양으로
    ("[최종 259만]삼성 갤럭시북5 프로360 NT960QHA-K51A 루나 울트라5 16GB/512GB", "노트북·PC"),
    ("2023 14Z90R-GR50K 인텔 i5-1340P/WIN11/14인치", "노트북·PC"),
    ("ASUS TUF A14 경량 게이밍 노트북", "노트북·PC"),
    ("TBZ NT950XEW-A51A WIN10 노트북 키스킨(지문막힘) WFMTLVV", ACCESSORY),  # 노트북보다 액세서리가 먼저
    ("썬더볼트5 USB4 80Gbps M.2 SSD 외장하드 케이스 SC110", ACCESSORY),
    ("삼성전자 외장하드 Y3 1TB + 파우치 증정 HX-MK10Y", "저장장치"),        # 파우치 '증정'은 덤
    ("Bose QuietComfort 15 노이즈 캔슬링 헤드폰 케이스 포함", None),
    ("너의 모든 것을 사랑해 (리커버 에디션)", None),
    ("갤럭시 S22 울트라 S22U 버건디 SM-S908N", "스마트폰"),
    ("델 DELL 27인치 QHD P2720D 민트급 IPS 모니터", "모니터"),
])
def test_product_type(name, kind):
    assert product_type(name) == kind


def test_category_used_when_name_unknown():
    assert product_type("스텐 3중 바닥 24cm", "프라이팬") == "프라이팬"
    assert product_type("스텐 3중 바닥 24cm", "product") is None
    assert product_type("생선 저장 케이스", "밀폐찬통/반찬용기") == "밀폐찬통/반찬용기"   # 분류가 이름보다 먼저
    assert product_same_kind(None, "노트북 키스킨", None) is False   # 품목 몰라도 액세서리는 뺌
    assert product_same_kind(None, "스텐 냄비", None) is True


def test_laptop_page_shows_same_kind_when_llm_picks_nothing():
    class PicksNothing:  # 학교 LLM이 'NT200B5C와 다르다'며 {"picks": []}를 돌려준 실제 경우
        name = "local"
        def rank(self, *a):
            return []
    rows = [food(1, "TBZ NT950XEW-A51A WIN10 노트북 키스킨(지문막힘)", 0.66),
            food(2, "[최종 259만]삼성 갤럭시북5 프로360 NT960QHA-K51A 루나 울트라5", 0.64),
            food(3, "썬더볼트5 USB4 80Gbps M.2 SSD 외장하드 케이스 SC110", 0.71),
            food(4, "2023 14Z90R-GR50K 인텔 i5-1340P/WIN11/14인치", 0.71)]
    fake = Fake(rows)
    r = Recommender(fake, fake, fake, PicksNothing()).recommend(
        UserProfile("u"), "삼성전자 NT200B5C i5 4G SSD128G Win10삼성전자", min_score=0.5, score_margin=0.25, domain="product")
    assert {p.name for p in r.picks} == {"2023 14Z90R-GR50K 인텔 i5-1340P/WIN11/14인치",   # 노트북만, 키스킨·케이스 없음
                                         "[최종 259만]삼성 갤럭시북5 프로360 NT960QHA-K51A 루나 울트라5"}
    assert r.ranker == "rule-fallback"
