"""
FastAPI entrypoint. Phase 0: health check only. Real routers get mounted
here as each phase lands (api/chat.py, api/research.py, ...).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.research import router as research_router
from app.config import settings
from app.security import RateLimitMiddleware, SecurityHeadersMiddleware

app = FastAPI(
    title="Vakeel AI",
    description="Agentic, citation-verified legal research assistant for Indian law.",
    version="0.2.0",
    docs_url=None if settings.deploy_mode == "CLOUD" else "/docs",
    redoc_url=None if settings.deploy_mode == "CLOUD" else "/redoc",
    openapi_url=None if settings.deploy_mode == "CLOUD" else "/openapi.json",
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


app.include_router(chat_router)
app.include_router(research_router)
app.include_router(documents_router)


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "deploy_mode": settings.deploy_mode,
        "version": app.version,
    }
