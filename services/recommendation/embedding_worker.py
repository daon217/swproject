"""Durable catalog embedding worker; inference runs outside database transactions."""
import argparse
import gc
import logging
import os
import sys
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
# 할 일이 없을 때 모델(약 450MB)을 내려놓기까지 기다리는 시간. 0이면 계속 들고 있는다(#93).
IDLE_UNLOAD_SECONDS = max(0.0, float(os.getenv('EMBEDDING_IDLE_UNLOAD_SECONDS', '300')))


def serving_models(conn):
    return [config.validate(conn, k) for k in ('product', 'food')]


def park_lost(conn, models):
    """Jobs whose worker died while holding them already used up their attempts at claim time.
    Without this they would keep attempts>=MAX with no exhausted mark: never claimed again and
    invisible to --requeue-failed (#71). Park them the same way retry() parks a failing job."""
    parked = conn.execute('''UPDATE app.embedding_jobs SET available_at='infinity',lease_token=NULL,lease_until=NULL,
        last_error=%s WHERE model_id=ANY(%s) AND attempts>=%s AND lease_until IS NOT NULL AND lease_until<now()''',
        (EXHAUSTED_PREFIX + 'WorkerLost', models, MAX_ATTEMPTS)).rowcount
    if parked:
        log.error('%d embedding jobs parked after their worker was lost %d times; run --requeue-failed after fixing the cause',
                  parked, MAX_ATTEMPTS)
    return parked


def claim_many(conn, limit=BATCH_SIZE, models=None):
    models = models or serving_models(conn)
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cursor:
        park_lost(conn, models)
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


def has_ready(conn, models):
    """처리할 작업이 있는지만 가볍게 본다(모델을 올릴지 정할 때). claim_many와 같은 조건."""
    return conn.execute('''SELECT EXISTS(SELECT 1 FROM app.embedding_jobs WHERE model_id=ANY(%s)
        AND available_at<=now() AND attempts<%s AND (lease_until IS NULL OR lease_until<now()))''',
        (models, MAX_ATTEMPTS)).fetchone()[0]


def release_memory():
    """모델을 버린 뒤 파이썬·C 할당자가 잡고 있던 메모리를 운영체제에 돌려준다(리눅스 glibc)."""
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except (OSError, AttributeError):
        pass


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
    # 모델은 처리할 작업이 있을 때만 올리고, IDLE_UNLOAD_SECONDS 동안 일이 없으면 내려놓는다(#93).
    # 예전에는 시작하자마자 올려 두어 작업이 없어도 상시 약 600MB를 썼다. 크롤러가 10분마다 보내는 소량 작업은
    # 다시 올리는 몇 초면 충분하다.
    encoder = config.embedder() if args.drain else None
    last_work = time.monotonic()
    while True:
        try:
            with config.connect() as conn:
                models = serving_models(conn)
                if encoder is None and has_ready(conn, models):
                    log.info('Embedding jobs ready; loading the model')
                    encoder = config.embedder()
                    last_work = time.monotonic()
                if encoder is not None:
                    while once(conn, encoder, models=models):
                        last_work = time.monotonic()
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
        if encoder is not None and IDLE_UNLOAD_SECONDS and time.monotonic() - last_work > IDLE_UNLOAD_SECONDS:
            # 모델 객체만 버리면 PyTorch 라이브러리·할당자가 메모리를 돌려주지 않아 약 600MB가 그대로 남는다(실측).
            # 같은 프로세스 자리에서 작업자를 새로 시작해(execv) 모델 없는 상태(약 24MB)로 돌아간다. 컨테이너 재시작 아님.
            log.info('No embedding jobs for %ds; restarting without the model to free memory', int(IDLE_UNLOAD_SECONDS))
            encoder = None
            release_memory()
            os.execv(sys.executable, [sys.executable, '-m', 'services.recommendation.embedding_worker', *sys.argv[1:]])
        time.sleep(2)


if __name__ == '__main__':
    main()
