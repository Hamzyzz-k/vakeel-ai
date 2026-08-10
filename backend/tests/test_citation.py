"""
Tests for closed-set citation verification (app/pipeline/citation.py) --
the core mechanism behind RQ3. NLI is stubbed out (use_nli=False) for these
tests: they check the *structural* guarantee (existence) and the lexical
gate deterministically, without depending on a loaded model. NLI-dependent
behavior is exercised separately once the model is confirmed loadable.
"""
from app.pipeline.citation import (
    extract_labels,
    strip_citations,
    split_sentences,
    lexical_overlap,
    verify_answer,
)
from app.pipeline.state import LegalQueryState, RetrievedSource


def make_state(raw_answer: str, sources: list[RetrievedSource]) -> LegalQueryState:
    state = LegalQueryState(user_query="test query")
    state.raw_answer = raw_answer
    state.retrieved_sources = sources
    return state


def test_extract_labels_single_and_multiple():
    assert extract_labels("This is settled law [S1].") == ["S1"]
    assert extract_labels("Two sources agree [S1, S3].") == ["S1", "S3"]
    assert extract_labels("No citation here.") == []


def test_strip_citations_removes_bracket_but_keeps_text():
    assert strip_citations("Interest is payable [S2].") == "Interest is payable."


def test_split_sentences_does_not_break_on_legal_abbreviations():
    text = "This follows Kusum Ingots v. Union of India. The ratio in Ors. matters."
    parts = split_sentences(text)
    # 'v.' must not create a spurious sentence boundary
    assert any("Kusum Ingots v. Union of India" in p for p in parts)


def test_lexical_overlap_basic():
    claim = "the landlord must return the security deposit"
    evidence = "a landlord shall return any security deposit collected"
    score = lexical_overlap(claim, evidence)
    assert score > 0.5


def test_fabricated_citation_is_structurally_rejected():
    """The core guarantee: citing a label never given to the model is
    rejected on existence alone, with zero model involvement."""
    sources = [RetrievedSource(label="S1", source_id="x", title="Real Act", text="Some real text.", source_type="SECTION")]
    state = make_state("This is settled law under Section 5 [S9].", sources)
    verify_answer(state, use_nli=False)

    assert len(state.rejected_claims) == 1
    assert state.rejected_claims[0].exists is False
    assert "S9" in state.rejected_claims[0].cited_labels
    assert state.verified_claims == []
    assert state.final_answer == ""


def test_supported_claim_with_high_lexical_overlap_is_kept():
    sources = [RetrievedSource(
        label="S1", source_id="x", title="Consumer Protection Act",
        text="A landlord shall return any security deposit collected from the tenant within a reasonable time.",
        source_type="SECTION",
    )]
    state = make_state(
        "A landlord shall return any security deposit collected from the tenant [S1].", sources
    )
    verify_answer(state, use_nli=False)

    assert len(state.verified_claims) == 1
    assert state.rejected_claims == []
    assert "[S1]" in state.final_answer


def test_unrelated_claim_citing_real_source_is_rejected_on_support():
    """A claim can cite a real, existing source and still be false --
    existence alone is not enough, which is why the support check exists."""
    sources = [RetrievedSource(
        label="S1", source_id="x", title="Sale of Goods Act",
        text="Goods must correspond with the description given by the seller.",
        source_type="SECTION",
    )]
    state = make_state(
        "The accused is entitled to anticipatory bail under this provision [S1].", sources
    )
    verify_answer(state, use_nli=False)

    assert len(state.rejected_claims) == 1
    assert state.rejected_claims[0].exists is True
    assert state.rejected_claims[0].supported is False


def test_uncited_sentence_is_kept_as_framing_not_a_claim():
    sources: list[RetrievedSource] = []
    state = make_state("Here is a summary of the applicable position.", sources)
    verify_answer(state, use_nli=False)
    assert state.final_answer == "Here is a summary of the applicable position."
    assert state.verified_claims == []
    assert state.rejected_claims == []


def test_trace_records_verification_counts():
    sources = [RetrievedSource(label="S1", source_id="x", title="t", text="a landlord shall return the deposit", source_type="SECTION")]
    state = make_state("A landlord shall return the deposit [S1]. This cites nothing real [S99].", sources)
    verify_answer(state, use_nli=False)

    event = next(e for e in state.trace if e.step == "citation_verification")
    assert event.detail["verified"] == 1
    assert event.detail["rejected"] == 1
    assert event.detail["fabricated_labels"] == 1
