"""
Cross-encoder reranking over an RRF-fused candidate pool, plus explicit
authority/recency boosts applied and measured separately from fusion --
an ablatable design, not a black-box weighted sum.
"""
from __future__ import annotations

_reranker_cache: dict[str, object] = {}


# Reranking needs enough of a passage to judge relevance, not the whole
# document. Left uncapped, CrossEncoder tokenizes candidates at whatever
# length they're passed in at -- measured directly: 30 candidates of 2000
# chars each took 35s per rerank call (would be ~58 minutes for a 100-query
# eval run). Capping to 256 tokens is standard practice for reranking and
# cut this to a small fraction of that.
_MAX_LENGTH = 256


def _get_reranker():
    if "reranker" not in _reranker_cache:
        from sentence_transformers import CrossEncoder
        from app.config import settings

        device = "cuda" if settings.use_gpu else "cpu"
        _reranker_cache["reranker"] = CrossEncoder(settings.reranker_model, device=device, max_length=_MAX_LENGTH)
    return _reranker_cache["reranker"]


def rerank(query: str, candidates: list[tuple[str, str]], top_k: int = 20) -> list[tuple[str, float]]:
    """
    candidates: list of (doc_id, doc_text).
    Returns [(doc_id, rerank_score), ...] best first, truncated to top_k.
    """
    if not candidates:
        return []
    model = _get_reranker()
    pairs = [(query, text) for _, text in candidates]
    scores = model.predict(pairs, batch_size=32)
    scored = list(zip([c[0] for c in candidates], (float(s) for s in scores)))
    scored.sort(key=lambda kv: -kv[1])
    return scored[:top_k]


def apply_authority_boost(
    scored: list[tuple[str, float]], authority_levels: dict[str, int], weight: float = 0.05
) -> list[tuple[str, float]]:
    """
    authority_levels: doc_id -> level (1=Constitution ... 8=secondary, spec
    section 23). Lower level = higher authority, so the boost is inverted
    and small by default (weight=0.05) -- this is meant to break near-ties
    among semantically-similar results, not override relevance. The weight
    is a named, ablatable parameter for exactly this reason.
    """
    boosted = []
    for doc_id, score in scored:
        level = authority_levels.get(doc_id, 8)
        boost = weight * (9 - level) / 8  # level 1 -> +weight, level 8 -> ~0
        boosted.append((doc_id, score + boost))
    boosted.sort(key=lambda kv: -kv[1])
    return boosted
