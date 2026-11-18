"""저장소 구현이 지켜야 할 동작. 새 어댑터(예: 소병선 DB)는 이 함수들을 통과하면 갈아끼울 수 있습니다.

사용 예 (DB 어댑터 테스트에서):
    from services.recommendation.tests.contract_suite import check_catalog
    check_catalog(lambda: PgCatalog(conn))
"""
from services.recommendation.contracts import CollectedProduct, UserProfile


def _product(i: str, **kw) -> CollectedProduct:
    base = {"source": "suite", "source_listing_id": i, "name": f"상품 {i}", "ingredients_raw": "쌀, 소금"}
    base.update(kw)
    return CollectedProduct.from_dict(base)


def check_catalog(make):
    repo = make()
    assert repo.upsert([_product("a"), _product("b")]) == 2
    assert {"suite:a", "suite:b"} <= set(repo.all_ids())
    got = repo.get_many(["suite:a", "suite:missing"])
    assert set(got) == {"suite:a"}  # 없는 id 는 조용히 빠짐
    assert got["suite:a"].ingredients_raw == "쌀, 소금"
    repo.upsert([_product("a", name="바뀐 이름")])  # 같은 id 는 덮어쓰기
    assert make().get_many(["suite:a"])["suite:a"].name == "바뀐 이름"  # 새로 열어도 유지


def check_profiles(make):
    repo = make()
    assert repo.get("nobody") is None
    repo.save(UserProfile(user_id="suite-u", allergens=["milk"], preferences="간식"))
    p = make().get("suite-u")
    assert p is not None and p.allergens == ["milk"] and p.preferences == "간식"


def check_vector_index(make):
    idx = make()
    idx.upsert([("x", [1.0, 0.0, 0.0]), ("y", [0.0, 1.0, 0.0]), ("z", [0.7, 0.7, 0.0])])
    res = idx.search([1.0, 0.1, 0.0], limit=2)
    assert [c.product_id for c in res] == ["x", "z"]
    assert res[0].score >= res[1].score
    idx.upsert([("x", [0.0, 0.0, 1.0])])  # 덮어쓰기
    assert idx.search([1.0, 0.1, 0.0], limit=1)[0].product_id == "z"
