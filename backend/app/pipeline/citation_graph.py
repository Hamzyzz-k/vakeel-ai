"""
Citation graph (spec section 14/15) + conflict detection (spec section 20).

networkx over the `citations` edge table, read into memory at query time
rather than traversed in SQL -- the graph is small enough (currently a few
thousand potential nodes, a handful of real edges over the AILA corpus,
given the extraction recall measured directly against this corpus) that
rebuilding it per request is cheap, and it keeps the conflict-detection
logic as plain graph algorithms instead of recursive SQL.

Conflict detection follows spec section 20's factors in this precedence
order, each one only breaking ties left by the one before it:

    1. OVERRULES / DISTINGUISHES relationship (explicit signal beats any
       inferred one -- if B overrules A, B wins regardless of the rest)
    2. Court hierarchy (a higher court's authority_level wins)
    3. Date (the later decision wins, once overruling/hierarchy don't decide)
    4. Bench strength (a larger bench is generally treated as more
       authoritative among co-equal, same-date, non-overruling decisions)

Court hierarchy and date matter more in principle than they do on THIS
corpus in practice: every AILA judgment is Supreme Court of India, so
authority_level is uniform across the current dataset and that factor
never actually breaks a tie here. It is implemented and tested against
synthetic multi-court data anyway, because the product corpus is not
restricted to one court and will exercise it once it carries judgments.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from app.corpus.repository import SQLiteCorpusRepository

_OVERRULE_RELATIONSHIPS = frozenset({"OVERRULES", "DISTINGUISHES"})


@dataclass
class ConflictFinding:
    source_a: str
    source_b: str
    relationship: str  # the edge relationship that surfaced the conflict
    stronger: str | None  # source_id of the stronger authority, if determinable
    reason: str


@dataclass
class PrecedentMapNode:
    source_id: str
    title: str
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (relationship, direction, other_id)


def build_citation_graph(repo: SQLiteCorpusRepository) -> nx.DiGraph:
    """Builds a directed graph: edge A->B with relationship attribute means
    "A cites/follows/overrules/distinguishes B", matching the citations
    table's (source_id, cited_source_id) direction."""
    graph = nx.DiGraph()
    conn = repo._conn()
    rows = conn.execute("SELECT source_id, cited_source_id, relationship, confidence FROM citations").fetchall()
    for row in rows:
        graph.add_edge(row["source_id"], row["cited_source_id"], relationship=row["relationship"], confidence=row["confidence"])
    return graph


def _authority_level(repo: SQLiteCorpusRepository, source_id: str) -> tuple[int, str | None, int | None]:
    """Returns (authority_level, date, bench_strength) for conflict ranking.
    Missing authority_level sorts as weakest (a high number) rather than
    strongest -- an unknown court should never win a conflict by default."""
    row = repo.get_source(source_id)
    if row is None:
        return (99, None, None)
    return (row["authority_level"] or 99, row["date"], row["bench_strength"])


def _stronger_authority(repo: SQLiteCorpusRepository, a: str, b: str) -> str | None:
    """Applies the court-hierarchy > date > bench-strength tie-break, in
    that order. Returns None if genuinely indeterminate (all three tie or
    are missing) -- callers must treat that as "flag the conflict, don't
    guess a winner", per spec section 20's own output shape."""
    level_a, date_a, bench_a = _authority_level(repo, a)
    level_b, date_b, bench_b = _authority_level(repo, b)

    if level_a != level_b:
        return a if level_a < level_b else b  # lower authority_level number = higher court

    if date_a and date_b and date_a != date_b:
        return a if date_a > date_b else b  # later decision wins

    if bench_a and bench_b and bench_a != bench_b:
        return a if bench_a > bench_b else b  # larger bench wins

    return None


def detect_conflicts(repo: SQLiteCorpusRepository, graph: nx.DiGraph, source_ids: list[str]) -> list[ConflictFinding]:
    """
    Given a set of sources retrieved/cited for a single query, checks every
    pair for an explicit OVERRULES/DISTINGUISHES edge between them (in
    either direction) and, when found, determines the stronger authority.

    This deliberately does NOT try to infer conflict from two sources
    merely disagreeing in substance -- that would require the reasoning
    layer, not the graph. It surfaces only the relationships the citation
    graph actually recorded, which is the part that can be verified rather
    than guessed.
    """
    findings: list[ConflictFinding] = []
    seen_pairs: set[frozenset[str]] = set()

    for i, a in enumerate(source_ids):
        for b in source_ids[i + 1:]:
            pair = frozenset({a, b})
            if pair in seen_pairs:
                continue
            relationship = None
            direction = None
            if graph.has_edge(a, b) and graph[a][b]["relationship"] in _OVERRULE_RELATIONSHIPS:
                relationship = graph[a][b]["relationship"]
                direction = (a, b)
            elif graph.has_edge(b, a) and graph[b][a]["relationship"] in _OVERRULE_RELATIONSHIPS:
                relationship = graph[b][a]["relationship"]
                direction = (b, a)
            if relationship is None:
                continue

            seen_pairs.add(pair)
            citing, cited = direction
            stronger = _stronger_authority(repo, citing, cited)
            reason = (
                f"[{citing}] {relationship.lower()} [{cited}]"
                if relationship == "OVERRULES"
                else f"[{citing}] distinguishes its facts from [{cited}]"
            )
            findings.append(ConflictFinding(source_a=citing, source_b=cited, relationship=relationship, stronger=stronger, reason=reason))

    return findings


def build_precedent_map(repo: SQLiteCorpusRepository, graph: nx.DiGraph, source_id: str) -> list[PrecedentMapNode]:
    """Returns the source itself plus its direct neighbors (both directions)
    -- spec section 61's precedent map, one hop deep. Deeper traversal is
    possible (networkx makes it a one-line BFS) but the citation graph is
    sparse enough right now that it would mostly return nothing new past
    one hop on real data."""
    if source_id not in graph:
        row = repo.get_source(source_id)
        title = row["title"] if row else source_id
        return [PrecedentMapNode(source_id=source_id, title=title, edges=[])]

    edges: list[tuple[str, str, str]] = []
    for _, target, data in graph.out_edges(source_id, data=True):
        edges.append((data["relationship"], "outgoing", target))
    for source, _, data in graph.in_edges(source_id, data=True):
        edges.append((data["relationship"], "incoming", source))

    row = repo.get_source(source_id)
    title = row["title"] if row else source_id
    return [PrecedentMapNode(source_id=source_id, title=title, edges=edges)]
