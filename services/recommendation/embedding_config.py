"""One immutable embedding space shared by indexing and HTTP query encoding."""
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
import os
import re

try:
    import psycopg
except ImportError:  # pragma: no cover - per-project unit CI runs without psycopg
    psycopg = None

from .adapters.postgres import _vectors
from .embedders import HashEmbedder, SentenceTransformerEmbedder

MODEL = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
# Pinned upstream weights, not a moving branch. See docs/embedding-pipeline.md.
REVISION = 'e8f8c211226b894fcb81acc59f3b34ba3efd5f42'
# v2 adds brand and category (migration 0011 puts them in job snapshots and content_version).
# Changing this text yields a new immutable contract id; bootstrap retires the previous one.
TEMPLATE = 'catalog-v2: name | brand | category | kind | description (omit empty fields)'
SNAPSHOT_FIELDS = ('name', 'brand', 'category', 'kind', 'description')


def settings():
    backend = os.getenv('RECO_EMBEDDER', 'st')
    if backend == 'hash':
        return 'hash-ngram-384', 'hash-ngram-v1', 384
    if backend != 'st':
        raise ValueError('RECO_EMBEDDER must be st or hash (test only)')
    revision = os.getenv('RECO_MODEL_REVISION', REVISION)
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('RECO_MODEL_REVISION must be an immutable commit SHA')
    return os.getenv('RECO_MODEL_NAME', MODEL), revision, int(os.getenv('RECO_MODEL_DIMENSIONS', '384'))


def contract(kind):
    if kind not in ('product', 'food'):
        raise ValueError('unsupported embedding domain')
    name, revision, dimensions = settings()
    values = dict(target=kind, encoder_name=name, revision=revision, dimensions=dimensions,
                  input_template=TEMPLATE, query_prefix='', document_prefix='', normalize=True)
    digest = hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()[:24]
    return _vectors().Contract(model_id=f'catalog-{kind}-{digest}', **values)


def snapshot_text(snapshot):
    return ' | '.join(str(snapshot[k]) for k in SNAPSHOT_FIELDS if snapshot.get(k))


@lru_cache(maxsize=1)
def embedder():
    name, revision, dimensions = settings()
    result = HashEmbedder() if name == 'hash-ngram-384' else SentenceTransformerEmbedder(name, revision=revision)
    if result.name != name or result.dimensions != dimensions:
        raise ValueError('encoder does not match the configured contract')
    return result


def connect(role='app'):
    if role not in ('app', 'owner'):
        raise ValueError('invalid database role')
    if psycopg is None:
        raise OSError('psycopg is not installed')
    return psycopg.connect(host=os.getenv('DB_HOST', '127.0.0.1'), port=os.getenv('DB_PORT', '5433'),
        dbname='kkulpick_catalog', user='kkulpick_catalog_' + role,
        password=os.environ['CATALOG_PASSWORD'], autocommit=True, connect_timeout=5)


def validate(conn, kind):
    expected = asdict(contract(kind))
    row = conn.execute('SELECT to_jsonb(m) FROM app.embedding_models m WHERE model_id=%s',
                       (expected['model_id'],)).fetchone()
    if not row or not row[0]['is_serving'] or any(row[0][k] != v for k, v in expected.items()):
        raise ValueError('embedding contract missing, inactive or incompatible; run bootstrap')
    return expected['model_id']


def bootstrap(conn):
    """Owner only; immutable contracts, matching HNSW indexes and backfill in one transaction."""
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('catalog-embedding-bootstrap',0))")
        # Serialize with catalog writes while the activation trigger snapshots existing rows.
        conn.execute('LOCK TABLE app.catalog_items IN SHARE ROW EXCLUSIVE MODE')
        for kind in ('product', 'food'):
            model = contract(kind)
            row = conn.execute('SELECT to_jsonb(m) FROM app.embedding_models m WHERE model_id=%s',
                               (model.model_id,)).fetchone()
            if row:
                if any(row[0][k] != v for k, v in asdict(model).items()):
                    raise ValueError('existing embedding contract differs')
            else:
                _vectors().register(conn, model)
            conn.execute('UPDATE app.embedding_models SET is_serving=true WHERE model_id=%s', (model.model_id,))
            # One serving contract per domain: otherwise every catalog write keeps enqueueing jobs for
            # superseded contracts (e.g. catalog-v1 after the v2 template) that no worker processes.
            conn.execute('''UPDATE app.embedding_models SET is_serving=false
                WHERE target=%s AND is_serving AND model_id<>%s''', (kind, model.model_id))
            conn.execute('''DELETE FROM app.embedding_jobs j USING app.embedding_models m
                WHERE j.model_id=m.model_id AND m.target=%s AND NOT m.is_serving''', (kind,))
