"""
Repository interface over the corpus. Every other module (retrieval,
ingestion, eval) goes through this, not raw SQL -- so a future Postgres
swap (if the rubric ever demands it, or scale ever does) is a new driver
file here, not a rewrite of the pipeline.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Iterable

from app.corpus.schema import get_connection, init_db


@dataclass
class LegalSource:
    id: str
    corpus: str
    source_type: str
    title: str
    full_text: str
    court: str | None = None
    jurisdiction: str = "India"
    domain: str | None = None
    date: str | None = None
    citation: str | None = None
    url: str | None = None
    authority_level: int | None = None
    act_name: str | None = None
    section_no: str | None = None
    case_number: str | None = None
    judges: str | None = None          # JSON array as text, per schema.py
    bench_strength: int | None = None


@dataclass
class LegalChunk:
    id: str
    source_id: str
    chunk_text: str
    section: str | None = None
    paragraph: int | None = None
    rhetorical_role: str | None = None
    char_start: int | None = None
    char_end: int | None = None


class SQLiteCorpusRepository:
    """
    The only supported driver for now. See module docstring.

    Holds one long-lived connection rather than opening a new one per call.
    An earlier per-call version also re-ran the full schema script on every
    instantiation, which made read-heavy loops (the eval harness calls
    get_source thousands of times) pathologically slow. Pass
    ensure_schema=False for read-only consumers that know the DB already
    exists.
    """

    def __init__(self, db_path: str, ensure_schema: bool = True):
        self.db_path = db_path
        if ensure_schema:
            init_db(db_path)
        self._connection = get_connection(db_path)
        self._source_cache: dict[str, sqlite3.Row | None] = {}

    def _conn(self) -> sqlite3.Connection:
        return self._connection

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "SQLiteCorpusRepository":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- writes -----------------------------------------------------------

    def upsert_source(self, s: LegalSource) -> None:
        self._conn().execute(
            """
            INSERT INTO legal_sources
                (id, corpus, source_type, title, court, jurisdiction, domain, date,
                 citation, url, authority_level, act_name, section_no, case_number,
                 judges, bench_strength, full_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, full_text=excluded.full_text,
                domain=excluded.domain, authority_level=excluded.authority_level,
                date=excluded.date, judges=excluded.judges, bench_strength=excluded.bench_strength,
                url=excluded.url
            """,
            (
                s.id, s.corpus, s.source_type, s.title, s.court, s.jurisdiction, s.domain,
                s.date, s.citation, s.url, s.authority_level, s.act_name, s.section_no,
                s.case_number, s.judges, s.bench_strength, s.full_text,
            ),
        )
        self._conn().commit()
        self._source_cache.pop(s.id, None)

    def upsert_chunks(self, chunks: Iterable[LegalChunk]) -> None:
        self._conn().executemany(
            """
            INSERT INTO legal_chunks (id, source_id, chunk_text, section, paragraph, rhetorical_role, char_start, char_end)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET chunk_text=excluded.chunk_text
            """,
            [
                (c.id, c.source_id, c.chunk_text, c.section, c.paragraph, c.rhetorical_role, c.char_start, c.char_end)
                for c in chunks
            ],
        )
        self._conn().commit()

    def add_eval_query(self, query_id: str, dataset: str, query_text: str) -> None:
        self._conn().execute(
            "INSERT INTO eval_queries (id, dataset, query_text) VALUES (?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET query_text=excluded.query_text",
            (query_id, dataset, query_text),
        )
        self._conn().commit()

    def add_qrel(self, query_id: str, source_id: str, relevance: int = 1) -> None:
        self._conn().execute(
            "INSERT OR IGNORE INTO eval_qrels (query_id, source_id, relevance) VALUES (?, ?, ?)",
            (query_id, source_id, relevance),
        )
        self._conn().commit()

    # -- reads --------------------------------------------------------------

    def get_source(self, source_id: str) -> sqlite3.Row | None:
        """Cached: the eval harness resolves the same source ids repeatedly
        across queries and methods, and these rows never change mid-run."""
        if source_id not in self._source_cache:
            self._source_cache[source_id] = self._conn().execute(
                "SELECT * FROM legal_sources WHERE id = ?", (source_id,)
            ).fetchone()
        return self._source_cache[source_id]

    def get_source_types(self, source_ids: Iterable[str]) -> dict[str, str]:
        """Bulk source_type lookup -- one query instead of N get_source calls."""
        ids = list(source_ids)
        if not ids:
            return {}
        placeholders = ",".join("?" * len(ids))
        rows = self._conn().execute(
            f"SELECT id, source_type FROM legal_sources WHERE id IN ({placeholders})", ids
        ).fetchall()
        return {r["id"]: r["source_type"] for r in rows}

    def count_sources(self, corpus: str | None = None) -> int:
        if corpus:
            return self._conn().execute(
                "SELECT COUNT(*) c FROM legal_sources WHERE corpus = ?", (corpus,)
            ).fetchone()["c"]
        return self._conn().execute("SELECT COUNT(*) c FROM legal_sources").fetchone()["c"]

    def count_chunks(self) -> int:
        return self._conn().execute("SELECT COUNT(*) c FROM legal_chunks").fetchone()["c"]

    def bm25_search(
        self, query: str, corpus: str | None = None, source_type: str | None = None,
        limit: int = 20, roles: list[str] | None = None,
    ) -> list[sqlite3.Row]:
        """FTS5 BM25 search over chunks, optionally scoped to a corpus,
        source_type, and/or a set of rhetorical_role values (Phase 4 / RQ5)."""
        sql = """
            SELECT lc.id, lc.source_id, lc.chunk_text, ls.corpus,
                   bm25(legal_chunks_fts) AS bm25_score
            FROM legal_chunks_fts
            JOIN legal_chunks lc ON lc.rowid = legal_chunks_fts.rowid
            JOIN legal_sources ls ON ls.id = lc.source_id
            WHERE legal_chunks_fts MATCH ?
        """
        params: list = [query]
        if corpus:
            sql += " AND ls.corpus = ?"
            params.append(corpus)
        if source_type:
            sql += " AND ls.source_type = ?"
            params.append(source_type)
        if roles:
            sql += f" AND lc.rhetorical_role IN ({','.join('?' for _ in roles)})"
            params.extend(roles)
        sql += " ORDER BY bm25_score LIMIT ?"
        params.append(limit)
        return self._conn().execute(sql, params).fetchall()

    def get_qrels_for_query(self, query_id: str) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT source_id, relevance FROM eval_qrels WHERE query_id = ?", (query_id,)
        ).fetchall()

    def get_eval_queries(self, dataset: str) -> list[sqlite3.Row]:
        return self._conn().execute(
            "SELECT id, query_text FROM eval_queries WHERE dataset = ?", (dataset,)
        ).fetchall()
