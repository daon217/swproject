"""Verify the selected team's actual development app, including denial without a service token."""
import importlib
import os
from pathlib import Path
import sys
from uuid import uuid4
from fastapi.testclient import TestClient

role = sys.argv[1]
if role not in ('vision', 'recommendation', 'collector'):
    raise SystemExit('Unknown adapter')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['WORKSPACE_TOKEN'] = 'test-only-' + 'a' * 64
app = importlib.import_module(f'services.{role}.devapp').app
with TestClient(app) as client:
    health = client.get('/health').json()
    assert health['service'] == role and health['business_ready'] is False
    response = client.post('/internal/dev/probe', json={'correlation_id': str(uuid4())})
    assert response.status_code == 401
    assert client.post('/internal/process').status_code == 501
print(role, 'development adapter and authorization checks passed')
