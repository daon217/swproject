import json
from pathlib import Path

import pytest

from services.recommendation import cli
from services.recommendation.adapters.local import InMemoryVectorIndex, JsonCatalog, JsonProfiles
from services.recommendation.allergens import ALLERGENS, assess, detect, normalize_code, split_ingredients
from services.recommendation.contracts import CollectedProduct, ContractError, UserProfile
from services.recommendation.embedders import HashEmbedder, torch_threads
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


def test_declared_codes_are_judged_as_codes_not_text():
    """#59: 'shellfish'·'pine_nut' 은 동의어 글자 매칭으로는 안 잡힌다. 신고 코드는 코드로 판정해야 한다."""
    assert not detect(split_ingredients("shellfish")) and not detect(split_ingredients("pine_nut"))
    for code in ALLERGENS:
        assert normalize_code(code) == code
    assert [normalize_code(x) for x in ("soybean", "Soybean", "pine nut", "pine-nut", "조개류", "잣", "unknown")] ==         ["soy", "soy", "pine_nut", "pine_nut", "shellfish", "pine_nut", None]
    base = dict(source="demo", source_listing_id="decl", name="해물 과자")
    shell = CollectedProduct.from_dict(base | {"allergens_declared": ["shellfish", "pine_nut", "soybean"]})
    for allergen in ("shellfish", "pine_nut", "soy"):
        v = assess(shell, UserProfile("u", allergens=[allergen]))
        assert not v.safe and v.detected == [allergen] and "신고 코드" in v.reasons[0]
    assert assess(shell, UserProfile("u", allergens=["milk"])).safe  # 신고 코드도 성분 정보로 인정


def test_declared_codes_apply_even_when_notice_text_exists():
    p = CollectedProduct.from_dict(dict(source="demo", source_listing_id="n", name="과자",
                                        allergen_notice_raw="밀 함유", allergens_declared=["shellfish"]))
    assert not assess(p, UserProfile("u", allergens=["shellfish"])).safe
    # 코드 체계 밖의 신고 값은 버리지 않고 글자로 한 번 더 확인한다.
    q = CollectedProduct.from_dict(dict(source="demo", source_listing_id="q", name="과자", allergens_declared=["새우 함유"]))
    assert not assess(q, UserProfile("u", allergens=["shrimp"])).safe
    with pytest.raises(ContractError):
        CollectedProduct.from_dict(dict(source="demo", source_listing_id="x", name="과자", allergens_declared="milk"))


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
            content = kw["messages"][0]["content"]
            juice = next(l.split("|")[0] for l in content.splitlines() if "|" in l and "주스" in l)
            return SimpleNamespace(stop_reason="end_turn", usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                                   parsed_output=_Picks(picks=[
                                       _Pick(id=juice, reason="달지 않은 100% 과즙"),
                                       _Pick(id="c99", reason="후보 밖 번호"),
                                   ]))

    rec = make_rec(tmp_path, ClaudeRanker(client=SimpleNamespace(messages=FakeMessages())))
    r = rec.recommend(UserProfile("u", allergens=["milk"]), "주스", top_k=3)
    assert [p.product_id for p in r.picks] == ["demo:juice-007"]
    assert r.ranker == "claude" and calls["output_format"] is _Picks
    content = calls["messages"][0]["content"]
    assert "버터 쿠키" not in content and "demo:" not in content  # 알레르기 상품·긴 id 는 LLM 에 안 보냄
    assert any("후보 밖" in n for n in r.notes)


def test_allergen_false_friends_not_flagged():
    """'메밀가루'는 밀, '코코아버터'는 우유가 아님. 괄호로 따로 적힌 알레르기는 그대로 잡음."""
    soba = CollectedProduct.from_dict({"source": "t", "source_listing_id": "soba", "name": "메밀면",
                                       "ingredients_raw": "메밀가루 100%"})
    choco = CollectedProduct.from_dict({"source": "t", "source_listing_id": "choco", "name": "다크",
                                        "ingredients_raw": "카카오매스, 코코아버터, 설탕"})
    milky = CollectedProduct.from_dict({"source": "t", "source_listing_id": "milky", "name": "쿠키",
                                        "ingredients_raw": "밀가루(밀), 버터(우유)"})
    assert assess(soba, UserProfile.from_dict({"user_id": "u", "allergens": ["wheat"]})).safe
    assert not assess(soba, UserProfile.from_dict({"user_id": "u", "allergens": ["buckwheat"]})).safe
    assert assess(choco, UserProfile.from_dict({"user_id": "u", "allergens": ["milk"]})).safe
    assert not assess(milky, UserProfile.from_dict({"user_id": "u", "allergens": ["milk"]})).safe


def test_compact_keeps_cheapest_duplicate():
    from services.recommendation.compress import compact_candidates

    a = CollectedProduct.from_dict({"source": "s1", "source_listing_id": "a", "name": "귀리 오트밀크 1L",
                                    "price": "4200", "currency": "KRW"})
    b = CollectedProduct.from_dict({"source": "s2", "source_listing_id": "b", "name": "귀리 오트밀크 1L",
                                    "price": "3900", "currency": "KRW"})
    c = compact_candidates(UserProfile.from_dict({"user_id": "u"}), "오트밀크", [(a, 0.9), (b, 0.8)])
    assert list(c.id_map.values()) == [b.product_id] and c.dropped_duplicates == 1


def test_torch_threads_default_avoids_oversubscription():
    """#67: all cores made MiniLM 8x slower (14 threads 34/s vs 4 threads 268/s)."""
    assert torch_threads(cpu_count=14, env="") == 4
    assert torch_threads(cpu_count=4, env="") == 2
    assert torch_threads(cpu_count=1, env="") == 1
    assert torch_threads(cpu_count=14, env="8") == 8
    with pytest.raises(ValueError):
        torch_threads(cpu_count=14, env="0")
