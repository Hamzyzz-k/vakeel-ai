from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.session as session_module
from app.config import settings
from app.security import SessionGateMiddleware, issue_session, session_is_valid


def _gated_client(enabled: bool) -> TestClient:
    gated = FastAPI()
    gated.add_middleware(SessionGateMiddleware, enabled=enabled)

    @gated.post("/api/v1/chat")
    def chat():
        return {"ok": True}

    @gated.post("/api/v1/chat/stream")
    def chat_stream():
        return {"ok": True}

    @gated.get("/api/v1/health")
    def health():
        return {"ok": True}

    return TestClient(gated)


def test_gate_is_off_without_a_turnstile_secret():
    client = _gated_client(enabled=False)
    assert client.post("/api/v1/chat").status_code == 200


def test_gate_requires_a_valid_session_when_on():
    client = _gated_client(enabled=True)
    missing = client.post("/api/v1/chat")
    assert missing.status_code == 401
    assert missing.json()["code"] == "session_required"
    assert client.post("/api/v1/chat/stream").status_code == 401
    assert client.get("/api/v1/health").status_code == 200
    ok = client.post("/api/v1/chat", headers={"X-Session-Token": issue_session(60)})
    assert ok.status_code == 200


def test_expired_or_tampered_sessions_are_rejected():
    token = issue_session(60, now=1_000_000)
    assert session_is_valid(token, now=1_000_030)
    assert not session_is_valid(token, now=1_000_061)
    expires, signature = token.split(".")
    assert not session_is_valid(f"{int(expires) + 3600}.{signature}", now=1_000_030)
    assert not session_is_valid("not-a-token")
    assert not session_is_valid(None)


def test_session_endpoint_reports_off_when_not_configured(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "turnstile_secret_key", None)
    resp = TestClient(app).post("/api/v1/session", json={"turnstile_token": "anything"})
    assert resp.status_code == 200
    assert resp.json() == {"required": False, "session": None, "expires_in": None}


def test_session_endpoint_issues_a_session_only_for_a_passed_check(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "turnstile_secret_key", "test-secret")
    verdicts = {"good-token": True, "bad-token": False}
    monkeypatch.setattr(session_module, "verify_turnstile", lambda token, remote_ip: verdicts[token])
    client = TestClient(app)

    passed = client.post("/api/v1/session", json={"turnstile_token": "good-token"}).json()
    assert passed["required"] is True and session_is_valid(passed["session"])
    assert client.post("/api/v1/session", json={"turnstile_token": "bad-token"}).status_code == 403


def test_cors_allows_the_session_header():
    from app.main import app

    resp = TestClient(app).options(
        "/api/v1/chat",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type,x-session-token"},
    )
    assert resp.status_code == 200
    assert "x-session-token" in resp.headers["access-control-allow-headers"].lower()
