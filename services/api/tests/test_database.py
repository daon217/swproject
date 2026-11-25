"""Integration only: dedicated disposable DB on CI."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import pytest
import psycopg
from fastapi.testclient import TestClient
from kkulpick.api import app
from kkulpick.vectors import Contract, register, put, candidates
from test_contract import fixture

pytestmark=pytest.mark.skipif(os.getenv("CATALOG_INTEGRATION")!="1",reason="requires disposable migrated catalog")


def pg(role="app"):
    return psycopg.connect(host="127.0.0.1",port=os.getenv("DB_PORT","5433"),dbname="kkulpick_catalog",
        user="kkulpick_catalog_"+role,password=os.environ["CATALOG_"+role.upper()+"_PASSWORD"], autocommit=True)


def retire_fixture_models(model_ids):
    """Fixture contracts must not stay serving: activation backfills a job for every catalog item,
    and later embedding tests (or a real worker) would inherit thousands of orphaned jobs."""
    with pg("owner") as owner:
        owner.execute("UPDATE app.embedding_models SET is_serving=false WHERE model_id=ANY(%s)",(model_ids,))
        owner.execute("DELETE FROM app.embedding_jobs WHERE model_id=ANY(%s)",(model_ids,))


def test_catalog_and_vectors(request):
    now=datetime.now(UTC)-timedelta(minutes=2)
    rid=uuid4()
    path=f"/internal/v2/crawl-runs/{rid}/observations"
    headers={"Authorization":"Bearer "+os.environ["COLLECTOR_TOKEN"]}
    base=fixture()|dict(source_listing_id=str(rid),source='vector_'+rid.hex)
    def obs(i,secs,**extra):
        return base|{"observation_key":f"{rid}:{i}","observed_at":(now+timedelta(seconds=secs)).isoformat()}|extra
    with TestClient(app) as api, pg() as db, pg("owner") as owner:
        def post(data):
            return api.post(path,json=data,headers=headers)
        assert api.get("/health").status_code==200
        first=obs(1,0)
        assert api.post(path,json=first).status_code==401
        with ThreadPoolExecutor(2) as pool:
            responses=list(pool.map(post,[first,first]))
        assert sorted(r.status_code for r in responses)==[200,201]
        offer=responses[0].json()["offer_id"]
        assert responses[1].json()["offer_id"]==offer
        assert post(first|{"price":"123.00"}).status_code==409
        update=obs(2,30,price="11500.0000",url="https://store.example.test/new")
        assert post(update).json()["state"]=="applied"
        assert post(obs(3,8,price="1.0000")).json()["state"]=="recorded"
        assert post(obs(4,30,price="1.0000")).json()["error_code"]=="SAME_TIME_CONFLICT"
        assert post(obs(5,31,source_listing_id=None)).json()["state"]=="quarantine"
        def visible():
            return [x for x in api.get("/v2/offers?selected_domain=product&source="+base['source']).json()["items"] if x["offer_id"]==offer]
        assert visible()[0]["price"]=="11500.0000"
        assert not any(x["offer_id"]==offer for x in api.get("/v2/offers?selected_domain=food").json()["items"])
        for table in ("price_history","offer_url_history"):
            assert db.execute("SELECT count(*) FROM app."+table+" WHERE offer_id=%s",(offer,)).fetchone()[0]==2
        item=db.execute("SELECT item_id FROM app.offers WHERE offer_id=%s",(offer,)).fetchone()[0]
        m1,m2=[str(uuid4()) for _ in range(2)]
        request.addfinalizer(lambda: retire_fixture_models([m1,m2]))
        for m in (m1,m2):
            register(owner,Contract(m,"product","fixture-only","test-rev",3,"public-name","","",False))
            owner.execute("UPDATE app.embedding_models SET is_serving=true WHERE model_id=%s",(m,))
        put(db,m1,item,1,[1,0,0])
        assert candidates(db,m1,[1,0,0])[0][0]==item
        assert candidates(db,m2,[1,0,0])==[]
        for bad in ([0,0,0],[1,0],[float("nan"),1,0]):
            with pytest.raises(ValueError):
                put(db,m1,item,1,bad)
        assert post(obs(6,45,name="가상 주전자 수정")).status_code==201
        assert not candidates(db,m1,[1,0,0])
        with pytest.raises(psycopg.Error):
            put(db,m1,item,1,[1,0,0])
        fail={k:v for k,v in obs(7,50).items() if k not in first["field_presence"]}
        fail.update(field_presence=[],result="timeout")
        assert post(fail).json()["state"]=="recorded" and visible()
        fail.update(result="not_found",observation_key=f"{rid}:8")
        assert post(fail).json()["state"]=="applied" and not visible()


def test_run_source_and_invoice_owner_are_enforced_by_the_database():
    """2026-11-26 schema review: repeated facts may not contradict their source row."""
    run = uuid4()
    with pg() as c:
        c.execute("INSERT INTO app.crawl_runs(run_id,source) VALUES(%s,'run_a')", (run,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute("""INSERT INTO app.crawl_observations(run_id,source,observation_key,payload_hash,observed_at,
                normalized_payload,state) VALUES(%s,'run_b','k1','h',now(),'{}','received')""", (run,))
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            c.execute("""INSERT INTO app.listing_extensions(run_id,source,observation_key,schema_version,payload_hash,
                observed_at,normalized_payload,state,change_kind) VALUES(%s,'run_b','e1','listing-extension-v1','h',
                now(),'{}','pending','pending')""", (run,))
    with pg("owner") as o:
        o.execute("DELETE FROM app.crawl_runs WHERE run_id=%s", (run,))
    member = psycopg.connect(host="127.0.0.1", port=os.getenv("DB_PORT", "5433"), dbname="kkulpick_member",
                             user="kkulpick_member_owner", password=os.environ["MEMBER_OWNER_PASSWORD"], autocommit=True)
    with member as m, m.transaction(force_rollback=True):
        a, b = (m.execute("""INSERT INTO app.members(login_id,password_hash,consent_version)
            VALUES(%s,'x','v') RETURNING user_id""", ('own' + uuid4().hex[:10],)).fetchone()[0] for _ in range(2))
        plan = m.execute("SELECT plan_id FROM app.subscription_plans LIMIT 1").fetchone()[0]
        sub = m.execute("""INSERT INTO app.subscriptions(user_id,plan_id,billing_mode) VALUES(%s,%s,'mock')
            RETURNING subscription_id""", (a, plan)).fetchone()[0]
        with pytest.raises(psycopg.errors.ForeignKeyViolation), m.transaction():
            m.execute("""INSERT INTO app.invoices(subscription_id,user_id,idempotency_key,request_hash,amount,currency,
                period_start,period_end) VALUES(%s,%s,'key-12345','h',1,'KRW',now(),now()+interval '1 day')""", (sub, b))
