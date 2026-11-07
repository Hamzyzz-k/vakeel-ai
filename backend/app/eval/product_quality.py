"""Small, human-labelled product retrieval suite.

These cases exercise the live product corpus. They are intentionally
separate from the AILA benchmark so product changes are not scored against
an unrelated judgment corpus.

Most cases hand retrieval the correct domain, which skips the intake model
entirely -- so they could never catch the intake model picking a plausible
but wrong domain. Cases with `intake_domain` set feed retrieval that wrong
domain instead, the way a real query reaches it.

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
    # The (wrong) domain an intake model plausibly assigns; None means the
    # case is given its correct `domain`.
    intake_domain: str | None = None


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
    ProductRetrievalCase(
        "bnss_s173_exact",
        "Can information be given electronically under BNSS section 173?",
        "criminal_procedure",
        ("indiacode:bnss_2023:s173",),
    ),
    ProductRetrievalCase(
        "bsa_s61_exact",
        "What legal effect does BSA section 61 give an electronic or digital record?",
        "evidence",
        ("indiacode:bsa_2023:s61",),
    ),
    ProductRetrievalCase(
        "it_s66c_exact",
        "What is the punishment for identity theft under IT Act section 66C?",
        "technology",
        ("indiacode:information_technology_act_2000:s66C",),
    ),
    ProductRetrievalCase(
        "rera_s18_exact",
        "What must a promoter do under RERA section 18 after failing to give possession?",
        "real_estate",
        ("indiacode:real_estate_act_2016:s18",),
    ),
    ProductRetrievalCase(
        "tpa_s106_exact",
        "What notice applies to a month-to-month lease under TPA section 106?",
        "property",
        ("indiacode:transfer_of_property_act_1882:s106",),
    ),
    ProductRetrievalCase(
        "karnataka_rent_s27_exact",
        "Under Karnataka Rent Act section 27, when can a landlord recover possession?",
        "tenancy",
        ("indiacode:karnataka_rent_act_1999:s27",),
    ),
    ProductRetrievalCase(
        "bnss_electronic_fir_fuzzy",
        "Can I report a cognizable offence electronically to a police station even if it happened in another area?",
        "criminal_procedure",
        ("indiacode:bnss_2023:s173",),
    ),
    ProductRetrievalCase(
        "bsa_digital_record_fuzzy",
        "Can a court reject my digital record only because it is electronic?",
        "evidence",
        ("indiacode:bsa_2023:s61",),
    ),
    ProductRetrievalCase(
        "it_identity_theft_fuzzy",
        "Someone dishonestly used my password and unique identification details online. Which cyber offence applies?",
        "technology",
        ("indiacode:information_technology_act_2000:s66C",),
    ),
    ProductRetrievalCase(
        "rera_delayed_possession_fuzzy",
        "The developer missed the possession date and I want to withdraw and recover the amount paid with interest.",
        "real_estate",
        ("indiacode:real_estate_act_2016:s18",),
    ),
    ProductRetrievalCase(
        "tpa_monthly_lease_notice_fuzzy",
        "There is no written term for my month-to-month lease. How much termination notice is required?",
        "property",
        ("indiacode:transfer_of_property_act_1882:s106",),
    ),
    ProductRetrievalCase(
        "karnataka_eviction_fuzzy",
        "In Karnataka, can my landlord evict me without relying on one of the statutory grounds?",
        "tenancy",
        ("indiacode:karnataka_rent_act_1999:s27",),
    ),
    ProductRetrievalCase(
        "registration_s17_exact",
        "Which documents require registration under Registration Act section 17?",
        "property",
        ("indiacode:registration_act_1908:s17",),
    ),
    ProductRetrievalCase(
        "registration_gift_fuzzy",
        "Does an instrument gifting immovable property have to be registered?",
        "property",
        ("indiacode:registration_act_1908:s17",),
    ),
    ProductRetrievalCase(
        "easements_s15_exact",
        "What does Easements Act section 15 require for acquisition by prescription?",
        "property",
        ("indiacode:easements_act_1882:s15",),
    ),
    ProductRetrievalCase(
        "easements_right_of_way_fuzzy",
        "I have openly and without interruption used a right of way over another person's land for twenty years.",
        "property",
        ("indiacode:easements_act_1882:s15",),
    ),
    ProductRetrievalCase(
        "arbitration_s34_exact",
        "How can an arbitral award be set aside under Arbitration Act section 34?",
        "dispute_resolution",
        ("indiacode:arbitration_act_1996:s34",),
    ),
    ProductRetrievalCase(
        "arbitration_set_aside_fuzzy",
        "I need to challenge and set aside an arbitral award because the arbitration agreement was invalid.",
        "dispute_resolution",
        ("indiacode:arbitration_act_1996:s34",),
    ),
    ProductRetrievalCase(
        "ni_s138_exact",
        "What are the requirements of NI Act section 138 for dishonour of a cheque?",
        "commercial",
        ("indiacode:negotiable_instruments_act_1881:s138",),
    ),
    ProductRetrievalCase(
        "ni_cheque_dishonour_fuzzy",
        "A cheque issued for a debt bounced because the account had insufficient funds. What provision applies?",
        "commercial",
        ("indiacode:negotiable_instruments_act_1881:s138",),
    ),
    ProductRetrievalCase(
        "constitution_article_21_exact",
        "What protection does Article 21 of the Constitution of India provide?",
        "constitutional",
        ("indiacode:constitution:a21",),
    ),
    ProductRetrievalCase(
        "constitution_article_14_exact",
        "Does Article 14 of the Indian Constitution guarantee equal protection of the laws?",
        "constitutional",
        ("indiacode:constitution:a14",),
    ),
    ProductRetrievalCase(
        "constitution_equal_protection_fuzzy",
        "The State denied a person equality before the law and equal protection of the laws. Which constitutional rule applies?",
        "constitutional",
        ("indiacode:constitution:a14",),
    ),
    ProductRetrievalCase(
        "specific_relief_s10_exact",
        "When is specific performance enforced under Specific Relief Act section 10?",
        "civil_remedies",
        ("indiacode:specific_relief_act_1963:s10",),
    ),
    ProductRetrievalCase(
        "specific_relief_infrastructure_schedule_fuzzy",
        "Which infrastructure project categories are covered by the Specific Relief Act schedule?",
        "civil_remedies",
        ("indiacode:specific_relief_act_1963:schedule",),
    ),
    ProductRetrievalCase(
        "limitation_article_54_exact",
        "What period applies under Article 54 of the Limitation Act for specific performance?",
        "civil_procedure",
        ("indiacode:limitation_act_1963:a54",),
    ),
    ProductRetrievalCase(
        "limitation_specific_performance_fuzzy",
        "How long do I have to sue for specific performance after learning that performance was refused?",
        "civil_procedure",
        ("indiacode:limitation_act_1963:a54",),
    ),
    ProductRetrievalCase(
        "karnataka_stamp_s34_exact",
        "What happens to an insufficiently stamped instrument under Karnataka Stamp Act section 34?",
        "property",
        ("indiacode:karnataka_stamp_act_1957:s34",),
    ),
    ProductRetrievalCase(
        "karnataka_stamp_schedule_exact",
        "Show the stamp-duty instrument categories in the Karnataka Stamp Act Schedule.",
        "property",
        ("indiacode:karnataka_stamp_act_1957:schedule",),
    ),
    ProductRetrievalCase(
        "karnataka_land_revenue_s95_exact",
        "What procedure applies under Karnataka Land Revenue Act section 95 to use agricultural land for another purpose?",
        "land",
        ("indiacode:karnataka_land_revenue_act_1964:s95",),
    ),
    ProductRetrievalCase(
        "karnataka_government_land_fuzzy",
        "In Karnataka, who owns public roads and land that is not shown to belong to anyone else?",
        "land",
        ("indiacode:karnataka_land_revenue_act_1964:s67",),
    ),
    # -- the intake model chose a plausible but wrong domain ---------------
    ProductRetrievalCase(
        "cheque_bounce_classified_criminal",
        "My cheque given to a supplier bounced for insufficient funds. Can they file a criminal case and within what time?",
        "commercial",
        ("indiacode:negotiable_instruments_act_1881:s138",),
        intake_domain="criminal",
    ),
    ProductRetrievalCase(
        "delayed_flat_possession_classified_consumer",
        "The builder has not handed over possession of my flat for two years. Can I get my money back with interest?",
        "real_estate",
        ("indiacode:real_estate_act_2016:s18",),
        intake_domain="consumer",
    ),
    ProductRetrievalCase(
        "arbitral_award_challenge_classified_contract",
        "Can I go to court to set aside an arbitral award, and on what grounds?",
        "dispute_resolution",
        ("indiacode:arbitration_act_1996:s34",),
        intake_domain="contract",
    ),
    ProductRetrievalCase(
        "arrest_without_warrant_classified_criminal",
        "Can the police arrest me without a warrant, and when are they allowed to?",
        "criminal_procedure",
        ("indiacode:bnss_2023:s35",),
        intake_domain="criminal",
    ),
)


def evaluate(repo: SQLiteCorpusRepository, top_k: int = 4) -> dict:
    results = []
    for case in CASES:
        state = LegalQueryState(
            user_query=case.query,
            legal_domain=case.intake_domain or case.domain,
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
