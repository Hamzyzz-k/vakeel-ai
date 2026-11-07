"""
LLM response cache keyed on hash(provider, model, prompt).

Two reasons this exists, both load-bearing:
  1. Evaluation. 500 questions x 3 calls = 1500 calls = the entire daily
     Gemini free-tier quota (verified: ~1500 RPD). Re-running an eval after
     a scoring tweak must not cost a day of quota.
  2. Demo reliability. A 429 during a live presentation kills the demo. A
     warm cache makes previously-seen queries answer instantly and
     deterministically, with no network at all.
"""
from __future__ import annotations

import hashlib
import sqlite3
import threading

from app.config import CORPUS_DB_PATH, settings
from app.corpus.schema import get_connection, init_db


def cache_key(provider: str, model: str, prompt: str) -> str:
    digest = hashlib.sha256(f"{provider}\x00{model}\x00{prompt}".encode("utf-8")).hexdigest()
    return digest


class LLMCache:
    def __init__(self, db_path: str | None = None, ttl_days: int | None = None):
        self.db_path = db_path or str(CORPUS_DB_PATH)
        init_db(self.db_path)
        self._conn: sqlite3.Connection = get_connection(self.db_path)
        # One connection shared by concurrent API requests; each get/put is
        # a single short statement, so a lock here is cheap and never held
        # across an LLM call.
        self._lock = threading.Lock()
        # Responses restate users' questions, so a hosted cache shouldn't
        # keep them forever. 0 = never expire (local evaluation reuse).
        self.ttl_days = settings.llm_cache_ttl_days if ttl_days is None else ttl_days
        self._cutoff = f"-{self.ttl_days} days"

    def get(self, provider: str, model: str, prompt: str) -> str | None:
        key = cache_key(provider, model, prompt)
        with self._lock:
            if self.ttl_days > 0:
                row = self._conn.execute(
                    "SELECT response FROM llm_cache WHERE cache_key = ? AND created_at >= datetime('now', ?)",
                    (key, self._cutoff),
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT response FROM llm_cache WHERE cache_key = ?", (key,)
                ).fetchone()
        return row["response"] if row else None

    def put(self, provider: str, model: str, prompt: str, response: str) -> None:
        key = cache_key(provider, model, prompt)
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (cache_key, provider, model, prompt_hash, response) "
                "VALUES (?, ?, ?, ?, ?)",
                (key, provider, model, prompt_hash, response),
            )
            if self.ttl_days > 0:
                self._conn.execute("DELETE FROM llm_cache WHERE created_at < datetime('now', ?)", (self._cutoff,))
            self._conn.commit()

    def count(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) c FROM llm_cache").fetchone()["c"]
