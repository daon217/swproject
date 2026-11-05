import os
from pathlib import Path
from uuid import UUID
import httpx
from celery import Celery
from redis import Redis

password = os.environ['REDIS_PASSWORD']
app = Celery('kkulpick-development', broker=f'redis://:{password}@broker:6379/0',
             backend=f'redis://:{password}@cache:6379/1')
app.conf.update(task_serializer='json', result_serializer='json', accept_content=['json'],
                result_expires=300, worker_prefetch_multiplier=1,
                task_time_limit=45, task_soft_time_limit=40,
                broker_transport_options={'visibility_timeout': 120},
                task_default_queue='development', broker_connection_retry_on_startup=True)


@app.task(name='development.probe')
def probe(role: str, correlation_id: str):
    if role not in ('vision', 'recommendation', 'collector'):
        raise ValueError('unknown role')
    ident = str(UUID(correlation_id))
    with httpx.Client(timeout=10, trust_env=False) as client:
        response = client.post(f'http://{role}:8000/internal/dev/probe',
                               headers={'Authorization': 'Bearer ' + os.environ['WORKSPACE_TOKEN']},
                               json={'correlation_id': ident})
        response.raise_for_status()
    return response.json()


@app.task(name='development.storage_probe')
def storage_probe(correlation_id: str):
    ident = str(UUID(correlation_id))
    path = Path('/var/lib/kkulpick/images') / (ident + '.bin')
    # The smoke client creates only this non-personal fixture, never a screenshot.
    if path.read_bytes() != b'kkulpick-development-fixture':
        raise ValueError('shared storage mismatch')
    path.unlink()
    cache = Redis(host='cache', password=password, decode_responses=True)
    key = 'development:probe:' + ident
    try:
        cache.set(key, 'ok', ex=30)
        if cache.get(key) != 'ok':
            raise ValueError('cache mismatch')
    finally:
        cache.delete(key)
        cache.close()
    return {'storage': 'ok', 'cache': 'ok', 'fixture_only': True}
