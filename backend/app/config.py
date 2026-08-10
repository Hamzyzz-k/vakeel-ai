"""
Central configuration for Vakeel AI.

Everything that differs between a local laptop run and a future cloud
deployment lives here, behind one switch. Don't add a second place that
reads os.environ for the same thing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent
# .env lives at the project root (vakeelAI/.env), one level above backend/ --
# matches .env.example's location, and keeps one shared file for both
# backend and any future frontend build-time env needs.
load_dotenv(BACKEND_ROOT.parent / ".env")
DATA_DIR = BACKEND_ROOT / "data"
CORPUS_DB_PATH = DATA_DIR / "corpus.db"
RAW_DATA_DIR = DATA_DIR / "raw"
EVAL_REPORTS_DIR = DATA_DIR / "eval_reports"
CACHE_DB_PATH = DATA_DIR / "llm_cache.db"


def _env_bool(name: str, default: bool) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # LOCAL is the only supported mode right now (user's explicit choice).
    # CLOUD is scaffolded but inert until Phase 10. Never enable billing on
    # the GCP project when wiring CLOUD up later -- it permanently kills the
    # Gemini free tier for that project (verified during planning).
    deploy_mode: str = field(default_factory=lambda: os.environ.get("DEPLOY_MODE", "LOCAL"))

    gemini_api_key: str | None = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))

    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.2:3b"))

    # Prefer Gemini when a key is present and quota allows; fall back to
    # Ollama on 429/error. Eval harness overrides this to force Ollama --
    # 500 questions x 3 calls would burn the whole daily Gemini quota.
    llm_provider_order: tuple[str, ...] = ("gemini", "ollama")

    use_gpu: bool = field(default_factory=lambda: _env_bool("USE_GPU", True))
    embedding_model: str = field(
        default_factory=lambda: os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    )
    reranker_model: str = field(
        default_factory=lambda: os.environ.get("RERANKER_MODEL", "BAAI/bge-reranker-base")
    )
    nli_model: str = field(
        default_factory=lambda: os.environ.get("NLI_MODEL", "cross-encoder/nli-deberta-v3-small")
    )

    def __post_init__(self) -> None:
        if self.deploy_mode not in {"LOCAL", "CLOUD"}:
            raise ValueError(f"DEPLOY_MODE must be LOCAL or CLOUD, got {self.deploy_mode!r}")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
