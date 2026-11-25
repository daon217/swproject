"""catalog DB(pgvector) 어댑터 통합 테스트. 마이그레이션까지 끝난 테스트용 DB 가 있을 때만 실행.

  $env:KKULPICK_TEST_PG_DSN="host=127.0.0.1 port=5433 dbname=kkulpick_catalog user=kkulpick_catalog_app password=..."
  $env:KKULPICK_TEST_PG_OWNER_DSN="... user=kkulpick_catalog_owner password=..."
  py -m pytest -q services/recommendation/tests/test_postgres_adapter.py

테스트 상품은 source='reco_test' 로 넣고 끝나면 지웁니다. 공용 DB 에서는 돌리지 마세요.
"""
import os
import uuid

import pytest

DSN, OWNER = os.getenv("KKULPICK_TEST_PG_DSN"), os.getenv("KKULPICK_TEST_PG_OWNER_DSN")
pytestmark = pytest.mark.skipif(not (DSN and OWNER), reason="KKULPICK_TEST_PG_DSN / _OWNER_DSN 없음")


@pytest.fixture()
def db():
    psycopg = pytest.importorskip("psycopg")
    owner = psycopg.connect(OWNER, autocommit=True)
    app = psycopg.connect(DSN, autocommit=True)
    model = f"reco-test-{uuid.uuid4().hex[:8]}"
    yield owner, app, model
    owner.close(); app.close()


def _seed(owner, listing, name, price="1000"):
    with owner.transaction():
        iid = owner.execute("INSERT INTO app.catalog_items(kind,name) VALUES ('food',%s) RETURNING item_id",
                            (name,)).fetchone()[0]
        owner.execute("INSERT INTO app.foods(item_id) VALUES (%s)", (iid,))
        owner.execute("""INSERT INTO app.offers(item_id,kind,source,source_listing_id,variant_key,condition,price,
            currency,current_url,availability,price_observed_at,status_observed_at,url_observed_at,
            content_observed_at,last_seen_at,last_checked_at,condition_observed_at,last_changed_at)
            VALUES (%s,'food','reco_test',%s,'default','new',%s,'KRW','https://t.test/p','available',
            now(),now(),now(),now(),now(),now(),now(),now())""", (iid, listing, price))


def _cleanup(owner):
    owner.execute("DELETE FROM app.food_embeddings WHERE food_id IN (SELECT item_id FROM app.offers WHERE source='reco_test')")
    ids = [r[0] for r in owner.execute("SELECT item_id FROM app.offers WHERE source='reco_test'").fetchall()]
    owner.execute("DELETE FROM app.offers WHERE source='reco_test'")
    with owner.transaction():
        owner.execute("DELETE FROM app.foods WHERE item_id = ANY(%s)", (ids,))
        owner.execute("DELETE FROM app.catalog_items WHERE item_id = ANY(%s)", (ids,))


class _Emb:  # 3차원 고정 임베딩
    name, dimensions = "reco-test-3d", 3


def test_pgvector_index_and_catalog(db):
    from services.recommendation.adapters.postgres import PgCatalog, PgVectorIndex, register_model

    owner, app, model = db
    _cleanup(owner)
    try:
        for i in "xyz":
            _seed(owner, i, f"테스트 {i}")
        register_model(owner, model, _Emb())
        idx = PgVectorIndex(app, model)
        x, y, z = "reco_test:x#default", "reco_test:y#default", "reco_test:z#default"
        idx.upsert([(x, [1.0, 0.0, 0.0]), (y, [0.0, 1.0, 0.0]), (z, [0.7, 0.7, 0.0])])
        res = idx.search([1.0, 0.1, 0.0], limit=2)
        assert [c.product_id for c in res] == [x, z] and res[0].score >= res[1].score
        idx.upsert([(x, [0.0, 0.0, 1.0])])  # 덮어쓰기
        assert idx.search([1.0, 0.1, 0.0], limit=1)[0].product_id == z
        with pytest.raises(KeyError):
            idx.upsert([("reco_test:nope#default", [1.0, 0.0, 0.0])])

        cat = PgCatalog(app)
        assert {x, y, z} <= set(cat.all_ids())
        got = cat.get_many([x, "reco_test:nope"])
        assert set(got) == {x} and got[x].name == "테스트 x" and got[x].ingredients_raw is None
    finally:
        _cleanup(owner)
        owner.execute("DELETE FROM app.food_embeddings WHERE model_id=%s", (model,))
        for (name,) in owner.execute("SELECT indexname FROM pg_indexes WHERE schemaname='app' "
                                     "AND indexdef LIKE %s", (f"%'{model}'%",)).fetchall():
            owner.execute(f'DROP INDEX app."{name}"')
        owner.execute("DELETE FROM app.embedding_models WHERE model_id=%s", (model,))
