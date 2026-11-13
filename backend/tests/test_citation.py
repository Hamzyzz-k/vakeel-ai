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


def test_verifier_splits_cited_sentences_when_model_omits_periods():
    sources = [RetrievedSource(
        label="S1", source_id="s1", title="Section 73",
        text="A party suffering loss caused by breach is entitled to compensation.",
        source_type="SECTION",
    )]
    state = make_state(
        "Loss caused by breach is compensable [S1] A party suffering that loss may claim compensation [S1]",
        sources,
    )

    verify_answer(state, use_nli=False)

    assert len(state.verified_claims) == 2
    assert state.final_answer == (
        "Loss caused by breach is compensable [S1]. "
        "A party suffering that loss may claim compensation [S1]."
    )


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


def test_uncited_sentence_is_removed_so_it_cannot_bypass_closed_set_verification():
    sources: list[RetrievedSource] = []
    state = make_state("Here is a summary of the applicable position.", sources)
    verify_answer(state, use_nli=False)
    assert state.final_answer == ""
    assert state.verified_claims == []
    assert len(state.rejected_claims) == 1
    assert state.rejected_claims[0].rejection_reason == "legal claim has no source citation"


def test_low_word_overlap_is_not_treated_as_support_without_nli():
    sources = [RetrievedSource(
        label="S1", source_id="x", title="Unrelated provision",
        text="A seller shall deliver goods according to the contract.", source_type="SECTION",
    )]
    state = make_state(
        "The seller must refund the buyer within thirty days and pay compensation [S1].", sources
    )
    verify_answer(state, use_nli=False)

    assert state.verified_claims == []
    assert len(state.rejected_claims) == 1
    assert state.rejected_claims[0].supported is False


def test_invented_numeric_deadline_is_rejected_even_with_high_word_overlap():
    sources = [RetrievedSource(
        label="S1", source_id="x", title="Delivery provision",
        text="The seller must deliver the goods within a reasonable time.", source_type="SECTION",
    )]
    state = make_state("The seller must deliver the goods within 30 days [S1].", sources)
    verify_answer(state, use_nli=False)

    assert state.verified_claims == []
    assert len(state.rejected_claims) == 1


def test_added_negation_cannot_reverse_the_source_rule():
    sources = [RetrievedSource(
        label="S1", source_id="x", title="Liability provision",
        text="The seller is liable for loss caused by the breach.", source_type="SECTION",
    )]
    state = make_state("The seller is not liable for loss caused by the breach [S1].", sources)
    verify_answer(state, use_nli=False)

    assert state.verified_claims == []
    assert len(state.rejected_claims) == 1


def test_and_or_cannot_make_cumulative_penalties_optional():
    sources = [RetrievedSource(
        label="S1", source_id="x", title="IT Act section 66C",
        text=(
            "The offender shall be punished with imprisonment for a term which may extend to "
            "three years and shall also be liable to fine which may extend to one lakh rupees."
        ),
        source_type="SECTION",
    )]
    state = make_state(
        "The offence is punishable by imprisonment for three years and/or a fine of one lakh rupees [S1].",
        sources,
    )
    verify_answer(state, use_nli=False)

    assert state.verified_claims == []
    assert len(state.rejected_claims) == 1


def test_trace_records_verification_counts():
    sources = [RetrievedSource(label="S1", source_id="x", title="t", text="a landlord shall return the deposit", source_type="SECTION")]
    state = make_state("A landlord shall return the deposit [S1]. This cites nothing real [S99].", sources)
    verify_answer(state, use_nli=False)

    event = next(e for e in state.trace if e.step == "citation_verification")
    assert event.detail["verified"] == 1
    assert event.detail["rejected"] == 1
    assert event.detail["fabricated_labels"] == 1


def test_model_typography_does_not_decide_whether_a_claim_survives():
    # gpt-oss-120b writes narrow no-break spaces before labels and inside
    # "Section 73"; the claim must verify exactly as its ASCII twin does.
    from app.pipeline.citation import verify_text
    from app.pipeline.state import RetrievedSource

    source = RetrievedSource(
        label="S1", source_id="x", title="Indian Contract Act - Section 73",
        text="The party who breaks a contract must compensate the other party for loss caused by the breach.",
        source_type="SECTION",
    )
    plain = "Under Section 73 the party who breaks a contract must compensate for loss caused by the breach [S1]."
    fancy = plain.replace("Section 73", "Section 73").replace(" [S1]", " [S1]").replace("breaks", "breaks ")
    kept_plain, verified_plain, _ = verify_text(plain, {"S1": source}, use_nli=False)
    kept_fancy, verified_fancy, _ = verify_text(fancy, {"S1": source}, use_nli=False)
    assert len(verified_plain) == len(verified_fancy) == 1
    assert " " not in kept_fancy and " " not in kept_fancy


def _section_sources():
    from app.pipeline.state import RetrievedSource

    return {
        "S1": RetrievedSource(label="S1", source_id="a", title="Sale of Goods Act - Section 15",
                              text="Where there is a contract for the sale of goods by description, there is an implied condition that the goods shall correspond with the description.",
                              source_type="SECTION", section_no="15"),
        "S2": RetrievedSource(label="S2", source_id="b", title="Sale of Goods Act - Section 42",
                              text="The buyer is deemed to have accepted the goods when he intimates to the seller that he has accepted them.",
                              source_type="SECTION", section_no="42"),
    }


def test_section_number_written_as_label_maps_to_that_supplied_source():
    from app.pipeline.citation import verify_text

    text = "The buyer is deemed to have accepted the goods when he intimates acceptance to the seller [S42]."
    kept, verified, rejected = verify_text(text, _section_sources(), use_nli=False)
    assert rejected == []
    assert verified[0].cited_labels == ["S2"]
    assert kept.endswith("[S2].")


def test_unmatched_section_style_label_is_still_rejected_as_unknown():
    from app.pipeline.citation import verify_text

    text = "The buyer may reject the goods within thirty days [S99]."
    _, verified, rejected = verify_text(text, _section_sources(), use_nli=False)
    assert verified == []
    assert rejected[0].exists is False
    assert "S99" in rejected[0].rejection_reason


def test_remapped_label_still_needs_support():
    from app.pipeline.citation import verify_text

    text = "The seller must refund the full price within seven days of any complaint [S42]."
    _, verified, rejected = verify_text(text, _section_sources(), use_nli=False)
    assert verified == []
    assert rejected[0].exists is True
    assert rejected[0].supported is False


_NI_138 = RetrievedSource(
    label="S1", source_id="ni138", title="The Negotiable Instruments Act, 1881 - Section 138",
    text="The payee makes a demand by giving a notice in writing to the drawer within thirty days "
         "of the receipt of information, and the drawer fails to pay within fifteen days of the receipt of the notice.",
    source_type="SECTION",
)


def test_full_width_citation_brackets_are_recognised():
    state = make_state("The drawer must pay within fifteen days of the notice 【S1】.", [_NI_138])
    verify_answer(state, use_nli=False)
    assert [c.cited_labels for c in state.verified_claims] == [["S1"]]


def test_digits_match_numbers_the_statute_spells_out():
    from app.pipeline.citation import has_high_impact_contradiction

    evidence = _NI_138.text
    assert not has_high_impact_contradiction("Notice must be given within 30 days [S1].", evidence)
    assert not has_high_impact_contradiction("The drawer then has 15 days to pay [S1].", evidence)
    assert has_high_impact_contradiction("Notice must be given within 60 days [S1].", evidence)
    assert not has_high_impact_contradiction("within 180 days", "within one hundred and eighty days")
    assert not has_high_impact_contradiction("within 21 days", "within twenty-one days")


def test_judge_approval_cannot_override_a_number_contradiction():
    from app.pipeline.citation import CONTRADICTION_REASON, claim_evidence, verify_text

    by_label = {"S1": _NI_138}
    claim = "Notice must be given within 60 days."
    judged = {(claim, claim_evidence(["S1"], by_label)): True}
    _, verified, rejected = verify_text(f"{claim[:-1]} [S1].", by_label, use_nli=False, judged=judged)
    assert not verified
    assert rejected[0].rejection_reason == CONTRADICTION_REASON
