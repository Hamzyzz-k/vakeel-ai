"""
Extracts citation edges (spec section 14/15) between AILA judgments by
finding verbatim mentions of one judgment's case title inside another's
full text.

This is a precision-first, not recall-first, extractor: it only creates an
edge when another judgment's exact "X v Y" title string appears in the
citing text. Real citations often use short forms ("in Masud Khan's case"),
citation numbers, or paraphrased party names that this will miss -- that is
a known, stated recall limitation (see the module's own edge-count report
at the end of ingestion), not a hidden one. A wrong edge in a legal citation
graph is worse than a missed one, so precision was the deliberate choice.

Relationship type defaults to CITES; upgraded to FOLLOWS / OVERRULES /
DISTINGUISHES if a signal word appears within a fixed window around the
title mention.
"""
from __future__ import annotations

import re

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository

_WINDOW_CHARS = 120

_SIGNAL_PATTERNS = [
    ("OVERRULES", re.compile(r"\boverrul(e|ed|ing)\b", re.IGNORECASE)),
    ("DISTINGUISHES", re.compile(r"\bdistinguish(ed|able|ing)?\b", re.IGNORECASE)),
    ("FOLLOWS", re.compile(r"\b(followed|following|relied\s+(up)?on|applied)\b", re.IGNORECASE)),
]


def _classify_relationship(context: str) -> str:
    for relationship, pattern in _SIGNAL_PATTERNS:
        if pattern.search(context):
            return relationship
    return "CITES"


def _normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip()


def extract_citations_for_corpus(repo: SQLiteCorpusRepository, corpus: str = "eval") -> dict:
    conn = repo._conn()
    rows = conn.execute(
        "SELECT id, title, full_text FROM legal_sources WHERE corpus = ? AND source_type = 'JUDGMENT'",
        (corpus,),
    ).fetchall()

    # Titles are long and specific enough ("Masud Khan v State Of Uttar
    # Pradesh") that false-positive substring matches across different
    # cases are unlikely -- no need for a length/generality filter here,
    # unlike the boilerplate-prefix trap in the RQ5 overlap check.
    title_to_id = {_normalize_title(r["title"]): r["id"] for r in rows}

    # One compiled alternation, scanned once per document, instead of an
    # O(documents^2) nested loop -- 2,914 documents x 2,914 titles would be
    # ~8.5M substring searches (~7 minutes); this is one regex pass per
    # document, ~2,914 passes total. Longest titles first so a longer,
    # more specific title wins over a shorter one that happens to be its
    # prefix (regex alternation matches the first alternative that fits at
    # a position, not the longest).
    sorted_titles = sorted(title_to_id.keys(), key=len, reverse=True)
    combined_pattern = re.compile("|".join(re.escape(t) for t in sorted_titles))

    # A judgment can mention the same cited case's title several times in
    # its body (a string citation, then a discussion later) -- each mention
    # is evidence for the SAME edge, not a separate one. Keep the first
    # (earliest, most likely to be the primary citation) match per
    # (source, cited) pair rather than inserting one row per mention.
    edges_by_pair: dict[tuple[str, str], tuple[str, str, str, str | None, float]] = {}
    for row in rows:
        text = row["full_text"]
        own_title = _normalize_title(row["title"])
        # Search past the document's own header (its own title always
        # appears at position 0) so it can't cite itself.
        search_start = len(own_title) if text.startswith(own_title) else 0
        for m in combined_pattern.finditer(text, search_start):
            other_title = m.group(0)
            other_id = title_to_id[other_title]
            if other_id == row["id"]:
                continue
            pair = (row["id"], other_id)
            if pair in edges_by_pair:
                continue
            start = max(0, m.start() - _WINDOW_CHARS)
            end = min(len(text), m.end() + _WINDOW_CHARS)
            relationship = _classify_relationship(text[start:end])
            edges_by_pair[pair] = (row["id"], other_id, relationship, None, 1.0)
    edges = list(edges_by_pair.values())

    conn.executemany(
        "INSERT INTO citations (source_id, cited_source_id, relationship, paragraph, confidence) "
        "VALUES (?, ?, ?, ?, ?)",
        edges,
    )
    conn.commit()

    by_relationship: dict[str, int] = {}
    for _, _, rel, _, _ in edges:
        by_relationship[rel] = by_relationship.get(rel, 0) + 1

    return {"n_edges": len(edges), "n_documents": len(rows), "by_relationship": by_relationship}


if __name__ == "__main__":
    repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    stats = extract_citations_for_corpus(repo, "eval")
    print(stats)
