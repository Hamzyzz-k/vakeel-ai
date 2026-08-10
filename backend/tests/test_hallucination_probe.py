"""Regression test for RQ3's probe set -- if a future change to
verify_answer() ever lets a fabricated or unsupported claim slip through,
this fails, rather than the drift being noticed only in a demo."""
from app.eval.hallucination_probe import run_probe


def test_probe_catches_every_fabricated_and_unsupported_claim():
    result = run_probe()
    summary = result["summary"]

    assert summary["fabrication_rate_without_verification"] > 0, "probe cases should include real fabrications"
    assert summary["fabrication_rate_with_verification"] == 0.0
    assert summary["unsupported_rate_with_verification_lexical_gate_only"] == 0.0


def test_correctly_supported_claim_is_not_falsely_rejected():
    result = run_probe()
    good_case = next(c for c in result["cases"] if c["case"] == "correctly_cited_supported_claim")
    assert good_case["verified_count"] == 1
    assert good_case["rejected_count"] == 0
