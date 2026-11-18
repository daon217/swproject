import json
from pathlib import Path

import pytest

from services.recommendation import cli
from services.recommendation.adapters.local import InMemoryVectorIndex, JsonCatalog, JsonProfiles
from services.recommendation.allergens import assess, split_ingredients
from services.recommendation.contracts import CollectedProduct, ContractError, UserProfile
from services.recommendation.embedders import HashEmbedder
from services.recommendation.pipeline import Recommender
from services.recommendation.rankers import RuleRanker
from services.recommendation.tests.contract_suite import check_catalog, check_profiles, check_vector_index

SAMPLES = Path(__file__).resolve().parents[1] / "samples"


def load_samples():
    return [CollectedProduct.from_dict(json.loads(l)) for l in
            (SAMPLES / "products.sample.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


# --- 어댑터 계약 ---------------------------------------------------------
def test_local_catalog_contract(tmp_path):
    check_catalog(lambda: JsonCatalog(tmp_path))


def test_local_profiles_contract(tmp_path):
    check_profiles(lambda: JsonProfiles(tmp_path))


def test_local_vector_contract(tmp_path):
    check_vector_index(lambda: InMemoryVectorIndex(tmp_path, "t"))


# --- 데이터 계약 ---------------------------------------------------------
def test_contract_rejects_bad_rows():
    with pytest.raises(ContractError) as e:
        CollectedProduct.from_dict({"source": "Bad Source", "name": "", "price": 1000, "oops": 1})
    msg = " ".join(e.value.errors)
    assert "source_listing_id" in msg and "price" in msg and "oops" in msg


def test_samples_are_valid():
    assert len(load_samples()) == 10


def test_split_flattens_parentheses():
    assert split_ingredients("밀가루(밀), 유청분말(우유) 3%, 쇼트닝[대두유]") == [
        "밀가루", "밀", "유청분말", "우유", "쇼트닝", "대두유"]


# --- 알레르기 규칙 ----------------------------------------------------------
@pytest.fixture
def by_id():
    return {p.source_listing_id: p for p in load_samples()}


def test_milk_detected_from_ingredients_and_notice(by_id):
    milk = UserProfile("u", allergens=["milk"])
    assert not assess(by_id["cookie-001"], milk).safe
    assert not assess(by_id["yogurt-010"], milk).safe  # '원유' + 표시
    assert not assess(by_id["protein-bar-004"], milk).safe  # 분리유청단백
    assert assess(by_id["juice-007"], milk).safe


def test_cross_contact_respected(by_id):
    strict = UserProfile("u", allergens=["peanut"], exclude_cross_contact=True)
    loose = UserProfile("u", allergens=["peanut"], exclude_cross_contact=False)
    v = assess(by_id["rice-cracker-002"], strict)
    assert not v.safe and "혼입" in v.reasons[0]
    assert assess(by_id["rice-cracker-002"], loose).safe


def test_unknown_ingredients_excluded_only_for_allergic_users(by_id):
    assert not assess(by_id["mystery-008"], UserProfile("u", allergens=["egg"])).safe
    assert assess(by_id["mystery-008"], UserProfile("u")).safe


def test_avoid_ingredient(by_id):
    v = assess(by_id["seaweed-006"], UserProfile("u", avoid_ingredients=["현미유"]))
    assert not v.safe


# --- 파이프라인 -----------------------------------------------------------
class EvilRanker:
    """LLM 이 후보 밖(알레르기 상품)을 고르거나 중복을 내는 경우를 흉내냄."""
    name = "evil"

    def rank(self, profile, query, items, top_k):
        return [("demo:cookie-001", "버터 맛있음"), (items[0][0].product_id, "ok"), (items[0][0].product_id, "dup")]


class BrokenRanker:
    name = "claude"

    def rank(self, *a):
        raise TimeoutError("api down")


def make_rec(tmp_path, ranker):
    emb = HashEmbedder()
    rec = Recommender(JsonCatalog(tmp_path), InMemoryVectorIndex(tmp_path, emb.name), emb, ranker)
    rec.catalog.upsert(load_samples())
    assert rec.reindex() == 10
    return rec


def test_recommend_never_returns_allergens(tmp_path):
    rec = make_rec(tmp_path, RuleRanker())
    prof = UserProfile("u", allergens=["milk", "wheat", "egg"])
    r = rec.recommend(prof, "버터 쿠키 과자", top_k=10)
    ids = {p.product_id for p in r.picks}
    assert "demo:cookie-001" not in ids and "demo:yogurt-010" not in ids
    assert "demo:cookie-001" in {v.product_id for v in r.excluded}
    assert r.picks and r.ranker == "rule"


def test_ranker_cannot_bypass_safety(tmp_path):
    rec = make_rec(tmp_path, EvilRanker())
    r = rec.recommend(UserProfile("u", allergens=["milk"]), "쿠키", top_k=5)
    assert "demo:cookie-001" not in {p.product_id for p in r.picks}
    assert len(r.picks) == 1
    assert any("후보 밖" in n for n in r.notes)


def test_ranker_failure_falls_back(tmp_path):
    rec = make_rec(tmp_path, BrokenRanker())
    r = rec.recommend(UserProfile("u"), "주스", top_k=3)
    assert r.ranker == "rule-fallback" and len(r.picks) == 3


# --- CLI 전체 흐름 ----------------------------------------------------------
def test_cli_end_to_end(tmp_path, capsys):
    d = str(tmp_path / "data")
    base = ["--data", d, "--ranker", "rule"]
    assert cli.main(base + ["validate", str(SAMPLES / "products.sample.jsonl")]) == 0
    assert cli.main(base + ["ingest", str(SAMPLES / "products.sample.jsonl")]) == 0
    assert cli.main(base + ["profile", str(SAMPLES / "profiles.sample.json")]) == 0
    capsys.readouterr()
    assert cli.main(base + ["recommend", "--user", "u-peanut-soy", "--query", "과자"]) == 0
    out = json.loads(capsys.readouterr().out)
    picked = {p["product_id"] for p in out["picks"]}
    assert not picked & {"demo:peanut-snack-005", "demo:soy-milk-009", "demo:rice-cracker-002",
                         "demo:protein-bar-004", "demo:mystery-008"}


# --- Claude 랭커 (실제 API 호출 없이 응답 형태만 확인) ---------------------------
def test_claude_ranker_parses_structured_output(tmp_path):
    from types import SimpleNamespace
    from services.recommendation.rankers import ClaudeRanker, _Pick, _Picks

    calls = {}

    class FakeMessages:
        def parse(self, **kw):
            calls.update(kw)
            return SimpleNamespace(stop_reason="end_turn", parsed_output=_Picks(picks=[
                _Pick(product_id="demo:juice-007", reason="달지 않은 100% 과즙"),
                _Pick(product_id="demo:cookie-001", reason="후보 밖"),
            ]))

    rec = make_rec(tmp_path, ClaudeRanker(client=SimpleNamespace(messages=FakeMessages())))
    r = rec.recommend(UserProfile("u", allergens=["milk"]), "주스", top_k=3)
    assert [p.product_id for p in r.picks] == ["demo:juice-007"]
    assert r.ranker == "claude" and calls["output_format"] is _Picks
    assert "demo:cookie-001" not in calls["messages"][0]["content"]  # 알레르기 상품은 LLM 에 안 보냄
