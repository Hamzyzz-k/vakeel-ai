"""Evidence-quality scoring calibrated around user-visible failure modes.

This is a transparent heuristic, not a probability of legal correctness.
Unlike the previous score it cannot reward a citation merely for existing:
relevance, completeness, and contradiction checks are first-class gates.
"""
from __future__ import annotations

import re

from app.pipeline.citation import _content_tokens, has_high_impact_contradiction, lexical_overlap
from app.pipeline.state import LegalQueryState

WEIGHTS = {
    "citation_support": 0.35,
    "source_relevance": 0.30,
    "answer_completeness": 0.20,
    "contradiction_check": 0.15,
}


def _labels_used(state: LegalQueryState) -> set[str]:
    return {label for claim in state.verified_claims for label in claim.cited_labels}


def _citation_support(state: LegalQueryState) -> float:
    total = len(state.verified_claims) + len(state.rejected_claims)
    return len(state.verified_claims) / total if total else 0.0


def _stem_overlap(framing: str, evidence: str) -> float:
    """Share of the framing's content words whose 6-letter stem appears in
    the evidence ("detained" meets "detention", "coerced" meets "coercion")."""
    framing_stems = {term[:6] for term in _content_tokens(framing)}
    if not framing_stems:
        return 0.0
    evidence_stems = {term[:6] for term in _content_tokens(evidence)}
    return len(framing_stems & evidence_stems) / len(framing_stems)


def _source_relevance(state: LegalQueryState) -> float:
    """How squarely the cited sources address the question.

    Compared against the question AND the intake's legal framing (issues
    and search queries), taking the best. Measured on everyday-wording
    questions: against the user's own words alone this sat at 0.10-0.40 even
    for answers whose every sentence was verified, so the 0.45 cap below
    pinned nearly every score at 49 -- "my landlord won't give a receipt"
    shares few words with "Receipt to be given for rent".
    """
    labels = _labels_used(state)
    if not labels:
        return 0.0
    sources = state.sources_by_label()
    framings = [state.user_query, *state.search_queries, " ".join(state.issues)]
    framings = [framing for framing in framings if framing.strip()]
    scores = []
    for label in labels:
        source = sources.get(label)
        if source is None:
            continue
        if source.retrieval_method in {"direct_reference", "temporal_reference"}:
            scores.append(1.0)
        elif source.retrieval_method == "concept_reference":
            scores.append(0.95)
        else:
            evidence = f"{source.title}\n{source.text}"
            # Half the question's own words, half the best legal framing:
            # the framing alone would be partly circular, since the same
            # search queries chose these sources.
            question = max(lexical_overlap(state.user_query, evidence), _stem_overlap(state.user_query, evidence))
            framing = max(_stem_overlap(text, evidence) for text in framings)
            scores.append(0.5 * question + 0.5 * framing)
    return sum(scores) / len(scores) if scores else 0.0


def _answer_completeness(state: LegalQueryState) -> float:
    if not state.verified_claims:
        return 0.0
    answer = " ".join(claim.sentence for claim in state.verified_claims)
    labels = _labels_used(state)
    sources = state.sources_by_label()
    evidence = " ".join(
        f"{sources[label].title} {sources[label].text}"
        for label in labels
        if label in sources
    )
    # Demand only query concepts that the retrieved law can address; names
    # and incidental facts should not lower a statutory summary score.
    query_terms = set(re.findall(r"[a-z0-9]+", state.user_query.lower()))
    evidence_terms = set(re.findall(r"[a-z0-9]+", evidence.lower()))
    answer_terms = set(re.findall(r"[a-z0-9]+", answer.lower()))
    material_terms = {term for term in query_terms & evidence_terms if len(term) > 2}
    term_coverage = len(material_terms & answer_terms) / len(material_terms) if material_terms else 0.5

    direct = any(
        sources[label].retrieval_method == "direct_reference"
        for label in labels
        if label in sources
    )
    expected_claims = 1 if direct else 2
    depth = min(1.0, len(state.verified_claims) / expected_claims)
    return 0.65 * term_coverage + 0.35 * depth


def _looks_contradictory(claim: str, evidence: str) -> bool:
    return has_high_impact_contradiction(claim, evidence)


def _contradiction_score(state: LegalQueryState) -> float:
    if not state.verified_claims and not state.rejected_claims:
        return 0.0
    sources = state.sources_by_label()
    checked = 0
    contradictions = 0
    for claim in state.verified_claims + state.rejected_claims:
        known = [sources[label] for label in claim.cited_labels if label in sources]
        if not known:
            continue
        checked += 1
        evidence = " ".join(f"{source.title} {source.text}" for source in known)
        if _looks_contradictory(claim.sentence, evidence):
            contradictions += 1
    return 1.0 - (contradictions / checked) if checked else 1.0


def compute_evidence_score(state: LegalQueryState, conflict_flagged_labels: set[str] | None = None) -> dict:
    del conflict_flagged_labels  # conflicts are surfaced separately.
    if not state.verified_claims:
        result = {
            "overall": 0.0,
            "components": {key: 0.0 for key in WEIGHTS},
            "weights": WEIGHTS,
            "note": "No evidence-backed claims were retained.",
        }
        state.evidence_score = result
        return result

    components = {
        "citation_support": _citation_support(state),
        "source_relevance": _source_relevance(state),
        "answer_completeness": _answer_completeness(state),
        "contradiction_check": _contradiction_score(state),
    }
    overall = sum(components[key] * WEIGHTS[key] for key in WEIGHTS) * 100

    if components["source_relevance"] < 0.45 or components["answer_completeness"] < 0.45:
        overall = min(overall, 49.0)
    if components["contradiction_check"] < 1.0:
        overall = min(overall, 59.0)

    result = {
        "overall": round(overall, 1),
        "components": {key: round(value * 100, 1) for key, value in components.items()},
        "weights": WEIGHTS,
        "note": "Evidence quality heuristic; not a probability of legal correctness.",
    }
    state.evidence_score = result
    return result
