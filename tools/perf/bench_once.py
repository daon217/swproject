"""Embedding DB throughput through the real worker loop (once()), hash embedder so the model is excluded."""
import os
import sys
import time

from services.recommendation import embedding_config as config, embedding_worker as worker
from services.recommendation.embedders import HashEmbedder

N = int(sys.argv[1])
app_pw = os.environ['CATALOG_PASSWORD']
os.environ['CATALOG_PASSWORD'] = os.environ['CATALOG_OWNER_PASSWORD']
with config.connect('owner') as owner:
    config.bootstrap(owner)
    with owner.transaction():
        owner.execute("""INSERT INTO app.catalog_items(kind,name,description,brand,category)
            SELECT CASE WHEN mod(g,2)=0 THEN 'product' ELSE 'food' END, 'bench '||g, 'desc '||g, 'b'||mod(g,50), 'c'||mod(g,20)
            FROM generate_series(1,%s) g""" % N)
        owner.execute("INSERT INTO app.products(item_id) SELECT item_id FROM app.catalog_items WHERE kind='product' ON CONFLICT DO NOTHING")
        owner.execute("INSERT INTO app.foods(item_id) SELECT item_id FROM app.catalog_items WHERE kind='food' ON CONFLICT DO NOTHING")
os.environ['CATALOG_PASSWORD'] = app_pw
with config.connect() as conn:
    models = worker.serving_models(conn)
    enc = HashEmbedder()
    t = time.perf_counter()
    while worker.once(conn, enc, models=models):
        pass
    d = time.perf_counter() - t
print(f'{os.environ.get("LABEL")}: {N} items in {d:.1f}s -> {N / d:.0f} items/s ({d / N * 1000:.2f} ms/item, model excluded)')
