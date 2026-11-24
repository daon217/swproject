"""E2E flows; imported helpers from sim.py."""
import os, sys, time, uuid, json, concurrent.futures as cf
from collections import Counter
from datetime import UTC, datetime, timedelta
sys.path.insert(0, '/sim')
from sim import API, RECO, COL, c, q, log, foods


def member(i, allergens=('peanut',)):
    lid = f'sim{i}{uuid.uuid4().hex[:6]}'
    pw = 'Sim-pass-427!'
    r = c.post(f'{API}/v2/auth/signup', json=dict(login_id=lid, password=pw, password_confirmation=pw, consent_accepted=True,
               consent_version='provisional-v1', birth_date='2000-01-01', gender='male', allergies=list(allergens)))
    assert r.status_code == 201, r.text
    t = c.post(f'{API}/v2/auth/login', json={'login_id': lid, 'password': pw}).json()['data']['token']
    return {'Authorization': 'Bearer ' + t}


def poll(h, aid, limit=200):
    t = time.monotonic()
    while time.monotonic() - t < limit:
        d = c.get(f'{API}/analyses/{aid}', headers=h).json()['data']
        if d['state'] not in ('queued', 'running'):
            return d, time.monotonic() - t
        time.sleep(0.7)
    return d, time.monotonic() - t


def summary(d):
    res = d.get('result') or {}
    items = res.get('items') if isinstance(res, dict) else res
    warn = (res.get('warnings') if isinstance(res, dict) else None) or d.get('warnings')
    return f"state={d['state']} domain={d.get('selected_domain')} items={len(items or [])} warnings={warn} error={d.get('error')}"


def analysis(h, **body):
    r = c.post(f'{API}/analyses', headers=h, json={'page_session_id': 's', 'page_revision': 1,
                                                   'request_key': uuid.uuid4().hex} | body)
    if r.status_code >= 400:
        return None, r
    return poll(h, r.json()['data']['analysis_id']), r


def e2e():
    real = json.load(open('/sim/real.json', encoding='utf-8'))
    h = member(1)
    (d, dt), _ = analysis(h, page_url=real[60]['url'])
    log(f'1 page_url real product: {dt:.1f}s {summary(d)}')
    log('  result keys', sorted(d.keys()), type(d.get('result')).__name__)
    (d, dt), _ = analysis(h, page_url='https://store.example.test/food/1')
    log(f'2 food page, peanut allergy: {dt:.1f}s {summary(d)}')
    files = {'image': ('cap.png', b'\x89PNG\r\n\x1a\n' + b'0' * 2000, 'image/png')}
    r = c.post(f'{API}/analyses', headers=h, data={'page_session_id': 's3', 'page_revision': '1',
                                                   'request_key': uuid.uuid4().hex}, files=files)
    if r.status_code < 400:
        aid = r.json()['data']['analysis_id']
        d, dt = poll(h, aid)
        log(f'3 capture-only, Vision down: {dt:.1f}s {summary(d)} db={q("SELECT attempt,state,error_code FROM app.analyses WHERE analysis_id=%s", aid)}')
    else:
        log('3 capture create failed', r.status_code, r.text[:200])
    (d, dt), _ = analysis(h, page_url='https://unknown-shop.example/p/1')
    log(f'4 unknown URL (no image): {dt:.1f}s {summary(d)}')

    hs = [member(100 + i) for i in range(12)]
    t = time.monotonic()
    def one(i):
        res, r = analysis(hs[i], page_url=real[i * 20]['url'])
        if res is None:
            return ('create', r.status_code)
        d, _ = res
        return (d['state'], (d.get('error') or {}).get('code') if isinstance(d.get('error'), dict) else None)
    with cf.ThreadPoolExecutor(12) as pool:
        outs = list(pool.map(one, range(12)))
    log(f'5 burst 12 page_url analyses: {time.monotonic()-t:.1f}s -> {Counter(map(str, outs))}')

    run = uuid.uuid4()
    ext = {'source': 'sim_late', 'source_listing_id': 'L1', 'variant_key': 'default', 'observation_key': 'late-ext-1',
           'observed_at': (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
           'matching_profile': {'brand': 'SimBrand', 'category': '주방가전', 'options': {'size': 'L'}}}
    r1 = c.post(f'{API}/internal/v2/crawl-runs/{run}/extensions', headers=COL, json=ext)
    obs = foods(1)[0] | {'source': 'sim_late', 'source_listing_id': 'L1', 'selected_domain': 'product', 'name': '전기 주전자',
                         'observation_key': 'late-obs-1', 'url': 'https://store.example.test/late/1',
                         'observed_at': (datetime.now(UTC) - timedelta(minutes=20)).isoformat()}
    r2 = c.post(f'{API}/internal/v2/crawl-runs/{run}/observations', headers=COL, json=obs)
    st = q("""SELECT e.state,i.brand,i.category,i.content_version FROM app.listing_extensions e
              JOIN app.offers o ON o.source=e.source AND o.source_listing_id=e.source_listing_id
              JOIN app.catalog_items i USING(item_id) WHERE e.observation_key='late-ext-1'""")
    log(f'6 extension early: {r1.status_code} {r1.json().get("state")} -> observation {r2.status_code} -> {st}')

    pw = 'Adm-pass-427!'
    lid = 'adm' + uuid.uuid4().hex[:8]
    r = c.post(f'{API}/v2/admin/auth/signup', json={'login_id': lid, 'password': pw, 'password_confirmation': pw,
               'consent_version': 'provisional-v1', 'consent_accepted': True})
    r2 = c.post(f'{API}/v2/admin/auth/login', json={'login_id': lid, 'password': pw})
    log(f'7 admin signup {r.status_code}, login before approval {r2.status_code} {r2.json().get("error", {}).get("code")}')
    open('/out/admin_login', 'w').write(lid)
    log('8 adpick unconfigured', c.post(f'{API}/v2/links/convert', json={'url': 'https://www.yappykids.com/x'}).status_code,
        'private URL', c.post(f'{API}/v2/links/convert', json={'url': 'http://10.0.0.1/x'}).status_code)


def admin_flow():
    lid = open('/out/admin_login').read().strip(); pw = 'Adm-pass-427!'
    tok = c.post(f'{API}/v2/admin/auth/login', json={'login_id': lid, 'password': pw})
    log('admin login after grant', tok.status_code, tok.text[:120] if tok.status_code != 200 else '')
    if tok.status_code != 200:
        return
    h = {'Authorization': 'Bearer ' + tok.json()['data']['token']}
    ov = c.get(f'{API}/v2/admin/overview', headers=h)
    log('overview', ov.status_code, {k: ov.json()['data'].get(k) for k in ('members', 'subscribers', 'today_subscribers')} if ov.status_code == 200 else ov.text[:200])
    ids = [r[0] for r in q("SELECT offer_id::text FROM app.offers WHERE source='adafruit' ORDER BY offer_id LIMIT 3")]
    d = c.post(f'{API}/v2/admin/catalog/offers/delete', headers=h, json={'offer_ids': ids})
    log('delete 3 offers', d.status_code, {k: len(v) for k, v in d.json()['data'].items()} if d.status_code == 200 else d.text[:200])
    log('members', c.get(f'{API}/v2/admin/members', headers=h).status_code,
        'support settings', c.get(f'{API}/v2/admin/support/settings', headers=h).status_code,
        'signup requests', c.get(f'{API}/v2/admin/auth/requests', headers=h).status_code)


if __name__ == '__main__':
    globals()[sys.argv[1]]()
