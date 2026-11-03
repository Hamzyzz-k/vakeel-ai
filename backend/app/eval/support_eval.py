"""
Claim-support evaluation: which checker should decide whether a cited
source actually supports a sentence?

Closed-set citation makes *existence* airtight; *support* is the half that
needs measurement (see app/pipeline/citation.py). Production has run the
lexical gate alone, and live answers showed it stripping correct paraphrases
-- every measured answer was cut to one or two sentences. This harness
collects real (claim, cited source) pairs from the live pipeline, labels
them with a strict LLM judge, and compares three checkers on held-out pairs:

  lexical  the current word-overlap gate (no model)
  nli      cross-encoder/nli-deberta-v3-small, threshold tuned on the train split
  judge    one batched Groq call per group of pairs

The number/negation vetoes in has_high_impact_contradiction apply to all
three, exactly as they do in production.

Gold labels come from Gemini, not a lawyer, so these numbers measure
agreement with a strict LLM judge. `collect` also writes a 50-pair sample to
spot-check by hand; check that before trusting a small gap between checkers.

Free-tier pacing is built in (Groq gpt-oss-120b: 8,000 tokens/minute), so a
full run takes roughly an hour, most of it waiting.

Run, in order:
  python -m app.eval.support_eval collect
  python -m app.eval.support_eval label
  python -m app.eval.support_eval compare
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

from app.config import CORPUS_DB_PATH, EVAL_REPORTS_DIR, settings
from app.corpus.repository import SQLiteCorpusRepository
from app.eval.product_quality import CASES
from app.llm.provider import LLMProvider
from app.pipeline.citation import has_high_impact_contradiction, nli_entailment_score, verify_claim
from app.pipeline.graph import run_query
from app.pipeline.support_judge import judge_support

PAIRS_PATH = EVAL_REPORTS_DIR / "support_pairs.jsonl"
LABELLED_PATH = EVAL_REPORTS_DIR / "support_pairs_labelled.jsonl"
SPOT_CHECK_PATH = EVAL_REPORTS_DIR / "support_spot_check.jsonl"
REPORT_PATH = EVAL_REPORTS_DIR / "SUPPORT_REPORT.md"

# Lay scenarios phrased the way users actually ask, unlike the mostly
# section-named retrieval cases. Asked in both modes.
LAY_QUERIES = (
    "My landlord in Bangalore is refusing to return my security deposit after I vacated the flat. What can I do?",
    "My cheque given to a supplier bounced for insufficient funds. Can they file a criminal case and within what time?",
    "I bought a phone online and it stopped working within a week, and the seller refuses a refund. What are my options?",
    "Someone hacked my email and is impersonating me to ask my friends for money. Is that a crime?",
    "The police took my brother for questioning without telling us why. What are his rights?",
    "Can WhatsApp messages be used as evidence in court?",
    "The builder delayed handing over my flat by two years. Can I claim interest?",
    "Is an oral agreement to sell land valid?",
    "How long do I have to file a suit to recover money I lent to a friend?",
    "Can I get an injunction to stop my neighbour from blocking my right of way?",
    "Does a gift deed of a house need to be registered?",
    "My car's fitness certificate expired. Can I still drive it?",
    "Can a contract I signed under threat be cancelled?",
    "I was caught riding a bike without a helmet in Bangalore. What penalty applies?",
    "The seller delivered a different model from the one described in the listing. What can I do?",
)

# Groq free tier: 8,000 tokens/minute, and one pipeline query uses ~3.5K.
SECONDS_BETWEEN_QUERIES = 30
JUDGE_BATCH = 8
SECONDS_BETWEEN_JUDGE_CALLS = 15


def _queries() -> list[tuple[str, str]]:
    # Lay scenarios first: they paraphrase the most, which is where the
    # support checker matters, and a run cut short still covers them.
    runs = [(query, "advice") for query in LAY_QUERIES]
    runs += [(query, "research") for query in LAY_QUERIES]
    runs += [(case.query, "advice") for case in CASES]
    return runs


def _split(pair: dict) -> str:
    """Deterministic 60/40 split on the claim text, stable across reruns."""
    digest = int(hashlib.sha256(pair["claim"].encode("utf-8")).hexdigest(), 16)
    return "train" if digest % 10 < 6 else "test"


def _pair_key(pair: dict) -> str:
    return hashlib.sha256(f"{pair['claim']}\x00{pair['evidence']}".encode("utf-8")).hexdigest()


def _read(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def collect() -> None:
    """Run every query through the live pipeline and keep each claim whose
    labels exist -- the only claims where support is actually in question."""
    done = {(row["query"], row["mode"]) for row in _read(PAIRS_PATH)} if PAIRS_PATH.exists() else set()
    llm = LLMProvider()
    with SQLiteCorpusRepository(str(CORPUS_DB_PATH), ensure_schema=False) as repo:
        for index, (query, mode) in enumerate(_queries(), start=1):
            if (query, mode) in done:
                continue
            run_started = time.perf_counter()
            state = run_query(query, repo, llm, mode=mode)
            run_seconds = time.perf_counter() - run_started
            providers =sorted({event.detail.get("provider") for event in state.trace if event.detail.get("provider")})
            by_label = state.sources_by_label()
            rows = []
            for claim in state.verified_claims + state.rejected_claims:
                if not claim.exists:
                    continue
                evidence = "\n".join(f"{by_label[label].title}\n{by_label[label].text}" for label in claim.cited_labels)
                rows.append({
                    "query": query, "mode": mode, "providers": providers,
                    "claim": claim.sentence, "labels": claim.cited_labels, "evidence": evidence,
                    "lexical_supported": claim.supported, "lexical_score": claim.support_score,
                })
            unknown_labels = sum(1 for claim in state.rejected_claims if not claim.exists and claim.cited_labels)
            # One marker row per query keeps resume and the unknown-label
            # rate correct even when a query yields no support pairs.
            rows.append({"query": query, "mode": mode, "providers": providers, "marker": True,
                         "unknown_label_claims": unknown_labels,
                         "total_claims": len(state.verified_claims) + len(state.rejected_claims)})
            with PAIRS_PATH.open("a", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(f"[{index}/{len(_queries())}] {mode:8s} {run_seconds:5.1f}s pairs={len(rows) - 1} providers={providers} {query[:60]}", flush=True)
            # A rerun after a verification change replays cached LLM output
            # and costs no quota, so only pace runs that called a provider.
            if any(not event.detail.get("from_cache", True) for event in state.trace if "provider" in event.detail):
                time.sleep(SECONDS_BETWEEN_QUERIES)

    pairs = [row for row in _read(PAIRS_PATH) if not row.get("marker")]
    sample = sorted(pairs, key=lambda row: hashlib.sha256(row["claim"].encode()).hexdigest())[:50]
    _write(SPOT_CHECK_PATH, [{**row, "human_label": None} for row in sample])
    print(f"{len(pairs)} pairs collected; spot-check sample at {SPOT_CHECK_PATH}")


JUDGE_PROMPT = """You are checking citations in a legal research tool. For each numbered PAIR, decide whether the \
SOURCE TEXT supports the CLAIM.

SUPPORTED: every factual assertion in the claim is stated in, or necessarily follows from, the source text. A faithful \
paraphrase or a plain-language restatement counts. Applying the source's rule to the user's stated facts counts only \
if the rule as stated plainly covers those facts.
NOT_SUPPORTED: the claim adds anything the source does not say -- a deadline, amount, remedy, procedure, exception, \
or condition -- or misstates the source, or only asserts what the source does NOT contain.

Judge strictly from the SOURCE TEXT; ignore your own legal knowledge. Respond with ONLY a JSON object holding one label per pair, in pair order:
{{"labels": ["SUPPORTED" or "NOT_SUPPORTED", ...]}}

{pairs}
"""


def _judge_batch(llm: LLMProvider, batch: list[dict], use_cache: bool = True) -> list[str]:
    pairs = "\n\n".join(
        f"PAIR {i}\nCLAIM: {row['claim']}\nSOURCE TEXT:\n{row['evidence'][:2400]}"
        for i, row in enumerate(batch, start=1)
    )
    # Positional enum labels, not {"pair": n, ...} objects: Gemini's
    # constrained decoding was seen emitting a 6,195-digit integer "pair".
    data, _ = llm.generate_json(
        JUDGE_PROMPT.format(pairs=pairs),
        json_schema={"type": "object", "properties": {"labels": {
            "type": "array", "items": {"type": "string", "enum": ["SUPPORTED", "NOT_SUPPORTED"]},
        }}},
        use_cache=use_cache,
    )
    labels = [str(label).upper() for label in data.get("labels", [])]
    if len(labels) != len(batch):
        return ["UNKNOWN"] * len(batch)  # can't align positions safely
    return labels


def label() -> None:
    """Gold labels from Gemini as a strict offline judge (slow is fine here)."""
    pairs = [row for row in _read(PAIRS_PATH) if not row.get("marker")]
    # The same sentence can cite different evidence in different runs; key
    # on both so neither pairing is dropped.
    labelled = {_pair_key(row): row for row in _read(LABELLED_PATH)} if LABELLED_PATH.exists() else {}
    todo = [row for row in pairs if _pair_key(row) not in labelled]
    gemini = LLMProvider(provider_order=("gemini",))
    for start in range(0, len(todo), JUDGE_BATCH):
        batch = todo[start:start + JUDGE_BATCH]
        try:
            verdicts = _judge_batch(gemini, batch)
        except Exception:  # noqa: BLE001 -- a malformed reply is cached; ask again uncached
            try:
                verdicts = _judge_batch(gemini, batch, use_cache=False)
            except Exception as exc:  # noqa: BLE001 -- excluded from scoring, not fatal
                print(f"judge batch failed twice, marking UNKNOWN: {exc}")
                verdicts = ["UNKNOWN"] * len(batch)
        for row, verdict in zip(batch, verdicts):
            labelled[_pair_key(row)] = {**row, "gold": verdict, "split": _split(row)}
        _write(LABELLED_PATH, list(labelled.values()))
        print(f"labelled {len(labelled)}/{len(pairs)}", flush=True)
        time.sleep(4)


def _metrics(gold: list[bool], predicted: list[bool]) -> dict:
    tp = sum(g and p for g, p in zip(gold, predicted))
    fp = sum((not g) and p for g, p in zip(gold, predicted))
    fn = sum(g and (not p) for g, p in zip(gold, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    accuracy = sum(g == p for g, p in zip(gold, predicted)) / len(gold) if gold else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
            "accepted": tp + fp, "n": len(gold)}


def compare(include_judge: bool = True) -> None:
    rows = [row for row in _read(LABELLED_PATH) if row.get("gold") in {"SUPPORTED", "NOT_SUPPORTED"}]
    train = [row for row in rows if row["split"] == "train"]
    test = [row for row in rows if row["split"] == "test"]

    # NLI scores everything once; the threshold is chosen on train only.
    for row in rows:
        row["nli_score"] = nli_entailment_score(row["claim"], row["evidence"])
        row["veto"] = has_high_impact_contradiction(row["claim"], row["evidence"])

    def nli_predict(row: dict, threshold: float) -> bool:
        return (not row["veto"]) and row["nli_score"] >= threshold

    def train_score(threshold: float) -> tuple[float, float]:
        m = _metrics([r["gold"] == "SUPPORTED" for r in train], [nli_predict(r, threshold) for r in train])
        # Precision first: in a legal tool a wrongly accepted claim is worse
        # than a wrongly stripped one. Require >= lexical's train precision.
        return (m["precision"] >= lexical_train["precision"], m["f1"])

    lexical_train = _metrics(
        [r["gold"] == "SUPPORTED" for r in train],
        [verify_claim(r["claim"], r["evidence"], use_nli=False)[0] for r in train],
    )
    thresholds = [t / 100 for t in range(5, 96, 5)]
    best_threshold = max(thresholds, key=train_score)

    gold = [r["gold"] == "SUPPORTED" for r in test]
    results = {
        "lexical": _metrics(gold, [verify_claim(r["claim"], r["evidence"], use_nli=False)[0] for r in test]),
        f"nli (threshold {best_threshold:.2f})": _metrics(gold, [nli_predict(r, best_threshold) for r in test]),
    }
    if include_judge:
        # The production judge (app/pipeline/support_judge.py), batched the
        # way the pipeline batches it -- one call per answer, so claims share
        # their sources -- so this row measures shipped code. A batch that
        # fails (usually Groq's 8,000 tokens/minute cap) is retried after a
        # minute rather than silently scored as all-rejected.
        # Only the judge's first configured model: a fallback would silently
        # mix models into one row.
        judge_model = settings.support_judge_order[0]
        groq = LLMProvider(provider_order=(judge_model,))
        by_answer: dict[tuple[str, str], list[int]] = {}
        for index, row in enumerate(test):
            by_answer.setdefault((row["query"], row["mode"]), []).append(index)
        verdicts: list[bool | None] = [None] * len(test)
        for indexes in by_answer.values():
            pairs = [(test[i]["claim"], test[i]["evidence"]) for i in indexes]
            judged = judge_support(groq, pairs)
            if judged is None:
                time.sleep(60)
                judged = judge_support(groq, pairs, use_cache=False)
            for i, verdict in zip(indexes, judged or [None] * len(indexes)):
                verdicts[i] = verdict
            time.sleep(SECONDS_BETWEEN_JUDGE_CALLS)
        scored = [i for i, verdict in enumerate(verdicts) if verdict is not None]
        results[f"LLM judge `{judge_model}` ({len(scored)}/{len(test)} judged)"] = _metrics(
            [gold[i] for i in scored], [verdicts[i] and not test[i]["veto"] for i in scored],
        )

    markers = [row for row in _read(PAIRS_PATH) if row.get("marker")]
    unknown = sum(row["unknown_label_claims"] for row in markers)
    total_claims = sum(row["total_claims"] for row in markers)
    lines = [
        "# Claim-support checker comparison",
        "",
        f"Pairs: {len(rows)} labelled ({len(train)} train / {len(test)} test), from {len(markers)} live pipeline runs. "
        f"Gold labels: Gemini as a strict judge (agreement with an LLM judge, not a lawyer).",
        f"Support rate in gold: {sum(r['gold'] == 'SUPPORTED' for r in rows) / len(rows):.0%}. "
        f"Unknown-label claims (e.g. a section number written as `[S45]`): {unknown}/{total_claims} "
        f"({unknown / total_claims:.1%} of all claims).",
        "",
        "| Checker (test split) | Precision | Recall | F1 | Accuracy | Accepted |",
        "|---|---|---|---|---|---|",
    ]
    for name, m in results.items():
        lines.append(f"| {name} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | {m['accuracy']:.2f} | {m['accepted']}/{m['n']} |")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "collect":
        collect()
    elif command == "label":
        label()
    elif command == "compare":
        compare(include_judge="--no-judge" not in sys.argv)
    else:
        raise SystemExit("usage: python -m app.eval.support_eval collect | label | compare [--no-judge]")
