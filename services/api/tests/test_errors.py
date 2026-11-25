from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from kkulpick.api import app


def test_database_error_does_not_expose_credentials(monkeypatch):
    class Broken:
        def connect(self):
            raise OperationalError('secret SQL password=do-not-return', {}, Exception('private detail'))
    monkeypatch.setattr(app.state, 'engine', Broken(), raising=False)
    response = TestClient(app).get('/health')
    assert response.status_code == 503
    assert response.json()['error']['code'] == 'DATABASE_UNAVAILABLE'
    assert response.json()['error']['retryable']
    assert response.headers['Retry-After'] == '3'
    assert 'do-not-return' not in response.text and 'private detail' not in response.text


def test_member_cors_idempotency_header():
    response = TestClient(app).options('/v2/me/subscriptions', headers={
        'Origin':'http://localhost:3000', 'Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'authorization,content-type,idempotency-key'})
    assert response.status_code == 200


def test_private_support_and_analysis_errors_cannot_be_cached():
    client = TestClient(app)
    for path in ['/v2/support/conversations', '/analyses/00000000-0000-0000-0000-000000000001']:
        response = client.get(path)
        assert response.status_code == 401
        assert response.headers['Cache-Control'] == 'no-store'
