"""Durable catalog embedding worker; inference runs outside database transactions."""
import argparse
import logging
import time

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - per-project unit CI runs without psycopg
    psycopg = None
    dict_row = None

from . import embedding_config as config
from .adapters.postgres import _vectors

log = logging.getLogger(__name__)


def claim(conn):
    models = [config.validate(conn, k) for k in ('product', 'food')]
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''WITH ready AS (
            SELECT j.item_id,j.model_id FROM app.embedding_jobs j
            WHERE j.model_id=ANY(%s) AND available_at<=now()
              AND (lease_until IS NULL OR lease_until<now())
            ORDER BY available_at,item_id FOR UPDATE SKIP LOCKED LIMIT 1
          ) UPDATE app.embedding_jobs j SET lease_token=gen_random_uuid(),
            lease_until=now()+interval '5 minutes',attempts=j.attempts+1
          FROM ready r WHERE j.item_id=r.item_id AND j.model_id=r.model_id RETURNING j.*''', (models,))
        return cursor.fetchone()


def finish(conn, job, vector):
    with conn.transaction():
        # Catalog -> queue lock order matches the catalog trigger. Ingest may proceed during inference.
        current = conn.execute('SELECT content_version FROM app.catalog_items WHERE item_id=%s FOR SHARE',
                               (job['item_id'],)).fetchone()
        lease = conn.execute('''SELECT content_version FROM app.embedding_jobs
            WHERE item_id=%s AND model_id=%s AND lease_token=%s AND lease_until>now() FOR UPDATE''',
            (job['item_id'], job['model_id'], job['lease_token'])).fetchone()
        if not current or not lease or current[0] != job['content_version'] or lease[0] != job['content_version']:
            return False
        _vectors().put(conn, job['model_id'], job['item_id'], job['content_version'], vector)
        conn.execute('DELETE FROM app.embedding_jobs WHERE item_id=%s AND model_id=%s AND lease_token=%s',
                     (job['item_id'], job['model_id'], job['lease_token']))
        return True


def retry(conn, job, error):
    # Bounded backoff; error class only, never raw text, credentials or user data.
    conn.execute('''UPDATE app.embedding_jobs SET lease_token=NULL,lease_until=NULL,last_error=%s,
        available_at=now() + (%s * interval '1 second')
        WHERE item_id=%s AND model_id=%s AND lease_token=%s''',
        (type(error).__name__, min(300, 2 ** min(job['attempts'], 8)),
         job['item_id'], job['model_id'], job['lease_token']))


def once(conn, encoder=None):
    job = claim(conn)
    if not job:
        return False
    try:
        vector = (encoder or config.embedder()).embed_documents([config.snapshot_text(job['snapshot'])])[0]
        finish(conn, job, vector)
    except Exception as error:
        retry(conn, job, error)
        log.warning('Embedding job deferred (%s)', type(error).__name__)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true', help='Owner-only contract registration and missing-vector backfill')
    parser.add_argument('--drain', action='store_true', help='Process ready jobs once; fail if any remain pending')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.bootstrap:
        with config.connect('owner') as conn:
            config.bootstrap(conn)
        print('Embedding contracts, indexes and backfill queue ready')
        return
    encoder = config.embedder()
    while True:
        try:
            with config.connect() as conn:
                while once(conn, encoder):
                    pass
                if args.drain:
                    count = conn.execute('SELECT count(*) FROM app.embedding_jobs WHERE model_id=ANY(%s)',
                        ([config.contract(k).model_id for k in ('product', 'food')],)).fetchone()[0]
                    if count:
                        raise SystemExit(f'{count} embedding jobs still pending/retrying')
                    print('All configured catalog embeddings are current')
                    return
        except (psycopg.Error, ValueError) as error:
            if args.drain:
                raise
            log.warning('Embedding worker unavailable (%s); retrying', type(error).__name__)
        time.sleep(2)


if __name__ == '__main__':
    main()
