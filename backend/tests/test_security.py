from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import app
from datetime import datetime, timedelta, timezone

from app.security import DailyQuotaMiddleware, RateLimitMiddleware, client_ip


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


class _Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 8, 23, 59, 30, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def _quota_client(per_client: int, total: int, clock) -> TestClient:
    quota_app = FastAPI()
    quota_app.add_middleware(DailyQuotaMiddleware, per_client=per_client, total=total, trusted_proxy_hops=1, clock=clock)

    @quota_app.post("/api/v1/chat")
    def chat():
        return {"ok": True}

    @quota_app.post("/api/v1/documents/upload")
    def upload():
        return {"ok": True}

    return TestClient(quota_app)


def _ask(client, address):
    return client.post("/api/v1/chat", headers={"X-Forwarded-For": address})


def test_daily_quota_caps_each_client_until_the_utc_day_changes():
    clock = _Clock()
    client = _quota_client(per_client=2, total=0, clock=clock)
    assert _ask(client, "203.0.113.9").status_code == 200
    assert _ask(client, "203.0.113.9").status_code == 200
    blocked = _ask(client, "203.0.113.9")
    assert blocked.status_code == 429
    assert "today's limit of 2 questions" in blocked.json()["detail"]
    assert blocked.headers["retry-after"] == "30"  # seconds to midnight UTC
    assert _ask(client, "198.51.100.4").status_code == 200

    clock.now += timedelta(minutes=1)
    assert _ask(client, "203.0.113.9").status_code == 200


def test_daily_budget_caps_all_clients_together():
    client = _quota_client(per_client=0, total=2, clock=_Clock())
    assert _ask(client, "203.0.113.9").status_code == 200
    assert _ask(client, "198.51.100.4").status_code == 200
    blocked = _ask(client, "192.0.2.1")
    assert blocked.status_code == 429
    assert "free usage limit" in blocked.json()["detail"]


def test_daily_quota_ignores_other_paths_and_rejected_requests_cost_nothing():
    client = _quota_client(per_client=1, total=2, clock=_Clock())
    for _ in range(3):
        assert client.post("/api/v1/documents/upload").status_code == 200
    assert _ask(client, "203.0.113.9").status_code == 200
    for _ in range(3):
        assert _ask(client, "203.0.113.9").status_code == 429
    # The blocked retries above didn't spend the shared budget.
    assert _ask(client, "198.51.100.4").status_code == 200


def test_daily_quota_off_by_default_outside_cloud(monkeypatch):
    for name in ("DEPLOY_MODE", "DAILY_CHAT_LIMIT_PER_CLIENT", "DAILY_CHAT_BUDGET", "LLM_CACHE_TTL_DAYS"):
        monkeypatch.delenv(name, raising=False)
    local = Settings()
    assert (local.daily_chat_limit_per_client, local.daily_chat_budget, local.llm_cache_ttl_days) == (0, 0, 0)


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
