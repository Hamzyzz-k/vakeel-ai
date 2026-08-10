"""
SQLite schema for the corpus. One file (`data/corpus.db`) is the entire
artifact -- no separate DB server to run, so the whole app stays runnable
with zero infrastructure beyond Python and a checked-in file.

Two corpora share this schema but are kept logically separate by the
`corpus` column on legal_sources: 'eval' (AILA / IL-TUR, has relevance
judgments, used only for measuring retrieval quality) vs 'product' (India
Code statutes + collected judgments, what the demo actually runs on).
Mixing them would mean self-scored evaluation.
"""
from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;

-- One row per document: a statute, a section, a judgment, an order.
-- Metadata fields follow spec section 27.
CREATE TABLE IF NOT EXISTS legal_sources (
    id              TEXT PRIMARY KEY,   -- e.g. 'aila:C1', 'indiacode:15256:s2'
    corpus          TEXT NOT NULL CHECK (corpus IN ('eval', 'product')),
    source_type     TEXT NOT NULL,      -- ACT | SECTION | JUDGMENT | ORDER | RULE | REGULATION | CONSTITUTION | NOTIFICATION
    title           TEXT NOT NULL,
    court           TEXT,
    jurisdiction    TEXT NOT NULL DEFAULT 'India',
    domain          TEXT,               -- criminal | consumer | contract
    date            TEXT,               -- ISO 8601, nullable (not every source has one)
    citation        TEXT,
    url             TEXT,
    authority_level INTEGER,            -- spec section 23: 1=Constitution ... 8=secondary
    act_name        TEXT,
    section_no      TEXT,
    case_number     TEXT,
    judges          TEXT,               -- JSON array as text
    bench_strength  INTEGER,
    full_text       TEXT NOT NULL,
    ingested_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sources_corpus ON legal_sources(corpus);
CREATE INDEX IF NOT EXISTS idx_sources_domain ON legal_sources(domain);
CREATE INDEX IF NOT EXISTS idx_sources_type ON legal_sources(source_type);

-- Legal-structure-aware chunks (spec section 22) -- chunked by rhetorical
-- role / section boundary, not fixed token windows. One source can have
-- many chunks; a chunk always traces back to its source and paragraph.
CREATE TABLE IF NOT EXISTS legal_chunks (
    id          TEXT PRIMARY KEY,      -- e.g. 'aila:C1:p3'
    source_id   TEXT NOT NULL REFERENCES legal_sources(id),
    chunk_text  TEXT NOT NULL,
    section     TEXT,
    paragraph   INTEGER,
    rhetorical_role TEXT,              -- Fact | Issue | Argument | Ratio | Decision | Statute | ... (Phase 4)
    char_start  INTEGER,
    char_end    INTEGER,
    embedding   BLOB                   -- numpy float32 bytes, populated once torch/embedder land
);

CREATE INDEX IF NOT EXISTS idx_chunks_source ON legal_chunks(source_id);

-- FTS5 virtual table mirroring chunk_text for BM25. Kept in sync by the
-- ingestion pipeline (insert into both, or use a trigger -- triggers are
-- simpler and used here so no ingestion code can forget the sync).
CREATE VIRTUAL TABLE IF NOT EXISTS legal_chunks_fts USING fts5(
    chunk_text,
    content='legal_chunks',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS legal_chunks_ai AFTER INSERT ON legal_chunks BEGIN
    INSERT INTO legal_chunks_fts(rowid, chunk_text) VALUES (new.rowid, new.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS legal_chunks_ad AFTER DELETE ON legal_chunks BEGIN
    INSERT INTO legal_chunks_fts(legal_chunks_fts, rowid, chunk_text) VALUES ('delete', old.rowid, old.chunk_text);
END;

CREATE TRIGGER IF NOT EXISTS legal_chunks_au AFTER UPDATE ON legal_chunks BEGIN
    INSERT INTO legal_chunks_fts(legal_chunks_fts, rowid, chunk_text) VALUES ('delete', old.rowid, old.chunk_text);
    INSERT INTO legal_chunks_fts(rowid, chunk_text) VALUES (new.rowid, new.chunk_text);
END;

-- Citation graph edges (spec section 14/15). Read into networkx at query
-- time rather than traversed in SQL -- graph algorithms belong in a graph
-- library, not recursive CTEs.
CREATE TABLE IF NOT EXISTS citations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL REFERENCES legal_sources(id),
    cited_source_id TEXT NOT NULL REFERENCES legal_sources(id),
    relationship    TEXT NOT NULL CHECK (relationship IN
                        ('CITES','FOLLOWS','OVERRULES','DISTINGUISHES','INTERPRETS','REFERS_TO','CONTAINS','AMENDS')),
    paragraph       TEXT,
    confidence      REAL
);

CREATE INDEX IF NOT EXISTS idx_citations_source ON citations(source_id);
CREATE INDEX IF NOT EXISTS idx_citations_cited ON citations(cited_source_id);

-- Eval-only: queries + relevance judgments (qrels) for the eval corpus,
-- used by Phase 2's Precision@K/Recall@K/MRR/NDCG harness. Never joined
-- against the product corpus.
CREATE TABLE IF NOT EXISTS eval_queries (
    id          TEXT PRIMARY KEY,      -- e.g. 'aila:AILA_Q1'
    dataset     TEXT NOT NULL,         -- 'aila_precedent' | 'aila_statute' | 'iltur_pcr'
    query_text  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_qrels (
    query_id    TEXT NOT NULL REFERENCES eval_queries(id),
    source_id   TEXT NOT NULL REFERENCES legal_sources(id),
    relevance   INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (query_id, source_id)
);

-- LLM response cache: hash(prompt, model) -> response. Makes eval runs
-- and demos free and deterministic on repeat -- no re-spending free-tier
-- quota just to re-run the same question twice.
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key   TEXT PRIMARY KEY,
    provider    TEXT NOT NULL,
    model       TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    response    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI dispatches sync ('def', not 'async
    # def') route handlers to a worker threadpool (via anyio.to_thread), so
    # the SAME repository/connection created at process startup gets used
    # from a DIFFERENT thread on every request. sqlite3's default same-
    # thread check turned this into a hard crash on the second request's
    # thread -- caught by FastAPI TestClient API tests, not by manual curl
    # testing (which happened to keep hitting the same worker thread). The
    # repository pairs this with a threading.Lock around all connection
    # use (see SQLiteCorpusRepository._conn) so access is still serialized,
    # not actually concurrent -- check_same_thread=False alone would only
    # remove the crash, not the real race.
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
