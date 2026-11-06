import json
from datetime import datetime, UTC
from pathlib import Path
import pytest
from pydantic import ValidationError
from kkulpick.models import Observation


def fixture():
    return dict(json.loads((Path(__file__).parents[1]/"fixtures"/"offer.json").read_text(encoding="utf8")),
                observation_key="unit",observed_at=datetime.now(UTC).isoformat())


@pytest.mark.parametrize("patch",[{"price":1.1},{"price":"-5"},{"currency":None},{"field_presence":["price"]},
                                  {"url":"https://localhost/private"},{"schema_version":3},{"unexpected":True}])
def test_reject_invalid(patch):
    with pytest.raises(ValidationError):
        Observation(**(fixture()|patch))


def test_valid():
    assert Observation(**fixture()).variant_key=="blue-1l"


def test_browser_public_api_preflight_and_untrusted_origin():
    from fastapi.testclient import TestClient
    from kkulpick.api import app
    # No DB lifespan needed: middleware handles preflight before a route executes.
    client = TestClient(app)
    headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "authorization,content-type"}
    assert client.options("/analyses", headers=headers).status_code == 200
    assert client.options("/analyses", headers=headers | {"Origin": "https://untrusted.example"}).status_code == 400


@pytest.mark.parametrize("with_length", [True, False])
def test_body_limit_rejects_oversized_payload_before_application(with_length):
    import asyncio
    from kkulpick.limits import RequestBodyLimit
    calls = []
    messages = iter([{'type': 'http.request', 'body': b'x' * 40000, 'more_body': True},
                     {'type': 'http.request', 'body': b'x' * 30000, 'more_body': False}])

    async def receive():
        return next(messages)

    async def send(message):
        calls.append(message)

    async def application(*args):
        raise AssertionError('oversized body reached application')

    scope = {'type': 'http', 'method': 'POST', 'headers': [(b'content-length', b'70000')] if with_length else []}
    asyncio.run(RequestBodyLimit(application)(scope, receive, send))
    assert calls[0]['status'] == 413


def test_body_limit_preserves_valid_json():
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient
    from kkulpick.limits import RequestBodyLimit
    app = FastAPI()
    app.add_middleware(RequestBodyLimit)

    @app.post('/echo')
    async def echo(request: Request):
        return await request.json()

    response = TestClient(app).post('/echo', json={'name': '상품'})
    assert response.status_code == 200 and response.json() == {'name': '상품'}
