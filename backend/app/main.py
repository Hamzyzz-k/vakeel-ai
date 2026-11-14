"""
FastAPI entrypoint. Phase 0: health check only. Real routers get mounted
here as each phase lands (api/chat.py, api/research.py, ...).
"""
from __future__ import annotations

import logging
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.chat import router as chat_router
from app.api.coverage import router as coverage_router
from app.api.documents import router as documents_router
from app.api.research import router as research_router
from app.config import settings
from app.api.session import router as session_router
from app.security import DailyQuotaMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware, SessionGateMiddleware

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="Vakeel AI",
    description="Agentic, citation-verified legal research assistant for Indian law.",
    version="0.2.0",
    docs_url=None if settings.deploy_mode == "CLOUD" else "/docs",
    redoc_url=None if settings.deploy_mode == "CLOUD" else "/redoc",
    openapi_url=None if settings.deploy_mode == "CLOUD" else "/openapi.json",
)

app.add_middleware(SecurityHeadersMiddleware)
# Added before (so inside) the per-minute limiter: requests that limiter
# rejects never spend the daily allowance.
app.add_middleware(
    DailyQuotaMiddleware,
    per_client=settings.daily_chat_limit_per_client,
    total=settings.daily_chat_budget,
    trusted_proxy_hops=settings.trusted_proxy_hops,
)
# Between the two limiters: requests without a passed bot check are
# turned away before they can spend the daily allowance.
app.add_middleware(SessionGateMiddleware, enabled=bool(settings.turnstile_secret_key))
app.add_middleware(
    RateLimitMiddleware,
    max_requests=settings.rate_limit_requests,
    window_seconds=settings.rate_limit_window_seconds,
    trusted_proxy_hops=settings.trusted_proxy_hops,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-Token"],
)


@app.on_event("startup")
def _warm_retrieval() -> None:
    # Loading the embedder takes ~13s on CPU, and even without it the first
    # searches after a start were slow (retrieval 3.3s, then 1.3s, 0.7s,
    # then 0.3s warm) while SQLite pages and the FTS index came off disk.
    # Run one throwaway retrieval in the background so the first user
    # doesn't pay for it; /health answers immediately meanwhile.
    def warm() -> None:
        from app.api.chat import _get_repo
        from app.pipeline.graph import PRODUCT_VECTOR_INDEX, run_retrieval
        from app.pipeline.state import LegalQueryState
        from app.retrieval.vectors import embed_texts

        try:
            if settings.enable_vector_retrieval and PRODUCT_VECTOR_INDEX.exists():
                PRODUCT_VECTOR_INDEX.load()
                embed_texts(["warm-up"])
            run_retrieval(LegalQueryState(user_query="compensation for breach of contract by the seller"), _get_repo())
        except Exception:  # noqa: BLE001 -- warm-up is an optimisation; a failure must not stop the app
            logger.warning("Retrieval warm-up failed", exc_info=True)

    threading.Thread(target=warm, name="retrieval-warmup", daemon=True).start()


app.include_router(chat_router)
app.include_router(coverage_router)
app.include_router(research_router)
app.include_router(documents_router)
app.include_router(session_router)


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "deploy_mode": settings.deploy_mode,
        "version": app.version,
    }
