"""Small paid/free-tier live generation smoke test for a verified batch.

Unlike the deterministic retrieval suite, this calls the configured LLM
providers.  Keep it deliberately small so repeated QA does not burn API
quota.

Run: python -m app.eval.live_tranche_smoke
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository
from app.llm.provider import LLMProvider
from app.pipeline.graph import run_query


@dataclass(frozen=True)
class LiveCase:
    id: str
    mode: str
    query: str
    expected_source: str


CASES = (
    LiveCase(
        "rera_delayed_possession_advice",
        "advice",
        "My builder missed the possession date and I want to withdraw. Under RERA section 18, what should I ask for next?",
        "indiacode:real_estate_act_2016:s18",
    ),
    LiveCase(
        "bnss_electronic_information_advice",
        "advice",
        "The cognizable offence happened in another area. Under BNSS section 173, can I send the information electronically and what must I do next?",
        "indiacode:bnss_2023:s173",
    ),
    LiveCase(
        "it_identity_theft_research",
        "research",
        "Research IT Act section 66C where someone dishonestly used another person's password and identification details.",
        "indiacode:information_technology_act_2000:s66C",
    ),
    LiveCase(
        "tpa_lease_notice_research",
        "research",
        "Research TPA section 106 for terminating a month-to-month lease where no contrary contract or local law is shown.",
        "indiacode:transfer_of_property_act_1882:s106",
    ),
    LiveCase(
        "constitution_liberty_advice",
        "advice",
        "The State is restricting my personal liberty. Under Article 21 of the Constitution of India, what is the governing safeguard and what facts should I document?",
        "indiacode:constitution:a21",
    ),
    LiveCase(
        "constitution_equality_research",
        "research",
        "Research Article 14 of the Indian Constitution where a person alleges denial of equality before law and equal protection of the laws.",
        "indiacode:constitution:a14",
    ),
    LiveCase(
        "limitation_specific_performance_advice",
        "advice",
        "The other party refused to perform our contract and no performance date was fixed. Under Article 54 of the Limitation Act, what deadline fact should I record?",
        "indiacode:limitation_act_1963:a54",
    ),
    LiveCase(
        "karnataka_stamp_admissibility_research",
        "research",
        "Research Karnataka Stamp Act section 34 where a party wants to rely on an insufficiently stamped instrument in evidence.",
        "indiacode:karnataka_stamp_act_1957:s34",
    ),
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    results = []
    failures = []
    with SQLiteCorpusRepository(str(CORPUS_DB_PATH)) as repo:
        llm = LLMProvider()
        for case in CASES:
            state = run_query(case.query, repo, llm, mode=case.mode)
            sources = [source.source_id for source in state.retrieved_sources]
            passed = (
                not state.abstained
                and sources[:1] == [case.expected_source]
                and "[S1]" in state.final_answer
                and "confidence score" not in state.final_answer.casefold()
            )
            if case.mode == "research":
                passed = passed and "RULE" in state.final_answer and "AUTHORITIES" in state.final_answer
            result = {
                "id": case.id,
                "mode": case.mode,
                "passed": passed,
                "abstained": state.abstained,
                "generation_mode": state.generation_mode,
                "retrieved_source_ids": sources,
                "answer": state.final_answer,
                "abstain_reason": state.abstain_reason,
                "provider_error": state.provider_error,
            }
            results.append(result)
            if not passed:
                failures.append(case.id)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    if failures:
        raise SystemExit(f"Live smoke failures: {', '.join(failures)}")


if __name__ == "__main__":
    main()
