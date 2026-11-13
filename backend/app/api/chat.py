"""
Chat endpoint. Thin wrapper over app.pipeline.graph.run_query -- the route
handler's job is request/response shaping only; all real logic (retrieval,
verification, safety, evidence scoring) lives in the pipeline, which is
tested independently of FastAPI (see tests/test_pipeline_graph.py).
"""
from __future__ import annotations

import json
import logging
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.config import CORPUS_DB_PATH, settings
from app.corpus.repository import SQLiteCorpusRepository
from app.llm.provider import LLMProvider
from app.pipeline.citation import UNCITED_REASON, UNSUPPORTED_REASON
from app.pipeline.graph import run_query

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = logging.getLogger("uvicorn.error")

# One repository + provider per process, not per request -- both hold a
# long-lived connection/cache that would be wasted work to reopen every call.
_repo: SQLiteCorpusRepository | None = None
_llm: LLMProvider | None = None

# FastAPI dispatches sync ('def') route handlers to a worker threadpool, so
# requests run concurrently. That used to need a global lock around the
# whole pipeline because one SQLite connection was shared by every thread;
# the repository now gives each thread its own connection and the LLM cache
# locks its own, so requests no longer queue behind each other's LLM calls.
# This lock only guards the lazy creation of the two singletons below.
_init_lock = threading.Lock()


def _get_repo() -> SQLiteCorpusRepository:
    global _repo
    if _repo is None:
        with _init_lock:
            if _repo is None:
                _repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    return _repo


def _get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        with _init_lock:
            if _llm is None:
                _llm = LLMProvider()
    return _llm


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)
    mode: Literal["advice", "research"] = "advice"


class SourceOut(BaseModel):
    label: str
    title: str
    source_type: str
    act_name: str | None = None
    section_no: str | None = None
    text: str | None = None  # the exact section/judgment text, not a summary
    url: str | None = None   # official source URL, when known (see app/ingest/load_statutes.py)
    supports: list[str] = Field(default_factory=list)


class ConflictOut(BaseModel):
    source_a: str
    source_b: str
    relationship: str
    stronger: str | None
    reason: str


class ChatResponse(BaseModel):
    answer: str
    abstained: bool
    abstain_reason: str | None
    evidence_score: dict
    sources: list[SourceOut]
    jurisdiction: dict
    legal_domain: str | None
    safety_flags: list[str]
    conflicts: list[ConflictOut]
    temporal_notes: list[str]
    missing_information: list[str]
    coverage: dict
    generation_mode: str
    provider_error: str | None
    # Sentences the model wrote that no supplied source supports, or that
    # carry no citation -- often practical steps ("send a written notice
    # first"). Shown apart from the answer and marked unverified, never
    # mixed into it. Fabricated labels and number/negation contradictions
    # are never shown.
    unverified: list[str] = Field(default_factory=list)
    # Milliseconds per pipeline stage, so slowness on a live host can be
    # read straight from the browser's network tab.
    timings: dict[str, float] = Field(default_factory=dict)


# SECTION sources (bare-act text) are usually short -- show the exact,
# untruncated definition. JUDGMENT sources can run to tens of thousands of
# characters; "the exact text" there means an excerpt, not the whole
# document, since the point is showing what was actually cited, not
# reproducing a full judgment in a chat response.
_SECTION_TEXT_CAP = 4000
_JUDGMENT_TEXT_CAP = 1500


def _source_out(s, repo: SQLiteCorpusRepository, supports: list[str] | None = None) -> SourceOut:
    row = repo.get_source(s.source_id)
    cap = _SECTION_TEXT_CAP if s.source_type in {"SECTION", "RULE", "ARTICLE", "SCHEDULE"} else _JUDGMENT_TEXT_CAP
    text = row["full_text"][:cap] if row else s.text
    url = row["url"] if row else None
    return SourceOut(
        label=s.label, title=s.title, source_type=s.source_type,
        act_name=s.act_name, section_no=s.section_no, text=text, url=url,
        supports=supports or [],
    )


_SHOWN_AS_UNVERIFIED = {UNSUPPORTED_REASON, UNCITED_REASON}
# An uncited sentence never meets the number check (that needs a cited
# source), so one carrying a figure, a provision or a case name ("file
# within 45 days", "under Section 12", "X v. Y") could be invented outright.
# Those stay hidden; only plain-language suggestions are shown.
_SPECIFIC_LEGAL_DETAIL = re.compile(r"\d|\b(?:section|sections|rule|article|clause)\b|\s+v\.?\s+|\b[A-Z][a-z]+ Act\b", re.IGNORECASE)


def _shown_as_unverified(claim) -> bool:
    if claim.rejection_reason not in _SHOWN_AS_UNVERIFIED:
        return False
    return claim.rejection_reason != UNCITED_REASON or not _SPECIFIC_LEGAL_DETAIL.search(claim.sentence)


def _timings(state) -> dict[str, float]:
    timings: dict[str, float] = {}
    for event in state.trace:
        timings[event.step] = round(timings.get(event.step, 0.0) + event.duration_ms, 1)
    return timings


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    started = time.perf_counter()
    state = run_query(req.message, _get_repo(), _get_llm(), mode=req.mode)
    response = build_chat_response(state)
    logger.info("chat mode=%s total_ms=%.0f stages=%s", req.mode, (time.perf_counter() - started) * 1000, response.timings)
    return response


# Which user-facing stage starts once a pipeline step finishes. Events are
# real (from state.record), not a timer, so the UI only ever claims work
# that is actually under way.
_NEXT_STAGE = {
    "intake": "searching", "intake_deterministic": "searching", "intake_fallback": "searching",
    "retrieval": "writing",
    "reasoning": "checking", "reasoning_research": "checking",
    "reasoning_failed": "checking", "reasoning_research_failed": "checking",
}
_STREAM_TIMEOUT_SECONDS = 180
# Streamed chats run here rather than on a fresh thread each: the
# repository keeps one SQLite connection per thread until shutdown, so a
# thread per request leaked a connection per request (measured: 10 streams,
# 10 extra connections). Reused workers bound that at the pool size.
_stream_workers = ThreadPoolExecutor(max_workers=8, thread_name_prefix="chat-stream")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/chat/stream")
def chat_stream(req: ChatRequest) -> StreamingResponse:
    """Same answer as /chat, sent as server-sent events: `stage` events as
    the pipeline moves (with the sections found once retrieval ends), then
    one `final` event carrying the /chat JSON, or an `error` event. No
    unverified model text is ever streamed -- the answer arrives whole,
    after citation checks."""
    events: queue.Queue[str | None] = queue.Queue()
    repo, llm = _get_repo(), _get_llm()

    def on_event(event, state) -> None:
        stage = _NEXT_STAGE.get(event.step)
        if stage is None:
            return
        data: dict = {"stage": stage}
        if event.step == "retrieval":
            data["sources"] = [source.title for source in state.retrieved_sources]
        events.put(_sse("stage", data))

    def work() -> None:
        started = time.perf_counter()
        try:
            state = run_query(req.message, repo, llm, mode=req.mode, on_event=on_event)
            response = build_chat_response(state)
            logger.info(
                "chat/stream mode=%s total_ms=%.0f stages=%s",
                req.mode, (time.perf_counter() - started) * 1000, response.timings,
            )
            events.put(_sse("final", response.model_dump()))
        except Exception:  # noqa: BLE001 -- reported to the client as one error event
            logger.exception("chat/stream failed")
            events.put(_sse("error", {"detail": "The answer could not be generated. Try again."}))
        finally:
            events.put(None)

    def stream():
        yield _sse("stage", {"stage": "reading"})
        _stream_workers.submit(work)
        while True:
            try:
                item = events.get(timeout=_STREAM_TIMEOUT_SECONDS)
            except queue.Empty:
                yield _sse("error", {"detail": "The answer took too long. Try again."})
                return
            if item is None:
                return
            yield item

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        # Proxies must pass each event on as it is written, not buffer the
        # whole response.
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


def build_chat_response(state) -> ChatResponse:
    claims_by_label: dict[str, list[str]] = {}
    for claim in state.verified_claims:
        for label in claim.cited_labels:
            claims_by_label.setdefault(label, []).append(claim.sentence)
    # The UI should show authorities actually used in the answer, not
    # every candidate the retriever considered.
    sources = [
        _source_out(s, _get_repo(), claims_by_label[s.label])
        for s in state.retrieved_sources
        if s.label in claims_by_label
    ]
    return ChatResponse(
        answer=state.final_answer,
        abstained=state.abstained,
        abstain_reason=state.abstain_reason,
        evidence_score=state.evidence_score,
        sources=sources,
        jurisdiction=state.jurisdiction,
        legal_domain=state.legal_domain,
        safety_flags=state.safety_flags,
        conflicts=[ConflictOut(**c) for c in state.conflicts],
        temporal_notes=state.temporal_notes,
        missing_information=state.missing_information,
        coverage=state.coverage,
        generation_mode=state.generation_mode,
        provider_error=state.provider_error if settings.expose_provider_errors else None,
        unverified=[] if state.abstained else [
            claim.sentence if claim.sentence.endswith((".", "?", "!")) else f"{claim.sentence}."
            for claim in state.rejected_claims if _shown_as_unverified(claim)
        ],
        timings=_timings(state),
    )
