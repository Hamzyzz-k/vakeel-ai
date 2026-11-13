"""
Everyday-wording quality suite: questions phrased the way a non-lawyer asks
them, run through the real pipeline (coverage gate, LLM intake, retrieval,
and for a subset the full answer and citation checks).

product_quality.py can't see this failure mode: its cases mostly name the
Act or section, and it hands retrieval the correct domain. These cases
don't. Expected sections were chosen by reading the statute text in the
corpus; they have NOT been reviewed by a lawyer. A case "hits" when any
expected section is among the four sources the answer model is given.

Ten cases are held out (held_out=True). Tuning looks only at the "tune"
split; the held-out split is run once at the end to check the changes
generalise rather than fit these exact phrasings.

    python -m app.eval.lay_quality retrieval --label baseline
    python -m app.eval.lay_quality retrieval --label baseline --no-vectors
    python -m app.eval.lay_quality answers --label baseline
    python -m app.eval.lay_quality retrieval --label final --split heldout
    python -m app.eval.lay_quality report

Free-tier budget: retrieval runs make one cached intake call per case
(~600 tokens); answer runs add the answer and judge calls (~3-5K tokens)
for the `answer=True` subset only, on gpt-oss-20b by default so tuning
doesn't spend the live site's gpt-oss-120b daily quota.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR, settings
from app.corpus.repository import SQLiteCorpusRepository
from app.llm.provider import LLMProvider
from app.pipeline.graph import run_intake, run_query, run_retrieval
from app.pipeline.safety import assess_corpus_coverage
from app.pipeline.state import LegalQueryState


@dataclass(frozen=True)
class LayCase:
    id: str
    query: str
    # Any of these (ids without the "indiacode:" prefix) in the top 4 is a hit.
    expected: tuple[str, ...]
    held_out: bool = False
    # Also run through answer generation and citation checks.
    answer: bool = False


CASES = (
    # -- consumer / sale of goods -------------------------------------
    LayCase("phone_dead_in_a_week",
            "I bought a phone online and it stopped working within a week, and the seller refuses a refund. What can I do?",
            ("consumer_protection_act_2019:s35", "consumer_protection_act_2019:s39", "sale_of_goods_act_1930:s16"), answer=True),
    LayCase("fake_advert",
            "An online shop advertised a product with features it doesn't have. Can anything be done about misleading ads?",
            ("consumer_protection_act_2019:s21", "consumer_protection_act_2019:s89")),
    LayCase("consumer_complaint_deadline",
            "How long do I have to file a consumer complaint after a bad purchase?",
            ("consumer_protection_act_2019:s69",)),
    LayCase("paid_advance_never_delivered",
            "I paid an advance for a sofa and the shop never delivered it. Can I get my money back?",
            ("sale_of_goods_act_1930:s57", "contract_act_1872:s73", "contract_act_1872:s65"), answer=True),
    LayCase("used_car_hidden_damage",
            "The person who sold me a used car hid that it had been in a major accident. Can I cancel the deal?",
            ("contract_act_1872:s17", "contract_act_1872:s19", "contract_act_1872:s18")),
    LayCase("washing_machine_not_fit",
            "I told the shop I needed a washing machine for hard water and they sold me one that breaks down with hard water. Is the shop responsible?",
            ("sale_of_goods_act_1930:s16",), held_out=True),
    # -- property / registration / tenancy -----------------------------
    LayCase("builder_delay_interest",
            "The builder delayed handing over my flat by two years. Can I claim interest?",
            ("real_estate_act_2016:s18",), answer=True),
    LayCase("builder_complaint_where",
            "Where do I complain if my builder isn't following the agreement for my apartment?",
            ("real_estate_act_2016:s31",)),
    LayCase("oral_land_sale",
            "Is an oral agreement to sell land valid?",
            ("transfer_of_property_act_1882:s54", "registration_act_1908:s17")),
    LayCase("gift_deed_registration",
            "Does a gift deed of a house need to be registered?",
            ("transfer_of_property_act_1882:s123", "registration_act_1908:s17"), answer=True),
    LayCase("deed_registration_time",
            "How many months do I have to get a sale deed registered after signing it?",
            ("registration_act_1908:s23",)),
    LayCase("unregistered_deed_effect",
            "What happens if a property document that should be registered is never registered?",
            ("registration_act_1908:s49",), held_out=True),
    LayCase("tenant_eviction_karnataka",
            "My tenant in Bangalore has stopped paying rent for months. Can I get him evicted?",
            ("karnataka_rent_act_1999:s27",), answer=True),
    LayCase("rent_receipt",
            "My landlord in Bengaluru refuses to give me a receipt when I pay rent. What can I do?",
            ("karnataka_rent_act_1999:s16",)),
    LayCase("monthly_tenancy_notice",
            "There is no written rent agreement. How much notice is needed to end a monthly tenancy?",
            ("transfer_of_property_act_1882:s106",), held_out=True),
    LayCase("rent_agreement_stamp",
            "How much stamp duty do I pay on a rental agreement in Karnataka?",
            ("karnataka_stamp_act_1957:schedule", "karnataka_stamp_act_1957:s3")),
    LayCase("neighbour_blocks_path",
            "Can I get an injunction to stop my neighbour from blocking my right of way?",
            ("specific_relief_act_1963:s38", "specific_relief_act_1963:s37", "easements_act_1882:s35", "easements_act_1882:s33")),
    # -- contracts / money ---------------------------------------------
    LayCase("loan_recovery_time",
            "How long do I have to file a case to recover money I lent to a friend?",
            ("limitation_act_1963:a19", "limitation_act_1963:a21", "limitation_act_1963:s3"), answer=True),
    LayCase("contract_under_threat",
            "Can a contract I signed under threat be cancelled?",
            ("contract_act_1872:s15", "contract_act_1872:s19")),
    LayCase("contract_with_minor",
            "I made a deal with a 16 year old. Is the contract valid?",
            ("contract_act_1872:s11",)),
    LayCase("promise_without_payment",
            "My uncle promised to give me money but I gave nothing in return. Can I enforce that promise?",
            ("contract_act_1872:s25", "contract_act_1872:s10")),
    LayCase("penalty_clause",
            "Our contract says I must pay 5 lakh if I break it. Will a court make me pay the full amount?",
            ("contract_act_1872:s74",), held_out=True),
    LayCase("force_specific_performance",
            "The seller backed out after agreeing to sell me his flat. Can the court force him to complete the sale?",
            ("specific_relief_act_1963:s10", "limitation_act_1963:a54"), held_out=True),
    LayCase("arbitration_award_challenge",
            "I lost an arbitration and think the award is unfair. How can I challenge it in court?",
            ("arbitration_act_1996:s34",)),
    LayCase("cheque_bounce",
            "My cheque given to a supplier bounced for insufficient funds. Can they file a criminal case?",
            ("negotiable_instruments_act_1881:s138",)),
    # -- cyber / crime ---------------------------------------------------
    LayCase("email_impersonation",
            "Someone hacked my email and is impersonating me to ask my friends for money. Is that a crime?",
            ("information_technology_act_2000:s66C", "information_technology_act_2000:s66D"), answer=True),
    LayCase("private_photos_posted",
            "Someone posted my private photos online without my permission. What law covers this?",
            ("information_technology_act_2000:s66E", "bns_2023:s77")),
    LayCase("threat_for_money",
            "A man keeps threatening to hurt my family unless I pay him money. What offence is this?",
            ("bns_2023:s308", "bns_2023:s351"), answer=True),
    LayCase("someone_following_woman",
            "A man keeps following my sister and messaging her even after she told him to stop. Is that illegal?",
            ("bns_2023:s78",)),
    LayCase("house_break_in",
            "Someone broke into our house at night and stole jewellery. What crimes did they commit?",
            ("bns_2023:s305", "bns_2023:s331", "bns_2023:s303")),
    LayCase("online_defamation",
            "Someone is spreading false stories about me on social media that damage my reputation. Is that a crime?",
            ("bns_2023:s356",), held_out=True),
    LayCase("money_entrusted_misused",
            "I gave my business partner money to buy stock and he spent it on himself. Is that a criminal offence?",
            ("bns_2023:s316",), held_out=True),
    # -- police / courts / rights ---------------------------------------
    LayCase("police_questioning",
            "The police took my brother for questioning without telling us why. What are his rights?",
            ("bnss_2023:s47", "bnss_2023:s48", "bnss_2023:s35", "bnss_2023:s179"), answer=True),
    LayCase("held_over_24_hours",
            "My cousin was arrested two days ago and still hasn't been taken before a judge. Is that allowed?",
            ("bnss_2023:s58", "constitution:a22")),
    LayCase("bail_minor_offence",
            "Can someone arrested for a minor bailable offence get bail at the police station?",
            ("bnss_2023:s478",), held_out=True),
    LayCase("police_refuse_fir",
            "The police are refusing to register my complaint about a serious crime. What can I do?",
            ("bnss_2023:s173",), held_out=True),
    LayCase("whatsapp_evidence",
            "Can WhatsApp messages be used as evidence in court?",
            ("bsa_2023:s63", "bsa_2023:s61", "bsa_2023:s62"), answer=True),
    LayCase("arrested_for_post",
            "Can I be jailed just for criticising a politician in a social media post?",
            ("constitution:a19", "constitution:a21")),
    # -- vehicles --------------------------------------------------------
    LayCase("no_helmet_fine",
            "I was caught riding a bike without a helmet in Bangalore. What penalty applies?",
            ("motor_vehicles_act_1988:s194D", "motor_vehicles_act_1988:s129")),
    LayCase("uninsured_vehicle",
            "What happens if I drive a car whose insurance has expired?",
            ("motor_vehicles_act_1988:s196", "motor_vehicles_act_1988:s146"), held_out=True),
)

_ID_PREFIX = "indiacode:"


def _split(cases, split: str):
    if split == "all":
        return list(cases)
    return [case for case in cases if case.held_out == (split == "heldout")]


def _llm(order: tuple[str, ...]) -> LLMProvider:
    return LLMProvider(provider_order=order)


class _SplitLLM:
    """Intake on one chain, every other call (answer, support judge) on
    another, so answer runs can use a cheaper model without changing the
    intake that drives retrieval."""

    def __init__(self, intake: LLMProvider, rest: LLMProvider):
        self.intake, self.rest = intake, rest

    def _pick(self, prompt: str) -> LLMProvider:
        return self.intake if prompt.startswith("You are the intake stage") else self.rest

    def generate(self, prompt, json_schema=None, use_cache=True):
        return self._pick(prompt).generate(prompt, json_schema=json_schema, use_cache=use_cache)

    def generate_json(self, prompt, json_schema, use_cache=True):
        return self._pick(prompt).generate_json(prompt, json_schema, use_cache=use_cache)


def run_retrieval_suite(repo, llm, cases, vectors: bool) -> list[dict]:
    previous = settings.enable_vector_retrieval
    settings.enable_vector_retrieval = vectors
    try:
        rows = []
        for case in cases:
            state = LegalQueryState(user_query=case.query)
            covered, reason = assess_corpus_coverage(state)
            if covered:
                run_intake(state, llm)
                covered, reason = assess_corpus_coverage(state)
            if covered:
                run_retrieval(state, repo)
            retrieved = [source.source_id.removeprefix(_ID_PREFIX) for source in state.retrieved_sources]
            rank = next((i + 1 for i, sid in enumerate(retrieved) if sid in case.expected), None)
            rows.append({
                "id": case.id, "held_out": case.held_out, "covered": covered, "coverage_reason": reason,
                "legal_domain": state.legal_domain, "retrieved": retrieved, "rank": rank,
                "intake_steps": [event.step for event in state.trace if event.step.startswith("intake")],
            })
        return rows
    finally:
        settings.enable_vector_retrieval = previous


def run_answer_suite(repo, llm, cases, pause: float) -> list[dict]:
    from app.api.chat import _shown_as_unverified

    rows = []
    for index, case in enumerate(cases):
        if index:
            time.sleep(pause)  # stay under Groq's 8K tokens/minute
        state = run_query(case.query, repo, llm, mode="advice")
        retrieved = [source.source_id.removeprefix(_ID_PREFIX) for source in state.retrieved_sources]
        rows.append({
            "id": case.id,
            "rank": next((i + 1 for i, sid in enumerate(retrieved) if sid in case.expected), None),
            "abstained": state.abstained,
            "abstain_reason": state.abstain_reason,
            "verified": len(state.verified_claims),
            "unverified_shown": sum(1 for claim in state.rejected_claims if _shown_as_unverified(claim)),
            "rejected": len(state.rejected_claims),
            "score": (state.evidence_score or {}).get("overall"),
            "score_components": (state.evidence_score or {}).get("components"),
            "generation_mode": state.generation_mode,
            "verified_sentences": [claim.sentence for claim in state.verified_claims],
            "rejected_sentences": [[claim.rejection_reason, claim.sentence] for claim in state.rejected_claims],
        })
    return rows


def _summary(rows: list[dict]) -> dict:
    n = len(rows)
    hits = [row for row in rows if row.get("rank")]
    summary = {"n": n, "hit_at_4": round(len(hits) / n, 3) if n else 0.0,
               "mrr": round(sum(1 / row["rank"] for row in hits) / n, 3) if n else 0.0}
    if rows and "verified" in rows[0]:
        answered = [row for row in rows if not row["abstained"]]
        summary.update({
            "abstained": n - len(answered),
            "verified_total": sum(row["verified"] for row in rows),
            "unverified_shown_total": sum(row["unverified_shown"] for row in rows),
            "rejected_total": sum(row["rejected"] for row in rows),
            "mean_score_answered": round(sum(row["score"] or 0 for row in answered) / len(answered), 1) if answered else None,
        })
    return summary


def _output_path(kind: str, label: str, split: str, vectors: bool | None) -> Path:
    suffix = "" if vectors is None else ("_vec" if vectors else "_novec")
    return EVAL_REPORTS_DIR / f"lay_quality_{kind}_{label}_{split}{suffix}.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("retrieval", "answers", "report"))
    parser.add_argument("--label", default="run")
    parser.add_argument("--split", choices=("tune", "heldout", "all"), default="tune")
    parser.add_argument("--no-vectors", action="store_true")
    parser.add_argument("--intake-order", default="groq")
    parser.add_argument("--answer-order", default="groq:openai/gpt-oss-20b")
    parser.add_argument("--pause", type=float, default=20.0)
    args = parser.parse_args()

    if args.kind == "report":
        write_report()
        return

    cases = _split(CASES, args.split)
    with SQLiteCorpusRepository(str(CORPUS_DB_PATH)) as repo:
        if args.kind == "retrieval":
            vectors = not args.no_vectors
            rows = run_retrieval_suite(repo, _llm(tuple(args.intake_order.split(","))), cases, vectors)
            path = _output_path("retrieval", args.label, args.split, vectors)
        else:
            vectors = None
            # Intake stays on its production model so retrieval matches the
            # live site; only the answer step uses the cheaper model.
            answer_llm = _SplitLLM(_llm(tuple(args.intake_order.split(","))), _llm(tuple(args.answer_order.split(","))))
            rows = run_answer_suite(repo, answer_llm, [case for case in cases if case.answer], args.pause)
            path = _output_path("answers", args.label, args.split, vectors)
    report = {"label": args.label, "split": args.split, "summary": _summary(rows), "rows": rows}
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    for row in rows:
        print(f"{'HIT ' if row.get('rank') else 'MISS'} {row['id']}: rank={row.get('rank')} {row.get('retrieved', '')}"
              + ("" if "verified" not in row else
                 f" verified={row['verified']} unverified={row['unverified_shown']} abstained={row['abstained']} score={row['score']}"))


def write_report() -> None:
    """Collects every lay_quality_*.json run into LAY_QUALITY_REPORT.md."""
    runs = sorted(EVAL_REPORTS_DIR.glob("lay_quality_*.json"))
    lines = [
        "# Everyday-wording quality",
        "",
        "Generated by `python -m app.eval.lay_quality report` from the runs below.",
        f"{len(CASES)} questions phrased the way a non-lawyer asks them "
        f"({sum(not c.held_out for c in CASES)} tuning, {sum(c.held_out for c in CASES)} held out). "
        "Expected sections were picked by reading the statute text; **no lawyer has reviewed them**. "
        "A hit means an expected section was among the 4 sources given to the answer model.",
        "",
        "| Run | Split | Vectors | n | hit@4 | MRR | Refused | Verified | Unverified shown | Mean score |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for path in runs:
        data = json.loads(path.read_text(encoding="utf-8"))
        s = data["summary"]
        kind = "answers" if "_answers_" in path.name else "retrieval"
        vectors = "on" if path.stem.endswith("_vec") else "off" if path.stem.endswith("_novec") else "on"
        lines.append(
            f"| {data['label']} ({kind}) | {data['split']} | {vectors} | {s['n']} | {s['hit_at_4']} | {s['mrr']} | "
            f"{s.get('abstained', '')} | {s.get('verified_total', '')} | {s.get('unverified_shown_total', '')} | "
            f"{s.get('mean_score_answered', '') or ''} |"
        )
    (EVAL_REPORTS_DIR / "LAY_QUALITY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()

