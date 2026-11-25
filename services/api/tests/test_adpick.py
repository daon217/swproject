"""Adpick conversion endpoint without a database or the real upstream."""
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from kkulpick import adpick
from kkulpick.errors import install_errors

URL = 'https://shop.example.com/goods/123?opt=1'


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('ADPICK_API_KEY', 'test-key-not-real')
    monkeypatch.setenv('ADPICK_API_URL', 'https://adpick.example.test/convert')
    adpick._cache.clear()
    slots = []

    async def no_limit(req, bucket, limit, code):
        slots.append((bucket.split(':')[0], limit))
    monkeypatch.setattr(adpick, '_take_slot', no_limit)
    app = FastAPI()
    install_errors(app)
    app.include_router(adpick.router)
    c = TestClient(app)
    c.slots = slots
    yield c
    adpick._cache.clear()


def post(client, url=URL):
    return client.post('/v2/links/convert', json={'url': url})


def test_converts_and_caches(client, monkeypatch):
    calls = []
    def upstream(url, key, endpoint):
        calls.append((url, key, endpoint))
        return 'https://link.adpick.example.test/abc'
    monkeypatch.setattr(adpick, 'call_upstream', upstream)
    first = post(client)
    assert first.status_code == 200, first.text
    assert first.json()['data'] == {'original_url': URL, 'affiliate_url': 'https://link.adpick.example.test/abc', 'cached': False}
    assert post(client).json()['data']['cached'] is True
    assert len(calls) == 1 and calls[0][1] == 'test-key-not-real'
    # Per-client budget first, then the shared 60/min upstream budget; cache hits use neither.
    assert client.slots == [('adpick-client', 10), ('adpick-upstream', 60)]
    assert 'test-key-not-real' not in first.text


def test_unsupported_url_is_400_and_negative_cached(client, monkeypatch):
    calls = []
    def upstream(url, key, endpoint):
        calls.append(url)
        raise adpick.UpstreamUnsupported()
    monkeypatch.setattr(adpick, 'call_upstream', upstream)
    for _ in range(2):
        r = post(client)
        assert r.status_code == 400 and r.json()['error']['code'] == 'AFFILIATE_URL_UNSUPPORTED'
        assert r.json()['error']['retryable'] is False
    assert len(calls) == 1


@pytest.mark.parametrize('status,expected,code', [
    (429, 429, 'AFFILIATE_LINK_BUSY'),
    (500, 503, 'AFFILIATE_LINK_UNAVAILABLE'),
    (401, 503, 'AFFILIATE_LINK_NOT_CONFIGURED'),
    ('TimeoutError', 503, 'AFFILIATE_LINK_UNAVAILABLE'),
])
def test_upstream_failures_are_mapped_and_not_cached(client, monkeypatch, status, expected, code):
    def upstream(url, key, endpoint):
        raise adpick.UpstreamUnavailable(status, '30' if status == 429 else None)
    monkeypatch.setattr(adpick, 'call_upstream', upstream)
    r = post(client)
    assert r.status_code == expected and r.json()['error']['code'] == code
    if status == 429:
        assert r.headers['Retry-After'] == '30'
    assert URL not in adpick._cache


def test_rate_limit_rejects_before_upstream(client, monkeypatch):
    async def limited(req, bucket, limit, code):
        raise HTTPException(429, code, headers={'Retry-After': '12'})
    monkeypatch.setattr(adpick, '_take_slot', limited)
    monkeypatch.setattr(adpick, 'call_upstream', lambda *a: pytest.fail('upstream must not be called'))
    r = post(client)
    assert r.status_code == 429 and r.headers['Retry-After'] == '12'
    assert r.json()['error']['code'] == 'AFFILIATE_LINK_RATE_LIMITED'


@pytest.mark.parametrize('bad', ['ftp://shop.example.com/a', 'https://user:pw@shop.example.com/a',
                                 'http://127.0.0.1/admin', 'https://192.168.0.10/x', 'not a url'])
def test_rejects_non_public_urls(client, bad):
    assert post(client, bad).status_code == 422


def test_not_configured(client, monkeypatch):
    monkeypatch.delenv('ADPICK_API_KEY')
    r = post(client)
    assert r.status_code == 503 and r.json()['error']['code'] == 'AFFILIATE_LINK_NOT_CONFIGURED'


@pytest.mark.parametrize('payload,link', [
    ({'data': {'url': 'https://a.test/1'}}, 'https://a.test/1'),
    ({'deeplink': 'https://a.test/2'}, 'https://a.test/2'),
    ({'result': 'https://a.test/3'}, 'https://a.test/3'),
    ('https://a.test/4', 'https://a.test/4'),
    ({'data': {'url': 'javascript:alert(1)'}}, None),
    ({'ok': True}, None),
])
def test_extract_link(payload, link):
    assert adpick._extract_link(payload) == link
