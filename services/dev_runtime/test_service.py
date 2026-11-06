from fastapi.testclient import TestClient
from .service import make_app


def test_scaffold_never_claims_business_completion(monkeypatch):
    monkeypatch.setenv('WORKSPACE_TOKEN', 'a' * 64)
    client = TestClient(make_app('vision'))
    assert client.get('/health').json()['business_ready'] is False
    assert client.post('/internal/process').status_code == 501
    payload = {'correlation_id': 'f504f20b-7f69-44e4-bcaf-bc8cd99bf0cc'}
    assert client.post('/internal/dev/probe', json=payload).status_code == 401
    assert client.post('/internal/dev/probe', json=payload, headers={'Authorization': 'Bearer wrong'}).status_code == 401
    response = client.post('/internal/dev/probe', json=payload, headers={'Authorization': 'Bearer ' + 'a' * 64})
    assert response.status_code == 200
    assert response.json()['correlation_id'] == payload['correlation_id']
    assert response.json()['business_ready'] is False


def test_unconfigured_token_denies_access(monkeypatch):
    monkeypatch.delenv('WORKSPACE_TOKEN', raising=False)
    client = TestClient(make_app('collector'))
    response = client.post('/internal/dev/probe', json={'correlation_id':'f504f20b-7f69-44e4-bcaf-bc8cd99bf0cc'}, headers={'Authorization':'Bearer '})
    assert response.status_code == 401
