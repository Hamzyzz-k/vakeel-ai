from app.pipeline.evidence_score import compute_evidence_score
from app.pipeline.state import LegalQueryState, RetrievedSource, VerifiedClaim


def test_all_claims_verified_scores_high_on_citation_component():
    state = LegalQueryState(user_query="q")
    state.retrieved_sources = [
        RetrievedSource(label="S1", source_id="x", title="t", text="e", source_type="SECTION",
                         authority_level=1, retrieval_score=0.9)
    ]
    state.verified_claims = [VerifiedClaim(sentence="a", cited_labels=["S1"], exists=True, supported=True)]
    result = compute_evidence_score(state)
    assert result["components"]["citation_verification"] == 100.0


def test_no_claims_at_all_scores_zero_not_crash():
    state = LegalQueryState(user_query="q")
    result = compute_evidence_score(state)
    assert result["overall"] == 0.0


def test_mix_of_verified_and_rejected_scores_between_zero_and_hundred():
    state = LegalQueryState(user_query="q")
    state.retrieved_sources = [
        RetrievedSource(label="S1", source_id="x", title="t", text="e", source_type="SECTION", authority_level=2, retrieval_score=0.7)
    ]
    state.verified_claims = [VerifiedClaim(sentence="a", cited_labels=["S1"], exists=True, supported=True)]
    state.rejected_claims = [VerifiedClaim(sentence="b", cited_labels=["S9"], exists=False, supported=False)]
    result = compute_evidence_score(state)
    assert 0.0 < result["components"]["citation_verification"] < 100.0


def test_conflict_flagged_source_lowers_conflict_penalty_component():
    state = LegalQueryState(user_query="q")
    state.retrieved_sources = [
        RetrievedSource(label="S1", source_id="x", title="t", text="e", source_type="JUDGMENT", authority_level=3, retrieval_score=0.8)
    ]
    state.verified_claims = [VerifiedClaim(sentence="a", cited_labels=["S1"], exists=True, supported=True)]

    no_conflict = compute_evidence_score(state, conflict_flagged_labels=set())["components"]["conflict_penalty"]
    with_conflict = compute_evidence_score(state, conflict_flagged_labels={"S1"})["components"]["conflict_penalty"]
    assert with_conflict < no_conflict
