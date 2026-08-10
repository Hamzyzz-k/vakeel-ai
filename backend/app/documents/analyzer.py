"""
Document analysis (spec section 21): given extracted clauses, detect which
standard fields a rental/contract-style document actually addresses, flag
the ones it doesn't, and retrieve relevant law for each detected clause
topic using the same retrieval the chat pipeline uses -- one retrieval
implementation, not a second one for documents.

Keyword-based topic detection, not a classifier: the spec's own example
list (Lease duration, Rent, Security deposit, Termination clause, Notice
period, Penalty, Dispute resolution, Jurisdiction) is a fixed, small set of
well-known contract topics with fairly stable vocabulary in Indian legal
drafting, which keyword matching handles reasonably at this scope. A
learned classifier would need labeled contract data this project doesn't
have and hasn't claimed to have.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.corpus.repository import SQLiteCorpusRepository
from app.documents.extractor import ExtractedClause, ExtractedDocument
from app.retrieval.bm25 import bm25_search_documents
from app.retrieval.hybrid import reciprocal_rank_fusion

# Each topic's patterns are checked against clause text (heading + body).
# Order matters only for readability; detection checks all topics against
# every clause independently.
_TOPIC_PATTERNS: dict[str, re.Pattern] = {
    "Lease duration": re.compile(r"\b(term of|duration|commenc\w+ on|shall (run|continue) for|period of \d+ (month|year))\b", re.IGNORECASE),
    "Rent": re.compile(r"\b(rent|lease amount|monthly (payment|charges))\b", re.IGNORECASE),
    "Security deposit": re.compile(r"\b(security deposit|refundable deposit|advance deposit)\b", re.IGNORECASE),
    "Termination clause": re.compile(r"\b(terminat\w+|cancell\w+ this agreement)\b", re.IGNORECASE),
    "Notice period": re.compile(r"\b(notice period|\d+\s*days?\s*(prior\s+)?notice|written notice of)\b", re.IGNORECASE),
    "Penalty": re.compile(r"\b(penalty|liquidated damages|late fee|fine of)\b", re.IGNORECASE),
    "Dispute resolution": re.compile(r"\b(arbitrat\w+|dispute resolution|mediation)\b", re.IGNORECASE),
    "Jurisdiction": re.compile(r"\b(jurisdiction of|courts? (at|in)|governing law)\b", re.IGNORECASE),
}


@dataclass
class ClauseAnalysis:
    number: int | None
    heading: str | None
    text: str
    detected_topics: list[str] = field(default_factory=list)
    relevant_source_ids: list[str] = field(default_factory=list)


@dataclass
class DocumentAnalysis:
    n_pages: int
    n_clauses: int
    detected_topics: list[str]
    missing_topics: list[str]  # spec section 21's "flag what's absent"
    clauses: list[ClauseAnalysis]


def _detect_topics(clause: ExtractedClause) -> list[str]:
    haystack = f"{clause.heading or ''}\n{clause.text}"
    return [topic for topic, pattern in _TOPIC_PATTERNS.items() if pattern.search(haystack)]


def analyze_document(doc: ExtractedDocument, repo: SQLiteCorpusRepository, retrieve_per_clause: bool = True) -> DocumentAnalysis:
    clause_analyses: list[ClauseAnalysis] = []
    all_detected: set[str] = set()

    for clause in doc.clauses:
        topics = _detect_topics(clause)
        all_detected.update(topics)

        relevant_ids: list[str] = []
        if retrieve_per_clause and topics:
            # Search on the topic names plus a short excerpt of the clause,
            # not the full clause text -- clauses can run long, and BM25's
            # OR-of-terms behavior degrades badly on very long queries (seen
            # firsthand with AILA's fact-pattern queries) if not kept
            # reasonably short.
            query = " ".join(topics) + " " + clause.text[:300]
            ranked = bm25_search_documents(repo, query, corpus="product", limit_docs=5)
            relevant_ids = reciprocal_rank_fusion([ranked])[:5]

        clause_analyses.append(ClauseAnalysis(
            number=clause.number, heading=clause.heading, text=clause.text,
            detected_topics=topics, relevant_source_ids=relevant_ids,
        ))

    missing = [t for t in _TOPIC_PATTERNS if t not in all_detected]

    return DocumentAnalysis(
        n_pages=doc.n_pages,
        n_clauses=len(doc.clauses),
        detected_topics=sorted(all_detected),
        missing_topics=missing,
        clauses=clause_analyses,
    )
