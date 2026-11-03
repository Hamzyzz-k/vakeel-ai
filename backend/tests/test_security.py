from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import app
from app.security import RateLimitMiddleware, client_ip


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


def _limited_client(trusted_proxy_hops: int) -> TestClient:
    limited_app = FastAPI()
    limited_app.add_middleware(
        RateLimitMiddleware, max_requests=2, window_seconds=60, trusted_proxy_hops=trusted_proxy_hops,
    )

    @limited_app.post("/api/v1/chat")
    def chat():
        return {"ok": True}

    return TestClient(limited_app)


def test_spoofed_forwarded_entries_do_not_open_new_buckets():
    client = _limited_client(trusted_proxy_hops=1)
    # The client controls everything left of the proxy's own entry.
    for spoofed in ("1.1.1.1", "2.2.2.2"):
        assert client.post("/api/v1/chat", headers={"X-Forwarded-For": f"{spoofed}, 203.0.113.9"}).status_code == 200
    blocked = client.post("/api/v1/chat", headers={"X-Forwarded-For": "3.3.3.3, 203.0.113.9"})
    assert blocked.status_code == 429


def test_different_clients_behind_proxy_get_separate_buckets():
    client = _limited_client(trusted_proxy_hops=1)
    for _ in range(2):
        assert client.post("/api/v1/chat", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200
    assert client.post("/api/v1/chat", headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 429
    assert client.post("/api/v1/chat", headers={"X-Forwarded-For": "198.51.100.4"}).status_code == 200


def test_forwarded_header_ignored_without_trusted_proxies():
    client = _limited_client(trusted_proxy_hops=0)
    for address in ("203.0.113.9", "198.51.100.4"):
        assert client.post("/api/v1/chat", headers={"X-Forwarded-For": address}).status_code == 200
    assert client.post("/api/v1/chat", headers={"X-Forwarded-For": "192.0.2.1"}).status_code == 429


def test_client_ip_uses_nth_entry_from_the_right():
    scope = {"client": ("10.0.0.1", 1234), "headers": [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.9, 10.0.0.2")]}
    assert client_ip(scope, 0) == "10.0.0.1"
    assert client_ip(scope, 1) == "10.0.0.2"
    assert client_ip(scope, 2) == "203.0.113.9"
    assert client_ip({"client": ("10.0.0.1", 1), "headers": []}, 1) == "10.0.0.1"


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
