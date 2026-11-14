"""
Cross-encoder reranking over an RRF-fused candidate pool, plus explicit
authority/recency boosts applied and measured separately from fusion --
an ablatable design, not a black-box weighted sum.
"""
from __future__ import annotations

import math
import re

_reranker_cache: dict[str, object] = {}


# Reranking needs enough of a passage to judge relevance, not the whole
# document. Left uncapped, CrossEncoder tokenizes candidates at whatever
# length they're passed in at -- measured directly: 30 candidates of 2000
# chars each took 35s per rerank call (would be ~58 minutes for a 100-query
# eval run). Capping to 256 tokens is standard practice for reranking and
# cut this to a small fraction of that.
_MAX_LENGTH = 256

_STOPWORDS = frozenset("""
a an the this that is are was were be of to in on at by for with from as and or but
what which who when how under act section sec s law legal india indian
""".split())

# Small, explicit legal-language normalisation. Users describe the practical
# problem ("doesn't match the description") while statutes use drafting terms
# ("shall correspond with the description"). This is deliberately narrow and
# auditable; it is not an opaque query-rewrite model.
_TERM_EQUIVALENTS = {
    "match": "correspond",
    "matches": "correspond",
    "matched": "correspond",
    "matching": "correspond",
    "unfit": "fitness",
}


def _terms(text: str) -> set[str]:
    return {
        _TERM_EQUIVALENTS.get(token, token)
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 1 and token not in _STOPWORDS
    }


def _stems(terms: set[str]) -> set[str]:
    # Crude, auditable stemming: compare 6-letter prefixes so "following",
    # "follows" and "follow", or "coercion" and "coerced", meet.
    return {term[:6] for term in terms}


# A section's heading is its first line up to the em dash:
# "15. "Coercion" defined.—". Headings name what a section is about.
_HEADING = re.compile(r"^\s*\d*[A-Z]?\s*[.\]]?\s*(.{3,160}?)(?:\.?\s*—|\.-|\n)")
# Definitions, short titles and savings clauses match almost any query's
# words but rarely answer one; measured crowding everyday-wording questions
# (CPA s.2, BNS s.2, BSA s.2 ranked above the operative sections).
_BOILERPLATE_HEADING = re.compile(
    r"\b(?:definitions?|short title|extent|commencement|savings?|repeal\w*|interpretation)\b", re.IGNORECASE,
)
_ASKS_FOR_MEANING = re.compile(r"\b(?:mean|means|meaning|defin\w*)\b", re.IGNORECASE)


def lexical_rerank(
    query: str, candidates: list[tuple[str, str]], top_k: int = 20, focus: list[str] | None = None,
) -> list[tuple[str, float]]:
    """Fast deterministic relevance reranker for the fused chunk pool.

    BM25 supplies term-frequency ranking; this second pass rewards coverage
    of the *distinct material terms* in the user's full question. It is also
    the safe fallback when the optional cross-encoder is unavailable.

    `focus` is the intake model's search queries, written in statutory terms
    ("coercion", "stalking", "electronic record"). Everyday wording rarely
    shares words with the operative section, so the best-matching focus
    query counts alongside the question, and a section whose heading names
    one of those terms gets a bonus.
    """
    query_terms = _terms(query)
    focus_sets = [_stems(_terms(text)) for text in (focus or []) if _terms(text)]
    all_stems = _stems(query_terms).union(*focus_sets) if focus_sets else _stems(query_terms)
    demote_boilerplate = not _ASKS_FOR_MEANING.search(query)
    chunk_terms_list = [_terms(text) for _, text in candidates]
    chunk_stems_list = [_stems(terms) for terms in chunk_terms_list]
    # Words common across the candidate pool ("contract", "goods",
    # "interest") say little about which candidate fits; rare ones
    # ("consideration", "stalking") say a lot. Weight focus matches by
    # inverse frequency within this pool.
    pool_size = max(1, len(candidates))
    frequency: dict[str, int] = {}
    for stems in chunk_stems_list:
        for stem in stems:
            frequency[stem] = frequency.get(stem, 0) + 1

    def weight(stem: str) -> float:
        return math.log((pool_size + 1) / (frequency.get(stem, 0) + 0.5))

    scored: list[tuple[str, float]] = []
    for rank, (chunk_id, text) in enumerate(candidates, start=1):
        chunk_terms = chunk_terms_list[rank - 1]
        coverage = len(query_terms & chunk_terms) / max(1, len(query_terms))
        phrase_bonus = 0.15 if query.strip().lower() in text.lower() else 0.0
        fused_rank_bonus = 1.0 / (20 + rank)
        score = coverage + phrase_bonus + fused_rank_bonus
        heading_match = _HEADING.match(text)
        heading = heading_match.group(1) if heading_match else ""
        if focus_sets:
            chunk_stems = chunk_stems_list[rank - 1]
            score += 0.6 * max(
                sum(weight(s) for s in stems & chunk_stems) / max(1e-9, sum(weight(s) for s in stems))
                for stems in focus_sets
            )
            # A heading naming a distinctive asked-about term marks the
            # operative section ("Stalking", "Coercion defined").
            heading_stems = _stems({t for t in _terms(heading) if len(t) > 3}) & all_stems
            distinctive = [s for s in heading_stems if frequency.get(s, 0) <= pool_size / 4]
            score += 0.1 * min(len(distinctive), 2)
        if demote_boilerplate and _BOILERPLATE_HEADING.search(heading):
            score -= 0.35
        scored.append((chunk_id, score))
    scored.sort(key=lambda item: -item[1])
    return scored[:top_k]


def _get_reranker():
    if "reranker" not in _reranker_cache:
        from sentence_transformers import CrossEncoder
        from app.config import settings

        device = "cuda" if settings.use_gpu else "cpu"
        _reranker_cache["reranker"] = CrossEncoder(
            settings.reranker_model,
            device=device,
            max_length=_MAX_LENGTH,
            local_files_only=True,
        )
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
