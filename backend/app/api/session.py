"""
Bot-check sessions (Cloudflare Turnstile, free tier).

The browser solves a Turnstile challenge, posts the resulting token here,
and gets back a signed session token (app.security.issue_session) that
SessionGateMiddleware requires on chat and upload while TURNSTILE_SECRET_KEY
is set. One check covers a whole session instead of one per question.
"""
from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.security import client_ip, issue_session

router = APIRouter(prefix="/api/v1", tags=["session"])
logger = logging.getLogger("uvicorn.error")

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class SessionRequest(BaseModel):
    turnstile_token: str = Field(min_length=1, max_length=4096)


class SessionResponse(BaseModel):
    required: bool
    session: str | None = None
    expires_in: int | None = None


def verify_turnstile(token: str, remote_ip: str | None) -> bool:
    data = {"secret": settings.turnstile_secret_key, "response": token}
    if remote_ip and remote_ip != "unknown":
        data["remoteip"] = remote_ip
    try:
        response = httpx.post(SITEVERIFY_URL, data=data, timeout=10.0)
        response.raise_for_status()
        result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Turnstile verification unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="Verification is temporarily unavailable. Try again.") from exc
    if not result.get("success"):
        logger.info("Turnstile rejected a token: %s", result.get("error-codes"))
    return bool(result.get("success"))


@router.post("/session", response_model=SessionResponse)
def create_session(req: SessionRequest, request: Request) -> SessionResponse:
    if not settings.turnstile_secret_key:
        return SessionResponse(required=False)
    if not verify_turnstile(req.turnstile_token, client_ip(request.scope, settings.trusted_proxy_hops)):
        raise HTTPException(status_code=403, detail="Verification failed. Please try again.")
    return SessionResponse(
        required=True,
        session=issue_session(settings.session_ttl_seconds),
        expires_in=settings.session_ttl_seconds,
    )
