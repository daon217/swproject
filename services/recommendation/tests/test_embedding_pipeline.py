"""Run on a disposable migrated PostgreSQL/pgvector database only (CI and local dev)."""
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

try:
    import psycopg
except ImportError:  # pragma: no cover - skipped in unit-only CI without psycopg
    psycopg = None
import pytest
from fastapi.testclient import TestClient

from services.recommendation import embedding_config as config
from services.recommendation import embedding_worker as worker
from services.recommendation.adapters.postgres import PgVectorIndex, _vectors
from services.recommendation.embedders import HashEmbedder
from services.recommendation.http_service import app

pytestmark = pytest.mark.skipif(os.getenv('EMBEDDING_INTEGRATION') != '1', reason='requires disposable migrated PostgreSQL')
TOKEN = 'embedding-test-' + 'x' * 40


def pg(role='app'):
    return psycopg.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=os.getenv('DB_PORT', '5433'),
        dbname='kkulpick_catalog', user='kkulpick_catalog_' + role,
        password=os.environ['CATALOG_' + role.upper() + '_PASSWORD'], autocommit=True)


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv('RECO_EMBEDDER', 'hash')
    monkeypatch.setenv('RECO_RANKER', 'rule')
    monkeypatch.setenv('WORKSPACE_TOKEN', TOKEN)
    monkeypatch.setenv('CATALOG_PASSWORD', os.environ['CATALOG_APP_PASSWORD'])
    cached_embedder = config.embedder
    cached_embedder.cache_clear()
    with pg('owner') as owner, pg() as runtime:
        config.bootstrap(owner)
        source = 'embedding_test_' + uuid4().hex
        yield owner, runtime, source
        ids = [r[0] for r in owner.execute('SELECT item_id FROM app.offers WHERE source=%s', (source,))]
        owner.execute('DELETE FROM app.offers WHERE source=%s', (source,))
        owner.execute('DELETE FROM app.catalog_items WHERE item_id=ANY(%s::uuid[])', (ids,))
    cached_embedder.cache_clear()


def seed(conn, source, name='전기 주전자', kind='product', availability='available', listing=None):
    listing = listing or uuid4().hex
    with conn.transaction():
        item = conn.execute('INSERT INTO app.catalog_items(kind,name) VALUES(%s,%s) RETURNING item_id', (kind,name)).fetchone()[0]
        table = {'product':'products','food':'foods'}[kind]
        conn.execute(f'INSERT INTO app.{table}(item_id) VALUES(%s)', (item,))
        offer = conn.execute('''INSERT INTO app.offers(item_id,kind,source,source_listing_id,variant_key,condition,
          price,currency,current_url,availability,price_observed_at,status_observed_at,url_observed_at,
          content_observed_at,last_seen_at,last_checked_at,condition_observed_at,last_changed_at)
          VALUES(%s,%s,%s,%s,'default','new',1000,'KRW',%s,%s,now(),now(),now(),now(),now(),now(),now(),now())
          RETURNING offer_id''', (item,kind,source,listing,'https://store.example.test/'+listing,availability)).fetchone()[0]
    return item, str(offer), f'{source}:{listing}#default'


def drain(conn):
    while worker.once(conn, HashEmbedder()):
        pass


def job_for(conn, item):
    # Drain unrelated jobs first so tests never rely on table iteration order.
    while True:
        job = worker.claim(conn)
        assert job is not None
        if job['item_id'] == item:
            return job
        worker.finish(conn, job, HashEmbedder().embed_query(config.snapshot_text(job['snapshot'])))


def request(client, **extra):
    return client.post('/internal/process', headers={'Authorization':'Bearer '+TOKEN},
        json={'query':'전기 주전자','selected_domain':'product',**extra})


def test_bootstrap_idempotent_and_backfills_existing_demo(db):
    owner, conn, source = db
    model = config.contract('product').model_id
    owner.execute('UPDATE app.embedding_models SET is_serving=false WHERE model_id=%s', (model,))
    item, _, _ = seed(conn, source)
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()
    config.bootstrap(owner)
    assert conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()
    drain(conn)
    config.bootstrap(owner)
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()
    assert owner.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='app' AND indexdef LIKE %s", ('%'+model+'%',)).fetchone()[0] == 1
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE app.embedding_models SET is_serving=false WHERE model_id=%s", (model,))


def test_http_reads_persistent_vectors_and_embeds_only_query(db, monkeypatch):
    owner, conn, source = db
    # 고유한 이름: 앞선 테스트들이 같은 이름('전기 주전자')의 상품을 남기면 점수가 같은 후보가 8개를 넘어
    # 이 상품이 상위 8개 밖으로 밀릴 수 있다(실행 순서에 따라 실패하던 원인).
    unique = '전기 주전자 ' + source[-6:]
    item, offer, _ = seed(conn, source, name=unique)
    drain(conn)
    before = conn.execute('SELECT created_at FROM app.product_embeddings WHERE product_id=%s', (item,)).fetchone()
    class QueryOnly(HashEmbedder):
        calls = 0
        def embed_documents(self, texts):
            raise AssertionError('HTTP must not rebuild the catalog')
        def embed_query(self, text):
            self.calls += 1
            return super().embed_query(text)
    encoder = QueryOnly()
    monkeypatch.setattr(config, 'embedder', lambda: encoder)
    with TestClient(app) as client:
        for _ in range(2):
            response = request(client, query=unique)
            assert response.status_code == 200, response.text
            assert offer in response.json()['offer_ids']
        assert request(client, offers=[]).status_code == 422
        assert client.post('/internal/process', json={'query':'q','selected_domain':'product'}).status_code == 401
    assert encoder.calls == 2
    assert conn.execute('SELECT created_at FROM app.product_embeddings WHERE product_id=%s', (item,)).fetchone() == before


def test_update_invalidates_old_vector_and_refreshes_snapshot(db):
    _, conn, source = db
    item, _, pid = seed(conn, source)
    drain(conn)
    model = config.contract('product').model_id
    conn.execute("UPDATE app.catalog_items SET name='무선 이어폰' WHERE item_id=%s", (item,))
    assert conn.execute('SELECT content_version FROM app.catalog_items WHERE item_id=%s',(item,)).fetchone()[0] == 2
    assert pid not in [c.product_id for c in PgVectorIndex(conn,model).search(HashEmbedder().embed_query('주전자'),100)]
    drain(conn)
    assert conn.execute('SELECT content_version FROM app.product_embeddings WHERE product_id=%s AND model_id=%s',(item,model)).fetchone()[0] == 2
    assert pid in [c.product_id for c in PgVectorIndex(conn,model).search(HashEmbedder().embed_query('무선 이어폰'),100)]


def test_stale_inflight_result_does_not_ack_new_job(db):
    _, conn, source = db
    item, _, _ = seed(conn, source)
    job = job_for(conn, item)
    conn.execute("UPDATE app.catalog_items SET description='새 설명' WHERE item_id=%s", (item,))
    assert worker.finish(conn,job,HashEmbedder().embed_query('old')) is False
    worker.retry(conn,job,ValueError('old error'))
    row = conn.execute('SELECT content_version,attempts,last_error FROM app.embedding_jobs WHERE item_id=%s',(item,)).fetchone()
    assert row == (2,0,None)
    drain(conn)
    assert conn.execute('SELECT content_version FROM app.product_embeddings WHERE product_id=%s',(item,)).fetchone()[0] == 2


def test_lease_recovery_and_concurrent_claims(db):
    _, conn, source = db
    drain(conn)
    items = {seed(conn,source)[0] for _ in range(2)}
    def take(_):
        with pg() as other:
            return worker.claim(other)
    with ThreadPoolExecutor(2) as pool:
        jobs = list(pool.map(take,range(2)))
    assert {j['item_id'] for j in jobs} == items
    old = jobs[0]
    conn.execute("UPDATE app.embedding_jobs SET lease_until=now()-interval '1 second' WHERE item_id=%s", (old['item_id'],))
    new = worker.claim(conn)
    assert new['item_id'] == old['item_id'] and new['lease_token'] != old['lease_token']
    assert not worker.finish(conn,old,HashEmbedder().embed_query('stale'))
    assert worker.finish(conn,new,HashEmbedder().embed_query('valid'))


def test_failed_inference_retries_without_losing_job(db):
    _, conn, source = db
    drain(conn)
    item, _, _ = seed(conn,source)
    class Broken:
        def embed_documents(self,texts):raise RuntimeError('do not store private error content')
    assert worker.once(conn,Broken())
    row = conn.execute('SELECT attempts,last_error,lease_token,available_at>now() FROM app.embedding_jobs WHERE item_id=%s',(item,)).fetchone()
    assert row == (1,'RuntimeError',None,True)
    conn.execute('UPDATE app.embedding_jobs SET available_at=now() WHERE item_id=%s',(item,))
    drain(conn)
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s',(item,)).fetchone()


def test_price_only_change_and_transaction_rollback_do_not_enqueue(db):
    _, conn, source = db
    item, offer, _ = seed(conn,source)
    drain(conn)
    conn.execute('UPDATE app.offers SET price=2000 WHERE offer_id=%s',(offer,))
    with pytest.raises(RuntimeError), conn.transaction():
        conn.execute("UPDATE app.catalog_items SET name='rolled back' WHERE item_id=%s",(item,))
        raise RuntimeError()
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s',(item,)).fetchone()
    assert conn.execute('SELECT name,content_version FROM app.catalog_items WHERE item_id=%s',(item,)).fetchone() == ('전기 주전자',1)


def test_domains_availability_and_missing_food_ingredients(db):
    _, conn, source = db
    ids = [seed(conn,source,availability=status)[1] for status in ('ended','suspect','out_of_stock')]
    food = seed(conn,source,name='우유 쿠키',kind='food')[1]
    safe_item, safe_food, _ = seed(conn,source,name='현미 쌀 쿠키',kind='food')
    milk_item, milk_food, _ = seed(conn,source,name='버터 우유 쿠키',kind='food')
    conn.execute(
        """UPDATE app.foods SET ingredients_raw=%s,
           ingredients='["현미","천일염"]'::jsonb, evidence_status='reported' WHERE item_id=%s""",
        ('현미 98%, 천일염 2%', safe_item),
    )
    conn.execute(
        """UPDATE app.foods SET ingredients_raw='밀가루, 우유, 버터',
           ingredients='["밀가루","우유","버터"]'::jsonb, allergens_declared='["milk","wheat"]'::jsonb,
           evidence_status='reported' WHERE item_id=%s""",
        (milk_item,),
    )
    # #59: only a structured code declares shellfish; 'shellfish' is not text-matchable and notice text is unrelated.
    shell_item, shell_food, _ = seed(conn,source,name='현미 해물 쿠키',kind='food',listing='shell-'+uuid4().hex)
    conn.execute(
        """UPDATE app.foods SET ingredients_raw='현미, 천일염', ingredients='["현미","천일염"]'::jsonb,
           allergen_notice_raw='밀 함유 없음', allergens_declared='["shellfish"]'::jsonb,
           evidence_status='reported' WHERE item_id=%s""",
        (shell_item,),
    )
    visible = seed(conn,source)[1]
    drain(conn)
    with TestClient(app) as client:
        data = request(client).json()
        assert visible in data['offer_ids'] and not set(ids+[food, safe_food, milk_food]) & set(data['offer_ids'])
        response = request(client,query='쿠키',selected_domain='food',profile={'user_id':'test','allergens':['milk']},ingredients=['우유'])
        assert response.status_code == 200
        # Missing-ingredient food and milk-containing food are excluded, while safe food with DB ingredients is recommended.
        assert food not in response.json()['offer_ids']
        assert milk_food not in response.json()['offer_ids']
        assert safe_food in response.json()['offer_ids']
        assert response.json()['warnings'][0]['allergen'] == 'milk'
        assert shell_food in response.json()['offer_ids']  # not allergic to shellfish -> still recommended
        shell = request(client,query='쿠키',selected_domain='food',profile={'user_id':'test','allergens':['shellfish']},
                        ingredients=['현미'])
        assert shell.status_code == 200
        assert shell_food not in shell.json()['offer_ids'] and safe_food in shell.json()['offer_ids']
        # The page itself: catalog-context hands the declared codes to the worker separately from ingredients.
        listing = conn.execute('SELECT source_listing_id FROM app.offers WHERE offer_id=%s',(shell_food,)).fetchone()[0]
        context = client.post('/internal/catalog-context',headers={'Authorization':'Bearer '+TOKEN},
            json={'page_url':'https://store.example.test/'+listing,'selected_domain':'food'}).json()['match']
        assert context['allergens_declared'] == ['shellfish'] and context['ingredients'] == ['현미','천일염']
        # 성분표 없이 판매처 알레르기 표시만 있는 식품: 표시에 없는 알레르기는 '인식 못함'으로 경고하지 않고,
        # 표시에 있는 알레르기는 경고한다. 둘 다 없을 때만 '인식 못함'.
        w = lambda **kw: request(client,query='쿠키',selected_domain='food',profile={'user_id':'t','allergens':['milk','shellfish']},**kw).json()['warnings']
        assert [(x['allergen'],x['evidence']) for x in w(allergens_declared=['soybean','wheat'])] == []
        assert [(x['allergen'],x['evidence']) for x in w(allergens_declared=['shellfish'])] == [('shellfish','contains')]
        assert {(x['allergen'],x['evidence']) for x in w()} == {('milk','unknown'),('shellfish','unknown')}


def test_missing_contract_returns_503_not_memory_fallback(db):
    owner, conn, _ = db
    model = config.contract('product').model_id
    owner.execute('UPDATE app.embedding_models SET is_serving=false WHERE model_id=%s',(model,))
    try:
        with TestClient(app) as client:
            assert request(client).status_code == 503
            assert client.get('/health').status_code == 503
    finally:
        config.bootstrap(owner)


def test_model_contract_mismatch_and_zero_vector_rejected(db):
    owner, conn, source = db
    item, _, _ = seed(conn,source)
    model = config.contract('product')
    with pytest.raises(psycopg.Error):
        owner.execute('UPDATE app.embedding_models SET revision=%s WHERE model_id=%s',('different',model.model_id))
    for vector in ([0]*384,[1,0],[float('nan')]*384):
        with pytest.raises(ValueError):
            _vectors().put(conn,model.model_id,item,1,vector)
    assert conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s',(item,)).fetchone()


def test_context_lookup_is_exact_and_not_first_thousand_limited(db):
    _, conn, source = db
    # More than the old API cap, committed together; no application pagination involved.
    with conn.transaction():
        for n in range(1001):
            seed(conn,source,name=f'가상 상품 {n}',listing=str(n))
    with TestClient(app) as client:
        for listing, found in [
            ('1000',True),
            ('1000#review',True),
            ('1000?different=1',False),
        ]:
            response = client.post('/internal/catalog-context',headers={'Authorization':'Bearer '+TOKEN},
                json={'page_url':'https://store.example.test/'+listing})
            assert response.status_code == 200
            assert bool(response.json()['match']) is found
        # Uppercase host, http vs https, and URL fragment still match the stored canonical URL
        for variant_url in [
            'https://STORE.EXAMPLE.TEST/1000#review',
            'http://store.example.test/1000#detail',
            'https://store.example.test:443/1000',
        ]:
            response = client.post('/internal/catalog-context',headers={'Authorization':'Bearer '+TOKEN},
                json={'page_url':variant_url})
            assert response.status_code == 200
            assert response.json()['match']['name'] == '가상 상품 1000'
    # Backfill processes all 1001 items, not just one API page.
    drain(conn)
    count = conn.execute('''SELECT count(*) FROM app.product_embeddings e JOIN app.offers o ON o.item_id=e.product_id
                           WHERE o.source=%s''',(source,)).fetchone()[0]
    assert count == 1001


def test_domain_switch_cleans_up_stale_embedding_jobs(db):
    owner, conn, source = db
    drain(conn)
    item, offer, _ = seed(conn, source, name='도메인 전환 테스트 상품', kind='product')
    product_model = config.contract('product').model_id
    food_model = config.contract('food').model_id
    assert conn.execute('SELECT count(*) FROM app.embedding_jobs WHERE item_id=%s AND model_id=%s', (item, product_model)).fetchone()[0] == 1

    # Switch item from product -> food inside a transaction (satisfying deferred subtype constraint)
    with owner.transaction():
        owner.execute('DELETE FROM app.offers WHERE offer_id=%s', (offer,))
        owner.execute('DELETE FROM app.products WHERE item_id=%s', (item,))
        owner.execute('INSERT INTO app.foods(item_id) VALUES(%s)', (item,))
        owner.execute("UPDATE app.catalog_items SET kind='food', name='도메인 전환 식품' WHERE item_id=%s", (item,))

    # The trigger removes the old product embedding job and enqueues only the food embedding job
    jobs = conn.execute('SELECT model_id FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchall()
    assert [r[0] for r in jobs] == [food_model]
    drain(conn)
    assert conn.execute('SELECT count(*) FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()[0] == 0


def test_poison_job_is_parked_instead_of_retrying_forever(db, monkeypatch):
    _, conn, source = db
    drain(conn)
    item, _, _ = seed(conn, source)
    monkeypatch.setattr(worker, 'MAX_ATTEMPTS', 2)
    class Broken:
        def embed_documents(self, texts): raise RuntimeError('always fails')
    for _ in range(2):
        conn.execute('UPDATE app.embedding_jobs SET available_at=now() WHERE item_id=%s', (item,))
        assert worker.once(conn, Broken())
    row = conn.execute("SELECT attempts,last_error,available_at='infinity' FROM app.embedding_jobs WHERE item_id=%s",
                       (item,)).fetchone()
    assert row == (2, 'exhausted:RuntimeError', True)
    # Parked: never claimed again, even when forced available, until explicitly requeued.
    conn.execute('UPDATE app.embedding_jobs SET available_at=now() WHERE item_id=%s', (item,))
    assert all(j['item_id'] != item for j in worker.claim_many(conn, 100))
    conn.execute("UPDATE app.embedding_jobs SET lease_token=NULL,lease_until=NULL,available_at='infinity' WHERE item_id=%s", (item,))
    assert worker.pending_counts(conn)[1] >= 1
    assert worker.requeue_failed(conn) >= 1
    drain(conn)
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()


def test_one_bad_item_does_not_block_the_batch(db):
    _, conn, source = db
    drain(conn)
    good, _, _ = seed(conn, source, name='무선 키보드')
    bad, _, _ = seed(conn, source, name='POISON 상품')
    class Picky:
        def embed_documents(self, texts):
            if any('POISON' in t for t in texts): raise ValueError('bad input')
            return HashEmbedder().embed_documents(texts)
    assert worker.once(conn, Picky())
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (good,)).fetchone()
    assert conn.execute('SELECT attempts,last_error FROM app.embedding_jobs WHERE item_id=%s', (bad,)).fetchone() == (1, 'ValueError')


def test_batch_commit_isolates_a_failing_write(db, monkeypatch):
    """#67: the batch commits once; a DB-side failure for one item rolls back only its savepoint."""
    _, conn, source = db
    drain(conn)
    good, _, _ = seed(conn, source, name='배치 정상 상품')
    bad, _, _ = seed(conn, source, name='배치 실패 상품')
    real_put = worker._vectors().put
    def put(c, model, parent, version, values):
        if str(parent) == str(bad):
            c.execute('SELECT 1/0')   # real SQL error inside the item's savepoint
        return real_put(c, model, parent, version, values)
    monkeypatch.setattr(worker._vectors(), 'put', put)
    assert worker.once(conn, HashEmbedder())
    assert conn.info.transaction_status.name == 'IDLE'   # batch transaction committed, not left open
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (good,)).fetchone()
    assert conn.execute('SELECT count(*) FROM app.product_embeddings WHERE product_id=%s', (good,)).fetchone()[0] == 1
    assert conn.execute('SELECT attempts,last_error FROM app.embedding_jobs WHERE item_id=%s', (bad,)).fetchone() == (1, 'DivisionByZero')


def test_job_whose_worker_kept_dying_is_parked_and_requeueable(db):
    """#71: attempts are counted at claim time, so a worker killed MAX times left a job that was
    neither claimable nor visible to --requeue-failed."""
    _, conn, source = db
    drain(conn)
    item, _, _ = seed(conn, source, name='반복 종료 상품')
    conn.execute('''UPDATE app.embedding_jobs SET attempts=%s, lease_token=gen_random_uuid(),
        lease_until=now()-interval '1 second' WHERE item_id=%s''', (worker.MAX_ATTEMPTS, item))
    worker.once(conn, HashEmbedder())
    row = conn.execute("SELECT last_error, available_at='infinity' FROM app.embedding_jobs WHERE item_id=%s", (item,)).fetchone()
    assert row == ('exhausted:WorkerLost', True)
    assert worker.pending_counts(conn)[1] >= 1                  # reported as parked, not silently pending
    assert worker.requeue_failed(conn) >= 1
    drain(conn)
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()


def test_brand_and_category_changes_reembed_and_enter_text(db):
    _, conn, source = db
    item, offer, _ = seed(conn, source)
    drain(conn)
    conn.execute("UPDATE app.catalog_items SET brand='꿀픽테크', category='주방가전' WHERE item_id=%s", (item,))
    assert conn.execute('SELECT content_version FROM app.catalog_items WHERE item_id=%s', (item,)).fetchone()[0] == 2
    snapshot = conn.execute('SELECT snapshot FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()[0]
    assert snapshot['brand'] == '꿀픽테크' and snapshot['category'] == '주방가전'
    assert config.snapshot_text(snapshot) == '전기 주전자 | 꿀픽테크 | 주방가전 | product'
    drain(conn)
    # Price changes alone still do not re-embed.
    conn.execute('UPDATE app.offers SET price=3000 WHERE offer_id=%s', (offer,))
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE item_id=%s', (item,)).fetchone()


def test_bootstrap_retires_superseded_contracts(db):
    owner, conn, source = db
    old = _vectors().Contract(model_id='catalog-product-superseded-' + uuid4().hex[:8], target='product',
                              encoder_name='hash-ngram-384', revision='hash-ngram-v1', dimensions=384,
                              input_template='catalog-v1: name | kind | description (omit empty fields)',
                              query_prefix='', document_prefix='', normalize=True)
    _vectors().register(owner, old)
    owner.execute('UPDATE app.embedding_models SET is_serving=true WHERE model_id=%s', (old.model_id,))
    seed(conn, source)
    config.bootstrap(owner)
    assert conn.execute('SELECT is_serving FROM app.embedding_models WHERE model_id=%s', (old.model_id,)).fetchone()[0] is False
    assert not conn.execute('SELECT 1 FROM app.embedding_jobs WHERE model_id=%s', (old.model_id,)).fetchone()
    owner.execute('DELETE FROM app.embedding_models WHERE model_id=%s', (old.model_id,))


def test_optional_staleness_window_drops_unconfirmed_offers(db, monkeypatch):
    _, conn, source = db
    item, offer, pid = seed(conn, source, name='오래된 주전자')
    drain(conn)
    model = config.contract('product').model_id
    query = HashEmbedder().embed_query('오래된 주전자')
    conn.execute("UPDATE app.offers SET last_seen_at=now()-interval '10 days' WHERE offer_id=%s", (offer,))
    assert pid in [c.product_id for c in PgVectorIndex(conn, model).search(query, 100)]  # default: keep
    monkeypatch.setenv('RECO_MAX_STALENESS_HOURS', '72')
    assert pid not in [c.product_id for c in PgVectorIndex(conn, model).search(query, 100)]
    conn.execute('UPDATE app.offers SET last_seen_at=now() WHERE offer_id=%s', (offer,))
    assert pid in [c.product_id for c in PgVectorIndex(conn, model).search(query, 100)]
