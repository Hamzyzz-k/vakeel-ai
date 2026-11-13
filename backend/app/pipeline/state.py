"""
The single state object threaded through every pipeline step (spec section 53),
plus the trace that makes the run auditable (spec section 54).

There is deliberately no agent framework here. A plain dataclass plus an
explicit list of steps keeps the control flow visible -- which is the thing
actually being examined in a viva -- and makes observability free: every step
appends to `trace`, so "why did the system give this answer?" is answerable by
reading one object. Spec section 32 explicitly permits a custom state machine.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

Mode = Literal["advice", "research"]


@dataclass
class RetrievedSource:
    """A candidate piece of evidence, carrying the citation label the model
    is allowed to use for it. The label (S1, S2, ...) is assigned by us, not
    by the model -- that is what makes closed-set citation enforceable."""
    label: str          # 'S1', 'S2', ...
    source_id: str
    title: str
    text: str
    source_type: str
    authority_level: int | None = None
    court: str | None = None
    date: str | None = None
    section_no: str | None = None
    act_name: str | None = None
    retrieval_score: float | None = None
    retrieval_method: str = "bm25"


@dataclass
class VerifiedClaim:
    """One sentence of the generated answer, with its verification outcome."""
    sentence: str
    cited_labels: list[str]
    exists: bool                 # every cited label was in the supplied set
    supported: bool              # cited text entails the sentence
    support_score: float | None = None
    rejection_reason: str | None = None


@dataclass
class TraceEvent:
    step: str
    detail: dict[str, Any]
    duration_ms: float


@dataclass
class LegalQueryState:
    user_query: str
    mode: Mode = "advice"

    # -- intake (LLM call 1) ---------------------------------------------
    jurisdiction: dict[str, Any] = field(default_factory=lambda: {"country": "India", "state": None})
    legal_domain: str | None = None
    issues: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    missing_information: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    # Honest product-scope signal. The live product corpus is intentionally
    # smaller than "Indian law" as a whole, so unsupported areas must be
    # identified before retrieval can substitute a merely similar Act.
    coverage: dict[str, Any] = field(default_factory=dict)
    # Phase 9 (spec section 57): populated when the query references an IPC
    # 1860 section this project has a verified BNS 2023 mapping for. See
    # app/legal/ipc_bns_mapping.py and app/legal/query_bridge.py.
    temporal_notes: list[str] = field(default_factory=list)

    # -- retrieval (deterministic) ---------------------------------------
    retrieved_sources: list[RetrievedSource] = field(default_factory=list)

    # -- reasoning (LLM call 2) ------------------------------------------
    raw_answer: str = ""
    counterarguments: list[str] = field(default_factory=list)
    generation_mode: str = "llm"
    provider_error: str | None = None
    # Research mode only (spec section 18's IRAC structure): raw text per
    # section, pre-verification. Populated instead of raw_answer when
    # mode == "research" -- see app/pipeline/graph.py's run_reasoning.
    irac_sections: dict[str, str] = field(default_factory=dict)

    # -- verification (deterministic, no LLM) ----------------------------
    verified_claims: list[VerifiedClaim] = field(default_factory=list)
    rejected_claims: list[VerifiedClaim] = field(default_factory=list)
    evidence_score: dict[str, Any] = field(default_factory=dict)
    # Phase 7 (spec section 20): OVERRULES/DISTINGUISHES relationships found
    # between the retrieved sources, via app/pipeline/citation_graph.py.
    # Each dict mirrors ConflictFinding's fields (kept as dicts, not the
    # dataclass, so this stays JSON-serializable for the API response).
    conflicts: list[dict[str, Any]] = field(default_factory=list)

    # -- safety + output --------------------------------------------------
    safety_flags: list[str] = field(default_factory=list)
    abstained: bool = False
    abstain_reason: str | None = None
    final_answer: str = ""

    trace: list[TraceEvent] = field(default_factory=list)
    # Called with each finished TraceEvent as it is recorded; the streaming
    # endpoint uses it to show real progress. Every step already records
    # itself, so this needs no change to the pipeline's control flow.
    on_event: Callable[[TraceEvent, "LegalQueryState"], None] | None = field(
        default=None, repr=False, compare=False,
    )

    def record(self, step: str, detail: dict[str, Any], started_at: float) -> None:
        event = TraceEvent(step=step, detail=detail, duration_ms=(time.perf_counter() - started_at) * 1000)
        self.trace.append(event)
        if self.on_event is not None:
            self.on_event(event, self)

    def sources_by_label(self) -> dict[str, RetrievedSource]:
        return {s.label: s for s in self.retrieved_sources}
