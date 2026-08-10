"""
Reciprocal Rank Fusion -- parameter-free merge of BM25 and vector
rankings. Replaces the spec's hand-picked weighted sum (0.35*semantic +
0.30*keyword + ...), which are invented numbers with no calibration
behind them. RRF is a standard IR baseline: score(d) = sum over rankers
of 1/(k + rank(d)), k=60 by convention (Cormack et al. 2009). Authority
level and recency are applied as separate, ablatable boosts at the
rerank stage (rerank.py), not folded in here -- so each can be measured
independently instead of guessed.
"""
from __future__ import annotations

RRF_K = 60


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = RRF_K) -> list[str]:
    """
    rankings: one ranked list of doc/chunk ids per retriever, best first.
    Returns a single fused ranking, best first.
    """
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: -kv[1])]
