from app.pipeline.evidence_score import compute_evidence_score
from app.pipeline.state import LegalQueryState, RetrievedSource, VerifiedClaim


def _state(query="What compensation follows breach of contract?"):
    state = LegalQueryState(user_query=query)
    state.retrieved_sources = [
        RetrievedSource(
            label="S1", source_id="x", title="Indian Contract Act - Section 73",
            text="Compensation is available for loss caused by breach of contract.",
            source_type="SECTION", authority_level=2, retrieval_score=0.9,
            retrieval_method="direct_reference",
        )
    ]
    return state


def test_supported_relevant_complete_answer_scores_high():
    state = _state()
    state.verified_claims = [
        VerifiedClaim(
            sentence="Compensation is available for loss caused by breach of contract.",
            cited_labels=["S1"], exists=True, supported=True,
        )
    ]
    result = compute_evidence_score(state)
    assert result["components"]["citation_support"] == 100.0
    assert result["components"]["source_relevance"] == 100.0
    assert result["overall"] >= 75.0


def test_no_claims_scores_zero():
    assert compute_evidence_score(_state())["overall"] == 0.0


def test_irrelevant_heading_cannot_score_strong():
    state = _state("Can I reject rice that does not match its description?")
    state.retrieved_sources[0].retrieval_method = "bm25_chunk_reranked"
    state.retrieved_sources[0].title = "Sale of Goods Act - Section 66"
    state.retrieved_sources[0].text = "Savings and repeals."
    state.verified_claims = [
        VerifiedClaim(sentence="Savings and repeals.", cited_labels=["S1"], exists=True, supported=True)
    ]
    assert compute_evidence_score(state)["overall"] <= 49.0


def test_numeric_contradiction_lowers_contradiction_component():
    state = _state("Is notice required within 30 days?")
    state.rejected_claims = [
        VerifiedClaim(
            sentence="Notice is required within 30 days.", cited_labels=["S1"],
            exists=True, supported=False,
        )
    ]
    state.verified_claims = [
        VerifiedClaim(sentence="Compensation follows breach.", cited_labels=["S1"], exists=True, supported=True)
    ]
    result = compute_evidence_score(state)
    assert result["components"]["contradiction_check"] < 100.0
    assert result["overall"] <= 59.0
