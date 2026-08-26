"""Small, human-labelled product retrieval suite.

These cases exercise the live four-Act corpus. They are intentionally
separate from the AILA benchmark so product changes are not scored against
an unrelated judgment corpus.

Run: python -m app.eval.product_quality
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR
from app.corpus.repository import SQLiteCorpusRepository
from app.pipeline.graph import run_retrieval
from app.pipeline.state import LegalQueryState


@dataclass(frozen=True)
class ProductRetrievalCase:
    id: str
    query: str
    domain: str
    expected_source_ids: tuple[str, ...]


CASES = (
    ProductRetrievalCase(
        "contract_s63_exact",
        "Under Section 63 of the Indian Contract Act, can a promisee waive or remit performance?",
        "contract",
        ("indiacode:contract_act_1872:s63",),
    ),
    ProductRetrievalCase(
        "contract_s124_exact",
        "Define indemnity under Section 124 of the Indian Contract Act, 1872.",
        "contract",
        ("indiacode:contract_act_1872:s124",),
    ),
    ProductRetrievalCase(
        "bns_s303_exact",
        "What conduct amounts to theft under BNS section 303?",
        "criminal",
        ("indiacode:bns_2023:s303",),
    ),
    ProductRetrievalCase(
        "consumer_s85_exact",
        "When is a product service provider liable under Consumer Protection Act Section 85?",
        "consumer",
        ("indiacode:consumer_protection_act_2019:s85",),
    ),
    ProductRetrievalCase(
        "sale_description_fuzzy",
        "The seller delivered cloth that does not match its written description. Which condition applies?",
        "contract",
        ("indiacode:sale_of_goods_act_1930:s15",),
    ),
    ProductRetrievalCase(
        "sale_description_material_substitution",
        "I ordered 100% cotton fabric based on the seller description, but polyester fabric arrived. Can I reject it and which rule applies?",
        "contract",
        ("indiacode:sale_of_goods_act_1930:s15",),
    ),
    ProductRetrievalCase(
        "sale_fitness_fuzzy",
        "I told the seller the particular purpose and relied on their skill, but the goods are unfit.",
        "contract",
        ("indiacode:sale_of_goods_act_1930:s16",),
    ),
    ProductRetrievalCase(
        "consumer_warning_fuzzy",
        "A dangerous product had no adequate usage instructions or warning and caused injury.",
        "consumer",
        ("indiacode:consumer_protection_act_2019:s84",),
    ),
    ProductRetrievalCase(
        "contract_penalty_fuzzy",
        "The agreement names an excessive sum payable on breach. What compensation rule applies?",
        "contract",
        ("indiacode:contract_act_1872:s74",),
    ),
    ProductRetrievalCase(
        "bns_theft_fuzzy",
        "Someone dishonestly moved my movable property out of my possession without consent.",
        "criminal",
        ("indiacode:bns_2023:s303",),
    ),
)


def evaluate(repo: SQLiteCorpusRepository, top_k: int = 4) -> dict:
    results = []
    for case in CASES:
        state = LegalQueryState(
            user_query=case.query,
            legal_domain=case.domain,
            search_queries=[case.query],
        )
        run_retrieval(state, repo, top_k=top_k)
        retrieved = [source.source_id for source in state.retrieved_sources]
        rank = next((i + 1 for i, source_id in enumerate(retrieved) if source_id in case.expected_source_ids), None)
        results.append({
            **asdict(case),
            "retrieved_source_ids": retrieved,
            "hit": rank is not None,
            "rank": rank,
        })
    hits = sum(result["hit"] for result in results)
    return {
        "n_cases": len(results),
        "hit_at_k": hits / len(results),
        "mean_reciprocal_rank": sum((1 / result["rank"]) if result["rank"] else 0 for result in results) / len(results),
        "results": results,
    }


def main() -> None:
    with SQLiteCorpusRepository(str(CORPUS_DB_PATH)) as repo:
        report = evaluate(repo)
    output = EVAL_REPORTS_DIR / "product_retrieval_quality.json"
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, indent=2))
    for result in report["results"]:
        print(f"{'PASS' if result['hit'] else 'FAIL'} {result['id']}: rank={result['rank']} {result['retrieved_source_ids']}")


if __name__ == "__main__":
    main()
