"""
Closed-set citation verification. This is the core of RQ3 and the single
most important design decision in the project.

The spec's original design let the model emit a free-form citation
("ABC v XYZ, 2024 SCC ...") and then checked whether it existed. That is
backwards: it can only ever *detect* fabrication after the fact, and only
as reliably as the checker.

Here the model never sees free-form citation space. It is given only the
retrieved sources, each pre-labelled by us (S1, S2, ...), and instructed to
cite by label. Verification is then two deterministic checks:

  1. EXISTENCE -- is the cited label in the set we supplied for this query?
     No model involvement, no fuzzy matching, no network. A fabricated
     authority is *structurally impossible* to express, not merely caught.

  2. SUPPORT -- does the cited source's text actually entail the sentence?
     A model can still cite a real source that does not say what it claims.
     This is the harder half, and it is the one that needs measurement
     rather than assertion (see the fallback ladder below).

Any sentence failing either check is stripped from the answer before the
user sees it, and recorded in state.rejected_claims so the strip rate is a
reportable metric rather than an invisible behaviour.
"""
from __future__ import annotations

import re

from app.pipeline.state import LegalQueryState, VerifiedClaim

# Matches the citation labels we assign: [S1], [S12], [S3, S7]
_CITATION_RE = re.compile(r"\[([Ss]\d+(?:\s*,\s*[Ss]\d+)*)\]")

# Sentence splitter that does not break on common legal abbreviations
# ("v.", "No.", "Ors.", "s. 138") -- splitting there would orphan citations
# from their claims and cause false rejections.
_ABBREV = r"(?<!\bv)(?<!\bNo)(?<!\bOrs)(?<!\bAnr)(?<!\bs)(?<!\bSec)(?<!\bArt)"
_SENTENCE_SPLIT_RE = re.compile(rf"{_ABBREV}\.\s+(?=[A-Z])")

# Below this lexical overlap a claim is not sent to the NLI model at all --
# it cannot plausibly be supported. Above the high gate it is accepted
# without NLI. Only the ambiguous middle band costs a model call.
_LEXICAL_REJECT_BELOW = 0.08
_LEXICAL_ACCEPT_ABOVE = 0.60
_NLI_SUPPORT_THRESHOLD = 0.5

_STOPWORDS = frozenset("""
a an the this that these those is are was were be been being of to in on at by for with
from as and or but not no nor it its their his her they them which who whom whose what
where when why how has have had do does did will would shall should can could may might
must if then than so such very also into onto upon under over between
""".split())

_nli_cache: dict[str, object] = {}


def split_sentences(text: str) -> list[str]:
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return parts


def extract_labels(sentence: str) -> list[str]:
    """Returns normalized labels cited in a sentence, e.g. ['S1', 'S7']."""
    labels: list[str] = []
    for match in _CITATION_RE.finditer(sentence):
        for raw in match.group(1).split(","):
            label = raw.strip().upper()
            if label and label not in labels:
                labels.append(label)
    return labels


def strip_citations(sentence: str) -> str:
    stripped = _CITATION_RE.sub("", sentence)
    # Removing "[S2]" from "payable [S2]." leaves a floating space before
    # the sentence's own punctuation ("payable ."); collapse that back.
    stripped = re.sub(r"\s+([.,;:])", r"\1", stripped)
    return stripped.strip()


def _content_tokens(text: str) -> set[str]:
    tokens = re.findall(r"\w+", text.lower())
    return {t for t in tokens if t not in _STOPWORDS and len(t) > 2}


def lexical_overlap(claim: str, evidence: str) -> float:
    """Fraction of the claim's content words that appear in the evidence."""
    claim_tokens = _content_tokens(claim)
    if not claim_tokens:
        return 0.0
    evidence_tokens = _content_tokens(evidence)
    return len(claim_tokens & evidence_tokens) / len(claim_tokens)


def _get_nli_model():
    if "nli" not in _nli_cache:
        from sentence_transformers import CrossEncoder
        from app.config import settings

        device = "cuda" if settings.use_gpu else "cpu"
        _nli_cache["nli"] = CrossEncoder(settings.nli_model, device=device)
    return _nli_cache["nli"]


def nli_entailment_score(claim: str, evidence: str) -> float:
    """
    Probability that `evidence` entails `claim`.

    General NLI models are trained on short everyday sentence pairs, so a
    legal-paragraph/legal-claim pair is out of distribution -- a known risk,
    which is exactly why it sits behind lexical gates and why the threshold
    is a named constant that can be tuned against labelled data rather than
    a hardcoded guess.
    """
    import numpy as np

    model = _get_nli_model()
    scores = model.predict([(evidence, claim)])
    raw = scores[0]
    # CrossEncoder NLI heads return 3 logits (contradiction, entailment,
    # neutral) for deberta-style models, or a single score for others.
    if hasattr(raw, "__len__") and len(raw) == 3:
        exp = np.exp(raw - np.max(raw))
        probs = exp / exp.sum()
        return float(probs[1])
    return float(1 / (1 + np.exp(-float(raw))))


def verify_claim(claim: str, evidence: str, use_nli: bool = True) -> tuple[bool, float]:
    """
    Fallback ladder: cheap lexical gate first, model only for the ambiguous
    middle band. Returns (supported, score).
    """
    overlap = lexical_overlap(claim, evidence)
    if overlap < _LEXICAL_REJECT_BELOW:
        return False, overlap
    if overlap >= _LEXICAL_ACCEPT_ABOVE:
        return True, overlap
    if not use_nli:
        return overlap >= _LEXICAL_REJECT_BELOW, overlap
    score = nli_entailment_score(claim, evidence)
    return score >= _NLI_SUPPORT_THRESHOLD, score


def verify_text(text: str, by_label: dict, use_nli: bool = True) -> tuple[str, list[VerifiedClaim], list[VerifiedClaim]]:
    """
    The verification core, independent of LegalQueryState. Both Consultant
    mode (one block of prose) and Research mode (six IRAC sections, verified
    separately so a bad Application doesn't sink an otherwise-good Rule) call
    this -- the guarantee (closed-set citation, existence + support checks)
    must be identical in both, not reimplemented per mode.

    Returns (kept_text, verified_claims, rejected_claims).
    """
    kept: list[str] = []
    verified: list[VerifiedClaim] = []
    rejected: list[VerifiedClaim] = []

    for sentence in split_sentences(text):
        labels = extract_labels(sentence)
        bare = strip_citations(sentence)

        # A sentence with no citation makes no legal claim of its own
        # (framing, transitions). Keep it, but never treat it as supported.
        if not labels:
            kept.append(bare)
            continue

        unknown = [lbl for lbl in labels if lbl not in by_label]
        if unknown:
            rejected.append(
                VerifiedClaim(
                    sentence=bare, cited_labels=labels, exists=False, supported=False,
                    rejection_reason=f"cited unknown label(s): {', '.join(unknown)}",
                )
            )
            continue

        evidence = "\n".join(by_label[lbl].text for lbl in labels)
        supported, score = verify_claim(bare, evidence, use_nli=use_nli)

        claim = VerifiedClaim(
            sentence=bare, cited_labels=labels, exists=True,
            supported=supported, support_score=score,
            rejection_reason=None if supported else "cited source does not support this claim",
        )
        if supported:
            verified.append(claim)
            citation_text = ", ".join(labels)
            kept.append(f"{bare} [{citation_text}]")
        else:
            rejected.append(claim)

    return " ".join(kept).strip(), verified, rejected


# Order matches spec section 18's IRAC structure. AUTHORITIES is included
# because the spec's example output separates "the rule" from "the specific
# cases/sections applying it" -- keeping them as one section would blur that
# distinction in the rendered report.
IRAC_SECTION_ORDER = ["issue", "rule", "authorities", "application", "counterargument", "conclusion"]
IRAC_SECTION_HEADINGS = {
    "issue": "ISSUE", "rule": "RULE", "authorities": "AUTHORITIES",
    "application": "APPLICATION", "counterargument": "COUNTERARGUMENT", "conclusion": "CONCLUSION",
}


def verify_irac(state: LegalQueryState, use_nli: bool = True) -> LegalQueryState:
    """
    Research-mode counterpart to verify_answer. Verifies each IRAC section
    independently -- via the same verify_text() core Consultant mode uses,
    so a fabricated authority is exactly as structurally impossible here as
    it is there -- then reassembles the surviving sentences into a headed
    IRAC report. Claims are aggregated into state.verified_claims /
    rejected_claims across all sections so evidence_score.py needs no
    mode-specific logic.
    """
    import time

    started = time.perf_counter()
    by_label = state.sources_by_label()
    rendered_sections: list[str] = []

    for key in IRAC_SECTION_ORDER:
        raw_section = state.irac_sections.get(key, "").strip()
        if not raw_section:
            continue
        kept_text, verified, rejected = verify_text(raw_section, by_label, use_nli=use_nli)
        state.verified_claims.extend(verified)
        state.rejected_claims.extend(rejected)
        if kept_text:
            rendered_sections.append(f"{IRAC_SECTION_HEADINGS[key]}\n{kept_text}")

    state.final_answer = "\n\n".join(rendered_sections).strip()

    state.record(
        "citation_verification",
        {
            "mode": "research_irac",
            "verified": len(state.verified_claims),
            "rejected": len(state.rejected_claims),
            "fabricated_labels": sum(1 for c in state.rejected_claims if not c.exists),
            "unsupported": sum(1 for c in state.rejected_claims if c.exists and not c.supported),
            "sections_rendered": len(rendered_sections),
            "used_nli": use_nli,
        },
        started,
    )
    return state


def verify_answer(state: LegalQueryState, use_nli: bool = True) -> LegalQueryState:
    """
    Verifies every sentence of state.raw_answer, populating
    state.verified_claims / state.rejected_claims and rebuilding
    state.final_answer from only the surviving sentences.
    """
    import time

    started = time.perf_counter()
    by_label = state.sources_by_label()

    final_text, verified, rejected = verify_text(state.raw_answer, by_label, use_nli=use_nli)
    state.verified_claims.extend(verified)
    state.rejected_claims.extend(rejected)
    state.final_answer = final_text

    state.record(
        "citation_verification",
        {
            "verified": len(state.verified_claims),
            "rejected": len(state.rejected_claims),
            "fabricated_labels": sum(1 for c in state.rejected_claims if not c.exists),
            "unsupported": sum(1 for c in state.rejected_claims if c.exists and not c.supported),
            "used_nli": use_nli,
        },
        started,
    )
    return state
