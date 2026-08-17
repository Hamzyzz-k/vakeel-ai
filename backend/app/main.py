"""
FastAPI entrypoint. Phase 0: health check only. Real routers get mounted
here as each phase lands (api/chat.py, api/research.py, ...).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.research import router as research_router
from app.config import settings

app = FastAPI(
    title="Vakeel AI",
    description="Agentic, citation-verified legal research assistant for Indian law.",
    version="0.0.1-phase0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat_router)
app.include_router(research_router)
app.include_router(documents_router)


@app.get("/api/v1/health")
def health() -> dict:
    return {
        "status": "ok",
        "deploy_mode": settings.deploy_mode,
        "phase": "0 - recon and skeleton",
    }
