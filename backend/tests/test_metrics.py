"""Hand-computed toy examples -- if these don't match arithmetic done on
paper, nothing downstream (RQ1) can be trusted."""
from app.eval.metrics import precision_at_k, recall_at_k, reciprocal_rank, ndcg_at_k, evaluate_run


def test_precision_at_k_basic():
    ranked = ["a", "b", "c", "d"]
    relevant = {"b", "d"}
    assert precision_at_k(ranked, relevant, 2) == 0.5  # b in top 2
    assert precision_at_k(ranked, relevant, 4) == 0.5  # b,d in top 4 of 4


def test_recall_at_k_basic():
    ranked = ["a", "b", "c", "d"]
    relevant = {"b", "d", "z"}  # z never retrieved
    assert recall_at_k(ranked, relevant, 4) == 2 / 3


def test_reciprocal_rank():
    assert reciprocal_rank(["a", "b", "c"], {"b"}) == 0.5
    assert reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0
    assert reciprocal_rank(["a", "b", "c"], {"z"}) == 0.0


def test_ndcg_perfect_ranking_is_one():
    ranked = ["a", "b", "c"]
    relevant = {"a", "b"}
    assert abs(ndcg_at_k(ranked, relevant, 3) - 1.0) < 1e-9


def test_ndcg_worst_ranking_less_than_best():
    relevant = {"a", "b"}
    best = ndcg_at_k(["a", "b", "c"], relevant, 3)
    worst = ndcg_at_k(["c", "a", "b"], relevant, 3)
    assert worst < best


def test_evaluate_run_skips_queries_with_no_relevant_docs():
    per_query_ranked = {"q1": ["a", "b"], "q2": ["x", "y"]}
    per_query_relevant = {"q1": {"a"}, "q2": set()}
    result = evaluate_run(per_query_ranked, per_query_relevant, k_values=(2,))
    assert result["n_queries"] == 1  # q2 excluded
