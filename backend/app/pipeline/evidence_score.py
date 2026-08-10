"""
Evidence-strength scoring (spec section 31). Deliberately not presented as
"87% legally correct" -- it is a transparent rubric over retrieval and
verification quality, not a probability of correctness. The spec's original
0.35/0.30/0.20/... weights were invented numbers with no calibration behind
them (same problem as the retrieval fusion weights -- see
app/retrieval/hybrid.py); this version is built the same way: named,
independently inspectable components instead of one opaque number.
"""
from __future__ import annotations

from app.pipeline.state import LegalQueryState

# Component weights. Named constants, not folded into one formula, so each
# can be reported and ablated independently -- consistent with how
# retrieval fusion is handled (RRF + separate boosts, not a weighted sum).
WEIGHTS = {
    "citation_verification": 0.35,  # fraction of claims that passed verify_answer
    "source_authority": 0.25,       # mean authority level of cited sources (inverted: 1=high)
    "retrieval_confidence": 0.20,   # mean retrieval score of cited sources
    "conflict_penalty": 0.20,       # 1.0 minus fraction of cited sources involved in a known conflict
}


def _citation_verification_score(state: LegalQueryState) -> float:
    total = len(state.verified_claims) + len(state.rejected_claims)
    if total == 0:
        return 0.0
    return len(state.verified_claims) / total


def _source_authority_score(state: LegalQueryState) -> float:
    labels_used = {lbl for c in state.verified_claims for lbl in c.cited_labels}
    if not labels_used:
        return 0.0
    by_label = state.sources_by_label()
    levels = [by_label[lbl].authority_level for lbl in labels_used if lbl in by_label and by_label[lbl].authority_level]
    if not levels:
        return 0.5  # unknown authority -- neutral, not zero
    # Level 1 (Constitution) -> 1.0, Level 8 (secondary) -> ~0.0
    return sum((9 - lvl) / 8 for lvl in levels) / len(levels)


def _retrieval_confidence_score(state: LegalQueryState) -> float:
    labels_used = {lbl for c in state.verified_claims for lbl in c.cited_labels}
    if not labels_used:
        return 0.0
    by_label = state.sources_by_label()
    scores = [by_label[lbl].retrieval_score for lbl in labels_used if lbl in by_label and by_label[lbl].retrieval_score is not None]
    if not scores:
        return 0.5
    # Retrieval scores aren't guaranteed to be in [0,1] (BM25 is unbounded
    # negative-is-better; rerank scores can be any real number) -- clamp.
    return max(0.0, min(1.0, sum(scores) / len(scores)))


def compute_evidence_score(state: LegalQueryState, conflict_flagged_labels: set[str] | None = None) -> dict:
    """
    Populates and returns state.evidence_score. conflict_flagged_labels is
    the set of source labels the citation graph (Phase 7) has flagged as
    part of a conflicting-authority pair; empty/None until that phase lands,
    which correctly yields a conflict_penalty of 1.0 (no penalty) rather
    than a fabricated number.
    """
    conflict_flagged_labels = conflict_flagged_labels or set()

    total_claims = len(state.verified_claims) + len(state.rejected_claims)
    if total_claims == 0:
        # No claims were made at all (e.g. the pipeline abstained). The
        # conflict-penalty component would otherwise default to "no
        # conflict found" = 1.0 and make an empty answer score 20/100
        # instead of 0 -- there is no evidence to have a conflict about.
        result = {
            "overall": 0.0,
            "components": {k: 0.0 for k in WEIGHTS},
            "weights": WEIGHTS,
            "note": "No evidence-backed claims were made.",
        }
        state.evidence_score = result
        return result

    citation_score = _citation_verification_score(state)
    authority_score = _source_authority_score(state)
    retrieval_score = _retrieval_confidence_score(state)

    labels_used = {lbl for c in state.verified_claims for lbl in c.cited_labels}
    if labels_used:
        conflicted = len(labels_used & conflict_flagged_labels)
        conflict_score = 1.0 - (conflicted / len(labels_used))
    else:
        conflict_score = 1.0

    components = {
        "citation_verification": citation_score,
        "source_authority": authority_score,
        "retrieval_confidence": retrieval_score,
        "conflict_penalty": conflict_score,
    }
    overall = sum(components[k] * WEIGHTS[k] for k in WEIGHTS)

    result = {
        "overall": round(overall * 100, 1),  # 0-100, matches spec section 31's display convention
        "components": {k: round(v * 100, 1) for k, v in components.items()},
        "weights": WEIGHTS,
        "note": "Evidence strength, not a guarantee of legal correctness.",
    }
    state.evidence_score = result
    return result
