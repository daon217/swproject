"""Durable catalog embedding worker; inference runs outside database transactions."""
import argparse
import logging
import os
import time

try:
    import psycopg
    from psycopg.rows import dict_row
    CONNECTION_LOST = (psycopg.OperationalError,)
except ImportError:  # pragma: no cover - per-project unit CI runs without psycopg
    psycopg = None
    dict_row = None
    CONNECTION_LOST = ()

from . import embedding_config as config
from .adapters.postgres import _vectors

log = logging.getLogger(__name__)


# A job that keeps failing (bad snapshot, model error) must not be retried forever.
# After MAX_ATTEMPTS it is parked (available_at = infinity) and reported, not claimed again.
MAX_ATTEMPTS = max(1, int(os.getenv('EMBEDDING_MAX_ATTEMPTS', '8')))
BATCH_SIZE = max(1, min(256, int(os.getenv('EMBEDDING_BATCH_SIZE', '32'))))
EXHAUSTED_PREFIX = 'exhausted:'


def serving_models(conn):
    return [config.validate(conn, k) for k in ('product', 'food')]


def claim_many(conn, limit=BATCH_SIZE, models=None):
    models = models or serving_models(conn)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''WITH ready AS (
            SELECT j.item_id,j.model_id FROM app.embedding_jobs j
            WHERE j.model_id=ANY(%s) AND available_at<=now() AND attempts<%s
              AND (lease_until IS NULL OR lease_until<now())
            ORDER BY available_at,item_id FOR UPDATE SKIP LOCKED LIMIT %s
          ) UPDATE app.embedding_jobs j SET lease_token=gen_random_uuid(),
            lease_until=now()+interval '5 minutes',attempts=j.attempts+1
          FROM ready r WHERE j.item_id=r.item_id AND j.model_id=r.model_id RETURNING j.*''',
            (models, MAX_ATTEMPTS, limit))
        return cursor.fetchall()


def claim(conn):
    jobs = claim_many(conn, 1)
    return jobs[0] if jobs else None


def finish(conn, job, vector):
    with conn.transaction():
        # Catalog -> queue lock order matches the catalog trigger. Ingest may proceed during inference.
        current = conn.execute('SELECT content_version, kind FROM app.catalog_items WHERE item_id=%s FOR SHARE',
                               (job['item_id'],)).fetchone()
        lease = conn.execute('''SELECT j.content_version, m.target
            FROM app.embedding_jobs j
            JOIN app.embedding_models m USING(model_id)
            WHERE j.item_id=%s AND j.model_id=%s AND j.lease_token=%s AND j.lease_until>now() FOR UPDATE OF j''',
            (job['item_id'], job['model_id'], job['lease_token'])).fetchone()
        if not lease:
            return False
        if not current or current[1] != lease[1]:
            # Item was deleted or switched domain (product <-> food); discard the obsolete domain job.
            conn.execute('DELETE FROM app.embedding_jobs WHERE item_id=%s AND model_id=%s AND lease_token=%s',
                         (job['item_id'], job['model_id'], job['lease_token']))
            return False
        if current[0] != job['content_version'] or lease[0] != job['content_version']:
            return False
        _vectors().put(conn, job['model_id'], job['item_id'], job['content_version'], vector)
        conn.execute('DELETE FROM app.embedding_jobs WHERE item_id=%s AND model_id=%s AND lease_token=%s',
                     (job['item_id'], job['model_id'], job['lease_token']))
        return True


def retry(conn, job, error):
    # Bounded backoff; error class only, never raw text, credentials or user data.
    exhausted = job['attempts'] >= MAX_ATTEMPTS
    conn.execute('''UPDATE app.embedding_jobs SET lease_token=NULL,lease_until=NULL,last_error=%s,
        available_at=CASE WHEN %s THEN 'infinity'::timestamptz ELSE now() + (%s * interval '1 second') END
        WHERE item_id=%s AND model_id=%s AND lease_token=%s''',
        ((EXHAUSTED_PREFIX if exhausted else '') + type(error).__name__, exhausted,
         min(300, 2 ** min(job['attempts'], 8)), job['item_id'], job['model_id'], job['lease_token']))
    if exhausted:
        log.error('Embedding job parked after %d attempts (%s); run --requeue-failed after fixing the cause',
                  job['attempts'], type(error).__name__)


def _embed(encoder, jobs):
    """Embed a batch; on failure fall back per job so one bad item cannot block the others."""
    texts = [config.snapshot_text(job['snapshot']) for job in jobs]
    try:
        vectors = encoder.embed_documents(texts)
        if len(vectors) != len(jobs):
            raise ValueError('encoder returned a different number of vectors')
        return [(job, vector, None) for job, vector in zip(jobs, vectors)]
    except Exception as batch_error:
        if len(jobs) == 1:
            return [(jobs[0], None, batch_error)]
    results = []
    for job, text in zip(jobs, texts):
        try:
            results.append((job, encoder.embed_documents([text])[0], None))
        except Exception as error:
            results.append((job, None, error))
    return results


def once(conn, encoder=None, *, limit=BATCH_SIZE, models=None):
    jobs = claim_many(conn, limit, models)
    if not jobs:
        return False
    encoder = encoder or config.embedder()
    results = _embed(encoder, jobs)  # inference stays outside the transaction
    # One commit per batch instead of per item (#67: 5.3 -> 2.8 ms/item). finish() opens a nested
    # transaction, i.e. a savepoint, so one failing item rolls back alone and is retried below.
    with conn.transaction():
        for job, vector, error in results:
            if error is None:
                try:
                    finish(conn, job, vector)
                    continue
                except CONNECTION_LOST:
                    raise  # connection lost: leases expire and the outer loop reconnects
                except Exception as finish_error:
                    error = finish_error
            retry(conn, job, error)
            log.warning('Embedding job deferred (%s)', type(error).__name__)
    return True


def pending_counts(conn):
    models = [config.contract(k).model_id for k in ('product', 'food')]
    row = conn.execute('''SELECT count(*) FILTER (WHERE coalesce(last_error,'') NOT LIKE %s),
        count(*) FILTER (WHERE last_error LIKE %s)
        FROM app.embedding_jobs WHERE model_id=ANY(%s)''',
        (EXHAUSTED_PREFIX + '%', EXHAUSTED_PREFIX + '%', models)).fetchone()
    return row[0], row[1]


def requeue_failed(conn):
    models = [config.contract(k).model_id for k in ('product', 'food')]
    return conn.execute('''UPDATE app.embedding_jobs SET attempts=0,available_at=now(),last_error=NULL,
        lease_token=NULL,lease_until=NULL WHERE model_id=ANY(%s) AND last_error LIKE %s''',
        (models, EXHAUSTED_PREFIX + '%')).rowcount


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true', help='Owner-only contract registration and missing-vector backfill')
    parser.add_argument('--drain', action='store_true', help='Process ready jobs once; fail if any remain pending')
    parser.add_argument('--requeue-failed', action='store_true', help='Give parked (exhausted) jobs a fresh retry budget')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.bootstrap:
        with config.connect('owner') as conn:
            config.bootstrap(conn)
        print('Embedding contracts, indexes and backfill queue ready')
        return
    if args.requeue_failed:
        with config.connect() as conn:
            print(f'Requeued {requeue_failed(conn)} parked embedding jobs')
        return
    encoder = config.embedder()
    while True:
        try:
            with config.connect() as conn:
                models = serving_models(conn)
                while once(conn, encoder, models=models):
                    pass
                if args.drain:
                    pending, parked = pending_counts(conn)
                    if pending or parked:
                        raise SystemExit(f'{pending} embedding jobs pending/retrying, {parked} parked after '
                                         f'{MAX_ATTEMPTS} attempts')
                    print('All configured catalog embeddings are current')
                    return
        except (psycopg.Error, ValueError) as error:
            if args.drain:
                raise
            log.warning('Embedding worker unavailable (%s); retrying', type(error).__name__)
        time.sleep(2)


if __name__ == '__main__':
    main()
