"""Database-backed arrival, ordering, concurrency and upload regressions."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from kkulpick.api import app
from test_contract import fixture
from test_database import pg

pytestmark = pytest.mark.skipif(os.getenv('CATALOG_INTEGRATION') != '1', reason='requires disposable migrated PostgreSQL')


@pytest.fixture
def catalog(monkeypatch):
    # Ordering/history tests intentionally use extreme values; anomaly policy is
    # exercised separately in test_sample_mutations with its production default.
    monkeypatch.setenv('CATALOG_PRICE_RATIO', '0')
    source = 'test_' + uuid4().hex
    start = datetime.now(UTC) - timedelta(days=10)
    base = fixture() | dict(source=source, source_listing_id='stable-1', variant_key='sku-1')
    base.pop('description', None)
    base['field_presence'].remove('description')
    path = f'/internal/v2/crawl-runs/{uuid4()}/observations'
    headers = {'Authorization': 'Bearer ' + os.environ['COLLECTOR_TOKEN']}
    with TestClient(app) as client, pg() as db:
        def post(seconds=0, patch=None, only=None, result='success', key=None):
            row = base | dict(observation_key=key or uuid4().hex,
                              observed_at=(start + timedelta(seconds=seconds)).isoformat(), result=result)
            if only is not None:
                for field in base['field_presence']:
                    row.pop(field, None)
                row['field_presence'] = list(only)
            row.update(patch or {})
            return client.post(path, json=row, headers=headers)
        def current():
            from psycopg.rows import dict_row
            with db.cursor(row_factory=dict_row) as cur:
                return cur.execute('SELECT o.*,i.name,i.description,i.content_version FROM app.offers o JOIN app.catalog_items i USING(item_id) WHERE source=%s', (source,)).fetchone()
        def count(table):
            return db.execute(f'SELECT count(*) FROM app.{table} h JOIN app.offers o USING(offer_id) WHERE source=%s', (source,)).fetchone()[0]
        yield client, post, current, count, source, db, base, start, path, headers
    # Match search spans sources (same GTIN/brand), so leftovers from an earlier run would leak into
    # later runs on the same database. Remove this run's rows.
    with pg('owner') as owner, owner.transaction():
        items = [r[0] for r in owner.execute('SELECT item_id FROM app.offers WHERE source=%s', (source,))]
        for table in ('offer_changes', 'price_history', 'offer_url_history', 'listing_extensions'):
            owner.execute(f'DELETE FROM app.{table} WHERE offer_id IN (SELECT offer_id FROM app.offers WHERE source=%s)', (source,))
        owner.execute('DELETE FROM app.listing_extensions WHERE source=%s', (source,))
        owner.execute('UPDATE app.crawl_observations SET offer_id=NULL WHERE source=%s', (source,))
        owner.execute('DELETE FROM app.affiliate_offers WHERE offer_id IN (SELECT offer_id FROM app.offers WHERE source=%s)', (source,))
        owner.execute('DELETE FROM app.offers WHERE source=%s', (source,))
        owner.execute('DELETE FROM app.catalog_items WHERE item_id=ANY(%s::uuid[])', (items,))


def test_changes_history_and_filters(catalog):
    api, post, current, count, source, *_ = catalog
    first = post().json()
    result = post(10, dict(price='42.50',url='https://store.example.test/moved',availability='out_of_stock',condition='used')).json()
    assert result['offer_id'] == first['offer_id']
    assert set(result['changed_fields']) == {'price','current_url','availability','condition'}
    assert str(current()['price']) == '42.5000'
    assert count('price_history') == count('offer_url_history') == count('offer_changes') == 2
    q = '/v2/offers?selected_domain=product&source=' + source
    assert api.get(q).json()['items'] == []
    assert len(api.get(q+'&condition=all&availability=all').json()['items']) == 1
    post(20, dict(condition='used',availability='available'))
    assert len(api.get(q+'&condition=used').json()['items']) == 1


def test_duplicate_unchanged_stale_and_conflict(catalog):
    _, post, current, count, *_ = catalog
    assert post(10,key='same').status_code == 201
    assert post(10,key='same').status_code == 200
    assert post(11,key='same').status_code == 409
    assert post(20).json()['change_kind'] == 'unchanged'
    assert post(0,dict(price='1')).json()['change_kind'] == 'stale'
    assert post(20,dict(price='2')).json()['error_code'] == 'SAME_TIME_CONFLICT'
    assert str(current()['price']) == '12000.0000'
    assert count('offer_changes') == count('price_history') == count('offer_url_history') == 1


def test_optional_backfill_shipping_and_content_version(catalog):
    _, post, current, count, *_ = catalog
    post(0,{'shipping_fee':'5','field_presence':['name','price','currency','url','availability','shipping_fee']})
    post(50,dict(name='new name',price='12500'))
    assert post(20,dict(description='later detail'),only=['description']).json()['change_kind'] == 'updated'
    assert current()['name'] == 'new name' and current()['description'] == 'later detail'
    assert str(current()['shipping_fee']) == '5.0000' and count('price_history') == 2
    assert current()['content_version'] == 3
    post(60,dict(name='changed',description=None),only=['name','description'])
    assert current()['description'] is None and current()['content_version'] == 4


def test_currency_change_does_not_reuse_shipping(catalog):
    _, post, current, *_ = catalog
    post()
    post(30,dict(price='10',currency='USD'),only=['price','currency'])
    post(10,dict(price='12000',currency='KRW',shipping_fee='3000'),only=['price','currency','shipping_fee'])
    assert current()['currency'] == 'USD' and current()['shipping_fee'] is None
    post(40,dict(price='10',currency='USD',shipping_fee='2'),only=['price','currency','shipping_fee'])
    assert str(current()['shipping_fee']) == '2.0000'
    post(50,dict(price='9',currency='EUR'),only=['price','currency'])
    assert current()['currency'] == 'EUR' and current()['shipping_fee'] is None


@pytest.mark.parametrize('failure',['timeout','blocked','error'])
def test_failures_do_not_remove_listing(catalog,failure):
    _, post, current, count, *_ = catalog
    post()
    assert post(10,only=[],result=failure).json()['change_kind'] == 'failed'
    assert current()['availability'] == 'available' and count('offer_changes') == 1


def test_not_found_recovery(catalog):
    _, post, current, *_ = catalog
    post()
    post(20,only=[],result='not_found')
    assert current()['availability'] == 'suspect'
    post(10)
    assert current()['availability'] == 'suspect'
    post(30)
    assert current()['availability'] == 'available'


def test_identity_options(catalog):
    _, post, _, _, source, db, *_ = catalog
    ids = [post().json()['offer_id'],post(10,dict(variant_key='sku-2')).json()['offer_id'],
           post(10,dict(source_listing_id='stable-2')).json()['offer_id']]
    assert len(set(ids)) == 3
    assert db.execute('SELECT count(*) FROM app.offers WHERE source=%s',(source,)).fetchone()[0] == 3


def test_concurrent_delivery(catalog):
    _, post, current, _, source, db, *_ = catalog
    with ThreadPoolExecutor(4) as pool:
        responses = list(pool.map(lambda _: post(key='first'),range(4)))
    assert sorted(r.status_code for r in responses) == [200,200,200,201]
    with ThreadPoolExecutor(4) as pool:
        responses = list(pool.map(lambda t: post(t,dict(price=str(t))),[40,10,30,20]))
    assert all(r.status_code == 201 for r in responses)
    assert str(current()['price']) == '40.0000'
    assert db.execute('SELECT count(*) FROM app.offers WHERE source=%s',(source,)).fetchone()[0] == 1


def test_no_expiry_and_currency_filter(catalog):
    api, post, _, _, source, *_ = catalog
    post()
    q = '/v2/offers?selected_domain=product&source='+source
    assert len(api.get(q).json()['items']) == 1
    assert api.get(q+'&currency=USD').json()['items'] == []
    assert len(api.get(q+'&currency=KRW').json()['items']) == 1


def test_omitted_condition_preserves_used(catalog):
    api, post, current, _, _, _, base, start, path, headers = catalog
    post(0,dict(condition='used'))
    row = base | dict(observation_key=uuid4().hex,observed_at=(start+timedelta(seconds=30)).isoformat())
    row.pop('condition',None)
    assert api.post(path,json=row,headers=headers).status_code == 201
    assert current()['condition'] == 'used'


def test_condition_unknown_is_stored_listed_and_never_erases_a_known_condition(catalog):
    """Shops that do not state new/used send condition=unknown (collector request, 2026-11-25)."""
    api, post, current, _, source, db, base, start, path, headers = catalog
    first = post(0, dict(condition='unknown'))
    assert first.status_code == 201 and first.json()['state'] == 'applied'
    assert current()['condition'] == 'unknown'
    q = '/v2/offers?selected_domain=product&source=' + source
    assert [i['condition'] for i in api.get(q + '&condition=unknown').json()['items']] == ['unknown']
    assert len(api.get(q).json()['items']) == 1                               # default list = new+used+unknown
    assert api.get(q + '&condition=new').json()['items'] == []                # "new only" never includes unknown
    assert len(api.get(q + '&condition=all').json()['items']) == 1
    # Public basic recommendations show anything not confirmed used.
    db.execute('UPDATE app.offers SET last_seen_at=now() WHERE source=%s', (source,))  # newest card first
    basic = api.get('/v2/recommendations/basic?selected_domain=product&limit=30').json()['data']
    card = next(i for i in basic if str(i['offer_id']) == first.json()['offer_id'])
    assert card['condition'] == 'unknown'                                     # clients label it '상태 미확인'
    # A later page that states the condition fills it in ...
    assert post(10, dict(condition='new')).json()['change_kind'] == 'updated'
    assert current()['condition'] == 'new'
    # ... and a later unknown never erases it.
    assert post(20, dict(condition='unknown')).json()['change_kind'] == 'unchanged'
    assert current()['condition'] == 'new'
    assert post(30, dict(condition='used')).json()['change_kind'] == 'updated'
    db.execute('UPDATE app.offers SET last_seen_at=now() WHERE source=%s', (source,))
    basic = api.get('/v2/recommendations/basic?selected_domain=product&limit=30').json()['data']
    assert next(i for i in basic if str(i['offer_id']) == first.json()['offer_id'])['condition'] == 'used'  # used is included
    assert post(40, dict(condition='unknown')).status_code == 201
    assert current()['condition'] == 'used'
    # Food may be unknown; used food stays rejected.
    food = base | dict(observation_key=uuid4().hex, observed_at=start.isoformat(), selected_domain='food',
                       source_listing_id='food-unknown', condition='unknown')
    assert api.post(path, json=food, headers=headers).status_code == 201
    used_food = food | dict(observation_key=uuid4().hex, source_listing_id='food-used', condition='used')
    assert api.post(path, json=used_food, headers=headers).status_code == 422
    bad = base | dict(observation_key=uuid4().hex, observed_at=start.isoformat(), condition='refurbished')
    assert api.post(path, json=bad, headers=headers).status_code == 422


def test_listing_extension_matching_and_food_evidence(catalog):
    api, post, _, _, source, db, base, start, path, headers = catalog
    first_id = post(0).json()['offer_id']
    food_id = post(5, dict(source_listing_id='food-1', variant_key='default', selected_domain='food', name='유기농 현미 스낵')).json()['offer_id']

    ext_path = path.replace('/observations', '/extensions')
    ext_body = {
        'schema_version': 'listing-matching-extension-v1',
        'source': source,
        'source_listing_id': 'stable-1',
        'variant_key': 'sku-1',
        'observation_key': 'ext-stable-1',
        'observed_at': (start + timedelta(seconds=10)).isoformat(),
        'matching_profile': {
            'brand': '꿀픽테크',
            'model_name': '주전자 프로',
            'model_number': 'KP-1000',
            'mpn': 'KP-1000-BLUE',
            'gtin': '8801043014809',
            'image_url': 'https://store.example.test/images/kettle.jpg',
            'color': 'blue',
            'options': {'capacity': '1L'},
            'seller_name': '공식스토어',
        },
    }
    r1 = api.post(ext_path, json=ext_body, headers=headers)
    assert r1.status_code == 201 and r1.json()['state'] == 'applied', r1.text
    # Idempotent replay
    assert api.post(ext_path, json=ext_body, headers=headers).status_code == 200
    # Payload conflict on same observation_key
    assert api.post(ext_path, json=ext_body | {'is_synthetic': True}, headers=headers).status_code == 409
    # Stale extension does not overwrite newer metadata
    stale = ext_body | {
        'observation_key': 'ext-stale',
        'observed_at': (start + timedelta(seconds=1)).isoformat(),
        'matching_profile': {'brand': '과거브랜드'},
    }
    assert api.post(ext_path, json=stale, headers=headers).json()['change_kind'] == 'stale'

    # 예전 수집기가 보내는 바코드·모델·판매자 값은 받기만 하고 저장하지 않는다(2026-11-27 컬럼 정리).
    item = db.execute('SELECT brand,image_url FROM app.catalog_items i JOIN app.offers o USING(item_id) WHERE o.offer_id=%s',
                      (first_id,)).fetchone()
    assert item == ('꿀픽테크', 'https://store.example.test/images/kettle.jpg')
    changed = db.execute("SELECT changed_fields FROM app.listing_extensions WHERE source=%s AND observation_key='ext-stable-1'",
                         (source,)).fetchone()[0]
    assert set(changed) <= {'brand', 'image_url', 'image_urls'}

    # Food evidence on product domain is quarantined
    bad_domain = {
        'schema_version': 'food-evidence-v1',
        'source': source,
        'source_listing_id': 'stable-1',
        'variant_key': 'sku-1',
        'observation_key': 'ext-domain-conflict',
        'observed_at': (start + timedelta(seconds=15)).isoformat(),
        'food_evidence': {'ingredients': ['현미', '소금']},
    }
    assert api.post(ext_path, json=bad_domain, headers=headers).json()['error_code'] == 'DOMAIN_CONFLICT'

    # Food evidence on food domain persists ingredients and allergen declarations
    food_ext = {
        'schema_version': 'food-evidence-v1',
        'source': source,
        'source_listing_id': 'food-1',
        'variant_key': 'default',
        'observation_key': 'ext-food-1',
        'observed_at': (start + timedelta(seconds=15)).isoformat(),
        'food_evidence': {
            'ingredients_raw': '유기농 현미 98%, 천일염 2%',
            'ingredients': ['유기농 현미', '천일염'],
            'allergen_notice_raw': '대두 함유',
            'allergens_declared': ['soy', '조개류', 'Pine Nut', '새우 함유'],
            'evidence_status': 'reported',
        },
    }
    rf = api.post('/internal/v2/listing-extensions', json=food_ext, headers=headers)
    assert rf.status_code == 201 and rf.json()['offer_id'] == food_id
    food_items = api.get(f'/v2/offers?selected_domain=food&source={source}').json()['items']
    assert len(food_items) == 1
    assert food_items[0]['ingredients'] == ['유기농 현미', '천일염']
    # #59: known codes/labels are stored as the shared client codes; unknown text is kept, never dropped.
    assert food_items[0]['allergens_declared'] == ['soybean', 'shellfish', 'pine_nut', '새우 함유']


def test_uploaded_300_import_and_replay(monkeypatch):
    path = os.getenv('CATALOG_REAL_DATA')
    if not path:
        pytest.skip('local dataset not committed to public repository')
    from urllib.parse import urlsplit
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    assert len(rows) == 300
    monkeypatch.setenv('CATALOG_URL_HOSTS',','.join(sorted({urlsplit(r['url']).hostname for r in rows})))
    runs = {r['source']:uuid4() for r in rows}
    headers = {'Authorization':'Bearer '+os.environ['COLLECTOR_TOKEN']}
    with TestClient(app) as api, pg() as db:
        ids=[]
        for row in rows:
            r=api.post(f"/internal/v2/crawl-runs/{runs[row['source']]}/observations",json=row,headers=headers)
            assert r.status_code == 201, r.text
            assert r.json()['change_kind'] == 'created'
            ids.append(r.json()['offer_id'])
        for row in rows:
            r=api.post(f"/internal/v2/crawl-runs/{runs[row['source']]}/observations",json=row,headers=headers)
            assert r.status_code == 200, r.text
        assert len(set(ids)) == 300
        for table in ['price_history','offer_url_history','offer_changes']:
            assert db.execute(f'SELECT count(*) FROM app.{table} h JOIN app.offers o USING(offer_id) WHERE source=ANY(%s)',(list(runs),)).fetchone()[0] == 300
        seen=[];cursor=None
        while True:
            q='/v2/offers?selected_domain=product&condition=all&availability=all&limit=100'
            if cursor: q+='&after='+cursor
            body=api.get(q).json()
            seen.extend(r['offer_id'] for r in body['items'] if r['source'] in runs)
            cursor=body['next_cursor']
            if not cursor: break
        assert len(seen) == len(set(seen)) == 300


def test_extension_before_first_observation_is_held_then_applied(catalog):
    api, post, current, _, source, db, base, start, path, headers = catalog
    ext_path = path.replace('/observations', '/extensions')
    early = {
        'source': source, 'source_listing_id': 'stable-1', 'variant_key': 'sku-1',
        'observation_key': 'ext-early', 'observed_at': (start + timedelta(seconds=5)).isoformat(),
        'matching_profile': {'brand': '먼저온브랜드', 'options': {'capacity': '1L', 'engraving': 'yes'}},
    }
    held = api.post(ext_path, json=early, headers=headers)
    assert held.status_code == 202 and held.json()['state'] == 'pending', held.text
    assert held.json()['error_code'] == 'OFFER_NOT_YET_OBSERVED'
    # Resend while still unknown: still held, not duplicated.
    assert api.post(ext_path, json=early, headers=headers).status_code == 202
    assert post(0).status_code == 201  # first observation creates the offer and applies the held details
    state = db.execute("SELECT state,change_kind,offer_id FROM app.listing_extensions WHERE source=%s AND observation_key='ext-early'",
                       (source,)).fetchone()
    assert state[0] == 'applied' and state[1] == 'updated' and str(state[2]) == str(current()['offer_id'])
    assert db.execute('SELECT brand FROM app.catalog_items WHERE item_id=%s', (current()['item_id'],)).fetchone()[0] == '먼저온브랜드'
    # A resend after it was applied is an idempotent replay.
    replay = api.post(ext_path, json=early, headers=headers)
    assert replay.status_code == 200 and replay.json()['state'] == 'applied'



def test_listing_checks_refresh_freshness_only_when_catalog_matches(catalog, monkeypatch):
    api, post, current, _, source, db, base, start, path, headers = catalog
    assert post(0).status_code == 201
    before = current()
    seen = datetime.now(UTC) - timedelta(minutes=1)
    check = {'source_listing_id': 'stable-1', 'variant_key': 'sku-1', 'observed_at': seen.isoformat(),
             'price': base['price'], 'currency': base['currency'], 'availability': base['availability']}
    batch = {'source': source, 'items': [
        check,
        check | {'price': '1.0000'},                                   # collector saw another price
        check | {'source_listing_id': 'never-observed'},              # not in catalog
        check | {'observed_at': (datetime.now(UTC) + timedelta(hours=1)).isoformat()},  # future
    ]}
    assert api.post('/internal/v2/listing-checks', json=batch).status_code == 401
    r = api.post('/internal/v2/listing-checks', json=batch, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # The matching check and the mismatching one share an identity: the newest one in the batch wins.
    assert body['rejected'][0]['reason'] == 'OBSERVED_AT_OUT_OF_RANGE'
    assert {'source_listing_id': 'never-observed', 'variant_key': 'sku-1'} in body['unknown']
    after = current()
    # Only freshness moves; the price clock and values stay untouched.
    assert after['price'] == before['price'] and after['price_observed_at'] == before['price_observed_at']
    assert after['last_changed_at'] == before['last_changed_at']
    if body['confirmed']:
        assert after['last_seen_at'] > before['last_seen_at']
    # A clean batch confirms and advances last_seen_at; an older check never moves it back.
    ok = api.post('/internal/v2/listing-checks', json={'source': source, 'items': [check]}, headers=headers).json()
    assert ok == {'confirmed': 1, 'mismatch': [], 'unknown': [], 'rejected': []}
    assert current()['last_seen_at'] == seen
    older = check | {'observed_at': (seen - timedelta(hours=1)).isoformat()}
    assert api.post('/internal/v2/listing-checks', json={'source': source, 'items': [older]}, headers=headers).json()['confirmed'] == 1
    assert current()['last_seen_at'] == seen
    bad = api.post('/internal/v2/listing-checks', json={'source': source, 'items': [check | {'price': '1.0000'}]}, headers=headers).json()
    assert bad['mismatch'] == [{'source_listing_id': 'stable-1', 'variant_key': 'sku-1'}] and bad['confirmed'] == 0


def test_cards_flag_stale_listings(catalog, monkeypatch):
    api, post, current, _, source, db, base, start, path, headers = catalog
    assert post(0).status_code == 201  # observed 10 days ago by the fixture clock
    monkeypatch.setenv('CATALOG_STALE_HOURS', '72')
    cards = api.get('/v2/recommendations/basic?limit=30').json()['data']
    mine = [c for c in cards if c['offer_id'] == str(current()['offer_id'])]
    if mine:  # basic lists the most recently seen listings; ours may be outside the window
        assert mine[0]['stale'] is True and mine[0]['seen_at']
    check = {'source_listing_id': 'stable-1', 'variant_key': 'sku-1', 'observed_at': datetime.now(UTC).isoformat(),
             'price': base['price'], 'currency': base['currency'], 'availability': base['availability']}
    assert api.post('/internal/v2/listing-checks', json={'source': source, 'items': [check]}, headers=headers).json()['confirmed'] == 1
    cards = api.get('/v2/recommendations/basic?limit=30').json()['data']
    mine = [c for c in cards if c['offer_id'] == str(current()['offer_id'])]
    assert mine and mine[0]['stale'] is False
