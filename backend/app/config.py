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
    # gemini-2.5-flash was retired from the legacy generateContent path for
    # new callers (confirmed live, 2026-08-17: 404 NOT_FOUND, "no longer
    # available to new users"). gemini-3.6-flash is the current stable
    # balanced model on the Interactions API this provider now calls.
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"))
    gemini_read_timeout: float = field(default_factory=lambda: float(os.environ.get("GEMINI_READ_TIMEOUT", "45")))
    gemini_max_retries: int = field(default_factory=lambda: int(os.environ.get("GEMINI_MAX_RETRIES", "1")))
    # Sent as generation_config.thinking_level; empty omits it. Measured on
    # a one-sentence prompt: default 7.6s, "low" 6.9s, "minimal" 4.6s.
    gemini_thinking_level: str = field(default_factory=lambda: os.environ.get("GEMINI_THINKING_LEVEL", "low").strip())

    groq_api_key: str | None = field(default_factory=lambda: os.environ.get("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"))
    groq_read_timeout: float = field(default_factory=lambda: float(os.environ.get("GROQ_READ_TIMEOUT", "30")))
    groq_max_retries: int = field(default_factory=lambda: int(os.environ.get("GROQ_MAX_RETRIES", "1")))
    # gpt-oss models accept low | medium | high. The pipeline's prompts are
    # summarisation over supplied text, not open-ended reasoning, so "low"
    # trims latency and tokens; the citation checks still gate every
    # sentence of whatever comes back. Empty omits it.
    groq_reasoning_effort: str = field(default_factory=lambda: os.environ.get("GROQ_REASONING_EFFORT", "low").strip())
    # Upper bound on one reply, reasoning included. The longest measured
    # output (a Research note) is ~1,800 characters, well under this; the
    # cap only stops a runaway reply from stretching latency and spending
    # the 200K tokens/day free budget.
    groq_max_completion_tokens: int = field(
        default_factory=lambda: int(os.environ.get("GROQ_MAX_COMPLETION_TOKENS", "2048"))
    )

    ollama_host: str = field(default_factory=lambda: os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    ollama_model: str = field(default_factory=lambda: os.environ.get("OLLAMA_MODEL", "llama3.2:3b"))

    # Groq first: measured on the same live queries, a full Advice answer
    # took ~5s on Groq vs ~30s on Gemini (Research: ~6s vs 26-56s), and
    # retrieval plus verification add well under a second. Eval harness
    # overrides this to force Ollama -- 500 questions x 3 calls would burn a
    # whole daily free quota.
    # qwen3.8-27b on Groq is a backup for when gpt-oss-120b's daily quota is
    # spent (quotas are per model), ahead of Gemini's 20 requests/day. Not
    # the primary: on 10 everyday questions it pasted statute text verbatim
    # twice, once from an irrelevant section (app/eval/lay_quality.py).
    llm_provider_order: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            provider.strip().lower()
            for provider in os.environ.get("LLM_PROVIDER_ORDER", "groq,groq:qwen/qwen3.8-27b,gemini,ollama").split(",")
            if provider.strip()
        )
    )

    # Comma-separated list; defaults to the Vite dev server only. Production
    # (Vercel frontend calling this backend directly, e.g. during manual
    # testing of the Render URL) adds its own origin via the CORS_ORIGINS
    # env var rather than a hardcoded domain baked into this file.
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in os.environ.get(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"
            ).split(",") if o.strip()
        )
    )
    trusted_hosts: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            host.strip()
            for host in os.environ.get("TRUSTED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            if host.strip()
        )
    )
    rate_limit_requests: int = field(
        default_factory=lambda: int(os.environ.get("RATE_LIMIT_REQUESTS", "20" if os.environ.get("DEPLOY_MODE") == "CLOUD" else "120"))
    )
    rate_limit_window_seconds: int = field(default_factory=lambda: int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60")))
    # Number of proxies in front of the app that append to X-Forwarded-For.
    # 0 (local) rate-limits on the socket peer. Behind a hosting platform's
    # proxy it must match that platform's hop count, or every user shares
    # the proxy's address and therefore one bucket (see security.client_ip).
    trusted_proxy_hops: int = field(default_factory=lambda: int(os.environ.get("TRUSTED_PROXY_HOPS", "0")))
    # Daily /chat caps per UTC day (0 = off). The free LLM tiers give
    # roughly 50 answers a day from each Groq model in the chain plus 20
    # from Gemini, so in CLOUD one address gets 25 and everyone together
    # 150 before a "limit reached" message.
    # The per-client default needs TRUSTED_PROXY_HOPS: without it every
    # user behind the platform proxy is one "client", and 25 questions
    # would close the site for everyone.
    daily_chat_limit_per_client: int = field(
        default_factory=lambda: int(os.environ.get(
            "DAILY_CHAT_LIMIT_PER_CLIENT",
            "25" if os.environ.get("DEPLOY_MODE") == "CLOUD" and int(os.environ.get("TRUSTED_PROXY_HOPS", "0")) > 0
            else "0",
        ))
    )
    daily_chat_budget: int = field(
        default_factory=lambda: int(os.environ.get(
            "DAILY_CHAT_BUDGET", "150" if os.environ.get("DEPLOY_MODE") == "CLOUD" else "0"
        ))
    )
    # Cached LLM responses embed users' questions, so in CLOUD they expire
    # after a week. 0 keeps them forever, which local evaluation relies on.
    llm_cache_ttl_days: int = field(
        default_factory=lambda: int(os.environ.get(
            "LLM_CACHE_TTL_DAYS", "7" if os.environ.get("DEPLOY_MODE") == "CLOUD" else "0"
        ))
    )
    expose_provider_errors: bool = field(
        default_factory=lambda: _env_bool("EXPOSE_PROVIDER_ERRORS", os.environ.get("DEPLOY_MODE", "LOCAL") == "LOCAL")
    )

    # Who decides whether a cited source supports a claim: "llm" (one
    # batched judge call per answer; precision 0.93 vs the lexical gate's
    # 0.72 on 125 held-out live claims, see SUPPORT_REPORT.md), "lexical"
    # (no extra call), or "nli" (local cross-encoder; measured no better
    # than lexical). "llm" falls back to lexical if the judge call fails.
    support_checker: str = field(default_factory=lambda: os.environ.get("SUPPORT_CHECKER", "llm").strip().lower())
    # The judge runs on its own chain so it doesn't spend the answer model's
    # free quota (Groq caps each model at 200K tokens/day; gpt-oss-20b has
    # its own). Same "provider" or "provider:model" syntax as
    # LLM_PROVIDER_ORDER.
    support_judge_order: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            entry.strip().lower()
            for entry in os.environ.get("SUPPORT_JUDGE_PROVIDERS", "groq:openai/gpt-oss-20b,groq,gemini").split(",")
            if entry.strip()
        )
    )

    use_gpu: bool = field(default_factory=lambda: _env_bool("USE_GPU", True))
    enable_vector_retrieval: bool = field(default_factory=lambda: _env_bool("ENABLE_VECTOR_RETRIEVAL", True))
    # Cross-encoder startup is expensive on some Windows setups. Keep a
    # deterministic lightweight reranker as the production baseline; this
    # flag enables the heavier model only after it passes local timing tests.
    enable_cross_encoder: bool = field(default_factory=lambda: _env_bool("ENABLE_CROSS_ENCODER", False))
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
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins; wildcard origins are not allowed")
        if not self.trusted_hosts or "*" in self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS must contain explicit hostnames; wildcard hosts are not allowed")
        if self.deploy_mode == "CLOUD" and "CORS_ORIGINS" not in os.environ:
            raise ValueError("CORS_ORIGINS must be explicitly set in CLOUD mode")
        if self.deploy_mode == "CLOUD" and "TRUSTED_HOSTS" not in os.environ:
            raise ValueError("TRUSTED_HOSTS must be explicitly set in CLOUD mode")
        if self.rate_limit_requests < 1 or self.rate_limit_window_seconds < 1:
            raise ValueError("Rate-limit settings must be positive integers")
        if self.support_checker not in {"llm", "lexical", "nli"}:
            raise ValueError("SUPPORT_CHECKER must be llm, lexical or nli")
        if self.trusted_proxy_hops < 0:
            raise ValueError("TRUSTED_PROXY_HOPS must be 0 or a positive integer")
        if min(self.daily_chat_limit_per_client, self.daily_chat_budget, self.llm_cache_ttl_days) < 0:
            raise ValueError("DAILY_CHAT_LIMIT_PER_CLIENT, DAILY_CHAT_BUDGET and LLM_CACHE_TTL_DAYS must be 0 or positive")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


settings = Settings()
