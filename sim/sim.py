"""Runtime simulation driver. Runs inside the compose network (python:3.12-slim + httpx + psycopg)."""
import json, os, sys, time, uuid, concurrent.futures as cf
from datetime import UTC, datetime, timedelta
import httpx, psycopg

API = 'http://api:8000'
RECO = 'http://recommendation:8000'
COL = {'Authorization': 'Bearer ' + os.environ['COLLECTOR_TOKEN']}
SVC = {'Authorization': 'Bearer ' + os.environ['WORKSPACE_TOKEN']}
c = httpx.Client(timeout=30)


def db(role='owner', name='catalog'):
    return psycopg.connect(host='postgres', port=5432, dbname='kkulpick_' + name, user=f'kkulpick_{name}_{role}',
                           password=os.environ[f'{name.upper()}_{role.upper()}_PASSWORD'], autocommit=True)


def q(sql, *a, name='catalog'):
    with db(name=name) as conn:
        return conn.execute(sql, a).fetchall()


def log(*a):
    print('[sim]', *a, flush=True)


def post_obs(rows):
    runs = {}
    for r in rows:  # one crawl run per source, like the real collectors
        runs.setdefault(r['source'], uuid.uuid4())
    def send(r):
        return c.post(f"{API}/internal/v2/crawl-runs/{runs[r['source']]}/observations", json=r, headers=COL)
    t = time.monotonic()
    with cf.ThreadPoolExecutor(8) as pool:
        res = list(pool.map(send, rows))
    dt = time.monotonic() - t
    codes = {}
    states = {}
    for r in res:
        codes[r.status_code] = codes.get(r.status_code, 0) + 1
        try:
            states[r.json().get('state')] = states.get(r.json().get('state'), 0) + 1
        except Exception:
            pass
    log(f'observations n={len(rows)} {dt:.1f}s ({len(rows)/dt:.0f}/s) http={codes} state={states}')
    bad = [r.text[:200] for r in res if r.status_code >= 400][:3]
    if bad:
        log('  sample errors:', bad)
    return res


def foods(n=20, start=None):
    start = start or datetime.now(UTC) - timedelta(hours=1)
    names = ['우유 식빵', '땅콩 버터', '초코 쿠키', '두유 1L', '참깨 라면', '새우깡', '아몬드 우유', '밀크 초콜릿',
             '현미 누룽지', '계란 과자', '김치 만두', '치즈 케이크', '오징어 땅콩', '고추장 떡볶이', '버터 쿠키',
             '호두 과자', '요거트', '메밀 국수', '토마토 주스', '복숭아 젤리']
    out = []
    for i in range(n):
        out.append({'schema_version': 2, 'source': 'sim_food', 'observed_at': (start + timedelta(seconds=i)).isoformat(),
                    'result': 'success', 'selected_domain': 'food', 'source_listing_id': f'food-{i}',
                    'variant_key': 'default', 'condition': 'new', 'name': names[i % len(names)],
                    'price': str(1000 + i * 100), 'currency': 'KRW', 'availability': 'available',
                    'url': f'https://store.example.test/food/{i}', 'observation_key': f'sim-food-{i}-{uuid.uuid4().hex[:6]}',
                    'field_presence': ['name', 'price', 'currency', 'availability', 'url']})
    return out


def wait_embeddings(limit=300):
    t = time.monotonic()
    while time.monotonic() - t < limit:
        rows = q("""SELECT count(*) FILTER (WHERE m.is_serving), count(*) FILTER (WHERE NOT m.is_serving)
                    FROM app.embedding_jobs j JOIN app.embedding_models m USING(model_id)""")
        if rows[0][0] == 0:
            log(f'embedding queue drained in {time.monotonic()-t:.1f}s (jobs for non-serving models: {rows[0][1]})')
            return True
        time.sleep(2)
    log('embedding queue NOT drained', q("SELECT model_id,count(*),max(attempts),array_agg(DISTINCT last_error) FROM app.embedding_jobs GROUP BY 1"))
    return False


def reco(query, domain='product', allergens=()):
    t = time.monotonic()
    r = c.post(f'{RECO}/internal/process', headers=SVC,
               json={'query': query, 'selected_domain': domain, 'profile': {'user_id': 'sim', 'allergens': list(allergens)}})
    return r.status_code, (r.json() if r.headers.get('content-type', '').startswith('application/json') else r.text), time.monotonic() - t


def vectors():
    return q("""SELECT m.model_id, m.input_template, m.is_serving,
                (SELECT count(*) FROM app.product_embeddings e WHERE e.model_id=m.model_id) +
                (SELECT count(*) FROM app.food_embeddings e WHERE e.model_id=m.model_id)
                FROM app.embedding_models m ORDER BY m.model_id""")


def stage1():
    real = json.load(open('/sim/real.json', encoding='utf-8'))
    post_obs(real)
    post_obs(foods())
    # A second crawl round: price changes for 100 listings.
    later = []
    for i, r in enumerate(real[:100]):
        later.append(r | {'observation_key': r['observation_key'] + ':r2', 'price': str(round(float(r['price']) * 1.1, 2)),
                          'observed_at': (datetime.fromisoformat(r['observed_at']) + timedelta(hours=6)).isoformat()})
    post_obs(later)
    wait_embeddings()
    log('vectors', vectors())
    for qtext, dom in [('socket header', 'product'), ('perfume', 'product'), ('땅콩 버터', 'food')]:
        st, body, dt = reco(qtext, dom)
        log(f'reco "{qtext}" {dom}: {st} {dt*1000:.0f}ms ids={len(body.get("offer_ids", [])) if isinstance(body, dict) else body}')


def gap():
    log('vectors', vectors())
    log('jobs', q("SELECT model_id,count(*) FROM app.embedding_jobs GROUP BY 1"))
    for qtext, dom in [('socket header', 'product'), ('땅콩 버터', 'food')]:
        st, body, dt = reco(qtext, dom)
        log(f'reco BEFORE re-embed "{qtext}" {dom}: {st} ids={len(body.get("offer_ids", [])) if isinstance(body, dict) else body}')


def after():
    wait_embeddings()
    log('vectors', vectors())
    for qtext, dom in [('socket header', 'product'), ('perfume', 'product'), ('땅콩 버터', 'food')]:
        st, body, dt = reco(qtext, dom)
        log(f'reco AFTER "{qtext}" {dom}: {st} {dt*1000:.0f}ms ids={len(body.get("offer_ids", [])) if isinstance(body, dict) else body}')


if __name__ == '__main__':
    globals()[sys.argv[1]]()
