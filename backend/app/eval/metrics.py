"""
Standard IR metrics, implemented directly rather than pulled in from a
library -- these are ~30 lines total and being able to point at exactly
what they compute matters for a project whose whole thesis is "measure,
don't assume". Verified against hand-computed toy examples in
tests/test_metrics.py.
"""
from __future__ import annotations

import math


def precision_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if k <= 0:
        return 0.0
    top_k = ranked_ids[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(top_k)


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    top_k = ranked_ids[:k]
    hits = sum(1 for doc_id in top_k if doc_id in relevant_ids)
    return hits / len(relevant_ids)


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for i, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    """Binary relevance NDCG@k."""
    top_k = ranked_ids[:k]
    dcg = sum(
        (1.0 / math.log2(i + 1)) for i, doc_id in enumerate(top_k, start=1) if doc_id in relevant_ids
    )
    ideal_hits = min(len(relevant_ids), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def evaluate_run(
    per_query_ranked: dict[str, list[str]],
    per_query_relevant: dict[str, set[str]],
    k_values: tuple[int, ...] = (5, 10, 20),
) -> dict:
    """
    per_query_ranked: query_id -> ranked list of doc ids (best first)
    per_query_relevant: query_id -> set of relevant doc ids (qrels)

    Only queries present in both dicts and with a non-empty relevant set
    are scored -- a query with zero known-relevant docs can't produce a
    meaningful recall/precision number and would silently drag averages
    toward zero if included.
    """
    query_ids = [qid for qid in per_query_ranked if per_query_relevant.get(qid)]
    n = len(query_ids)
    if n == 0:
        return {"n_queries": 0}

    out: dict = {"n_queries": n}
    for k in k_values:
        out[f"precision@{k}"] = sum(
            precision_at_k(per_query_ranked[q], per_query_relevant[q], k) for q in query_ids
        ) / n
        out[f"recall@{k}"] = sum(
            recall_at_k(per_query_ranked[q], per_query_relevant[q], k) for q in query_ids
        ) / n
        out[f"ndcg@{k}"] = sum(
            ndcg_at_k(per_query_ranked[q], per_query_relevant[q], k) for q in query_ids
        ) / n
    out["mrr"] = sum(reciprocal_rank(per_query_ranked[q], per_query_relevant[q]) for q in query_ids) / n
    return out
