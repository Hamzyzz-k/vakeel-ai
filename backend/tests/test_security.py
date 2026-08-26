from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import app
from app.security import RateLimitMiddleware


def test_api_responses_include_security_headers():
    response = TestClient(app).get("/api/v1/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert "camera=()" in response.headers["permissions-policy"]


def test_unknown_host_is_rejected():
    response = TestClient(app).get("/api/v1/health", headers={"Host": "attacker.example"})
    assert response.status_code == 400


def test_cors_allows_configured_local_origin_only():
    client = TestClient(app)
    allowed = client.options(
        "/api/v1/chat",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    blocked = client.options(
        "/api/v1/chat",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "POST"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_expensive_post_endpoints_are_rate_limited():
    limited_app = FastAPI()
    limited_app.add_middleware(RateLimitMiddleware, max_requests=2, window_seconds=60)

    @limited_app.post("/api/v1/chat")
    def chat():
        return {"ok": True}

    client = TestClient(limited_app)
    assert client.post("/api/v1/chat").status_code == 200
    assert client.post("/api/v1/chat").status_code == 200
    blocked = client.post("/api/v1/chat")

    assert blocked.status_code == 429
    assert blocked.headers["retry-after"]
    assert blocked.json()["detail"] == "Too many requests. Try again shortly."


def test_cloud_mode_requires_explicit_origins_and_hosts(monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "CLOUD")
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("TRUSTED_HOSTS", raising=False)

    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings()


def test_cloud_mode_accepts_explicit_restricted_hosts(monkeypatch):
    monkeypatch.setenv("DEPLOY_MODE", "CLOUD")
    monkeypatch.setenv("CORS_ORIGINS", "https://vakeel.example")
    monkeypatch.setenv("TRUSTED_HOSTS", "api.vakeel.example")

    production = Settings()

    assert production.cors_origins == ("https://vakeel.example",)
    assert production.trusted_hosts == ("api.vakeel.example",)
    assert production.expose_provider_errors is False
