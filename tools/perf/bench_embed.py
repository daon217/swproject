"""DB-side embedding throughput: hash embedder (no model), N catalog items, time per phase."""
import os, time, statistics, sys
os.environ.setdefault('RECO_EMBEDDER', 'hash')
import psycopg
from services.recommendation import embedding_config as config, embedding_worker as worker
from services.recommendation.embedders import HashEmbedder
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3000
app_pw=os.environ['CATALOG_PASSWORD']; os.environ['CATALOG_PASSWORD']=os.environ['CATALOG_OWNER_PASSWORD']
with config.connect('owner') as owner:
    config.bootstrap(owner)
    with owner.transaction():
      owner.execute("""INSERT INTO app.catalog_items(kind,name,description,brand,category)
        SELECT CASE WHEN mod(g,2)=0 THEN 'product' ELSE 'food' END, '벤치 상품 '||g, '설명 '||g, '브랜드'||mod(g,50), '카테고리'||mod(g,20)
        FROM generate_series(1,%s) g""" % N)
      owner.execute("INSERT INTO app.products(item_id) SELECT item_id FROM app.catalog_items WHERE kind='product' ON CONFLICT DO NOTHING")
      owner.execute("INSERT INTO app.foods(item_id) SELECT item_id FROM app.catalog_items WHERE kind='food' ON CONFLICT DO NOTHING")
os.environ['CATALOG_PASSWORD']=app_pw
enc = HashEmbedder()
# time phases manually for one representative pass
claim_t, embed_t, finish_t, n = 0.0, 0.0, 0.0, 0
with config.connect() as conn:
    models = worker.serving_models(conn)
    pending = conn.execute('SELECT count(*) FROM app.embedding_jobs').fetchone()[0]
    print('jobs queued:', pending)
    t0 = time.perf_counter()
    while True:
        a = time.perf_counter(); jobs = worker.claim_many(conn, worker.BATCH_SIZE, models); b = time.perf_counter()
        if not jobs: break
        res = worker._embed(enc, jobs); c = time.perf_counter()
        if os.getenv('BATCH_TX')=='1':
            with conn.transaction():   # one commit per batch; per-item finish becomes a savepoint
                for job, vec, err in res:
                    worker.finish(conn, job, vec)
        else:
            for job, vec, err in res:
                worker.finish(conn, job, vec)
        d = time.perf_counter()
        claim_t += b - a; embed_t += c - b; finish_t += d - c; n += len(jobs)
    total = time.perf_counter() - t0
print('mode=', 'batch-commit' if os.getenv('BATCH_TX')=='1' else 'per-item-commit'); print(f'items={n} total={total:.1f}s  -> {n/total:.0f} items/s')
print(f'claim={claim_t:.1f}s  embed(hash)={embed_t:.1f}s  finish(DB write)={finish_t:.1f}s  ({finish_t/n*1000:.2f} ms/item)')
