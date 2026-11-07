"""
BM25 retrieval over the FTS5 index, aggregated from chunk-level to
document-level (the AILA qrels are document-level: a case or a statute
is relevant, not a specific paragraph of it). A source's score is the
best (lowest, since sqlite's bm25() returns lower-is-better) score among
its own chunks -- i.e. its best-matching passage represents the document.
"""
from __future__ import annotations

import re

from app.corpus.repository import SQLiteCorpusRepository

# FTS5 MATCH treats these as syntax, not literal characters -- legal text
# is full of them (Section 138(1), "quoted phrases", A1/S1-style refs from
# the AILA query text itself). Strip to safe tokens rather than let a raw
# legal query 500-error the search.
_FTS5_UNSAFE = re.compile(r"[^\w\s]")

# AILA queries are 150-250 word fact patterns, not keyword queries. OR-joining
# every token -- including "the", "was", "of" -- turns FTS5's MATCH into an OR
# of ~150 terms where the common ones alone match nearly every chunk in the
# corpus. Measured directly: one such query took >60s and had to be killed.
# Stopwords must be dropped before OR-joining, not just for cleanliness --
# this is a real performance cliff, not a style choice.
_STOPWORDS = frozenset("""
a an the this that these those is are was were be been being
of to in on at by for with from as and or but not no nor
he she it they them his her its their him we you i our your my
which who whom whose what where when why how
has have had do does did will would shall should can could may might must
if then than so such very also into onto upon under over between
""".split())

# Even after stopword removal, some fact patterns still run long. Cap the
# term count to the longest (most distinctive) remaining words -- short
# common words carry the least signal in BM25 anyway.
_MAX_TERMS = 40


def sanitize_fts5_query(text: str) -> str:
    cleaned = _FTS5_UNSAFE.sub(" ", text)
    tokens = [t for t in cleaned.split() if t and t.lower() not in _STOPWORDS and len(t) > 1]
    if len(tokens) > _MAX_TERMS:
        tokens = sorted(tokens, key=len, reverse=True)[:_MAX_TERMS]
    # OR-join: legal queries are long fact patterns, not exact phrases: we
    # want "any of these terms", ranked by BM25, not an impossible AND of
    # every word in a 200-word fact pattern.
    return " OR ".join(tokens) if tokens else ""


def bm25_search_documents(
    repo: SQLiteCorpusRepository,
    query_text: str,
    corpus: str,
    source_type: str | None = None,
    limit_docs: int = 50,
    chunk_pool: int = 300,
    roles: list[str] | None = None,
    domain: str | None = None,
) -> list[str]:
    """Returns a ranked list of source_ids, best first. `roles`, if given,
    restricts candidate chunks to those with a rhetorical_role in the list
    (Phase 4 / RQ5) -- see app/ingest/rhetorical_role_classifier.py."""
    fts_query = sanitize_fts5_query(query_text)
    if not fts_query:
        return []
    rows = repo.bm25_search(
        fts_query, corpus=corpus, source_type=source_type,
        limit=chunk_pool, roles=roles, domain=domain,
    )
    best_per_source: dict[str, float] = {}
    for row in rows:
        sid = row["source_id"]
        score = row["bm25_score"]  # lower is better in sqlite's bm25()
        if sid not in best_per_source or score < best_per_source[sid]:
            best_per_source[sid] = score
    ranked = sorted(best_per_source.items(), key=lambda kv: kv[1])
    return [sid for sid, _ in ranked[:limit_docs]]


def bm25_search_chunks(
    repo: SQLiteCorpusRepository,
    query_text: str,
    corpus: str,
    limit_chunks: int = 50,
    domain: str | list[str] | None = None,
) -> list[str]:
    """Return matched chunk ids directly instead of collapsing to sources."""
    fts_query = sanitize_fts5_query(query_text)
    if not fts_query:
        return []
    rows = repo.bm25_search(
        fts_query,
        corpus=corpus,
        limit=limit_chunks,
        domain=domain,
    )
    return [row["id"] for row in rows]
