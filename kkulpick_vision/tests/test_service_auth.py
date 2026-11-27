from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
PATH = "/api/unknown-path-for-auth-check"  # 인증 미들웨어는 라우팅 전에 막는다


def test_missing_token_fails_closed(monkeypatch):
    monkeypatch.delenv("VISION_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("VISION_DEV_NO_AUTH", raising=False)
    assert client.get(PATH).status_code == 503


def test_dev_switch_opens_only_when_explicit(monkeypatch):
    monkeypatch.delenv("VISION_SERVICE_TOKEN", raising=False)
    monkeypatch.setenv("VISION_DEV_NO_AUTH", "1")
    assert client.get(PATH).status_code == 404


def test_token_required_when_configured(monkeypatch):
    monkeypatch.setenv("VISION_SERVICE_TOKEN", "t" * 32)
    monkeypatch.setenv("VISION_DEV_NO_AUTH", "1")  # 토큰이 있으면 개발 스위치보다 토큰이 우선
    assert client.get(PATH).status_code == 401
    assert client.get(PATH, headers={"Authorization": "Bearer " + "t" * 32}).status_code == 404
