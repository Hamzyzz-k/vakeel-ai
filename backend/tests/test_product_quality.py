from app.eval.product_quality import CASES
from app.legal.statute_reference import extract_statute_references


def test_product_eval_ids_are_unique():
    assert len({case.id for case in CASES}) == len(CASES)


def test_exact_reference_cases_resolve_without_semantic_guessing():
    exact_cases = [case for case in CASES if case.id.endswith("_exact")]
    assert exact_cases
    for case in exact_cases:
        refs = extract_statute_references(case.query)
        assert refs, case.id
