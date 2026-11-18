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
