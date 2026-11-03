"""
Chat endpoint. Thin wrapper over app.pipeline.graph.run_query -- the route
handler's job is request/response shaping only; all real logic (retrieval,
verification, safety, evidence scoring) lives in the pipeline, which is
tested independently of FastAPI (see tests/test_pipeline_graph.py).
"""
from __future__ import annotations

import threading
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config import CORPUS_DB_PATH, settings
from app.corpus.repository import SQLiteCorpusRepository
from app.llm.provider import LLMProvider
from app.pipeline.graph import run_query

router = APIRouter(prefix="/api/v1", tags=["chat"])

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


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    state = run_query(req.message, _get_repo(), _get_llm(), mode=req.mode)
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
    )
