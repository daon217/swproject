"""Integration check against real queues/HTTP/storage. No crawls, model downloads or paid calls."""
import os
from pathlib import Path
from uuid import uuid4
import httpx
from redis import Redis
from .tasks import probe, storage_probe


def main():
    with httpx.Client(timeout=15, trust_env=False) as client:
        for name in ('api', 'vision', 'recommendation', 'collector'):
            response = client.get(f'http://{name}:8000/health')
            response.raise_for_status()
            assert response.json()['status'] == 'ok', name
        for name in ('vision', 'recommendation', 'collector'):
            denied = client.post(f'http://{name}:8000/internal/dev/probe', json={'correlation_id': str(uuid4())})
            assert denied.status_code == 401, name
        response = client.get('http://web:3000/api/dev/status')
        response.raise_for_status()
        assert response.json()['api']['status'] == 'ok'
        response = client.get('http://admin:3000/api/dev/status')
        response.raise_for_status()
        assert response.json()['api']['status'] == 'ok'
    for role in ('vision', 'recommendation', 'collector'):
        ident = str(uuid4())
        result = probe.apply_async(args=[role, ident], queue=role)
        try:
            data = result.get(timeout=60)
            assert data['correlation_id'] == ident and data['service'] == role
            assert data['business_ready'] is False
        finally:
            result.forget()
        print('OK real Celery queue ->', role, 'HTTP scaffold')
    ident = str(uuid4())
    path = Path('/var/lib/kkulpick/images') / (ident + '.bin')
    path.write_bytes(b'kkulpick-development-fixture')
    result = storage_probe.apply_async(args=[ident], queue='development')
    try:
        assert result.get(timeout=60)['storage'] == 'ok'
        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)
        result.forget()
    password = os.environ['REDIS_PASSWORD']
    with Redis(host='broker', password=password, decode_responses=True) as broker, Redis(host='cache', password=password, decode_responses=True) as cache:
        assert broker.config_get('maxmemory-policy')['maxmemory-policy'] == 'noeviction'
        assert cache.config_get('maxmemory-policy')['maxmemory-policy'] == 'allkeys-lru'
        assert broker.info('server')['run_id'] != cache.info('server')['run_id']
    print('OK separate broker/cache, shared private storage, web -> API; no business inference performed')


if __name__ == '__main__':
    main()
