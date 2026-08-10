"""
Chat endpoint. Thin wrapper over app.pipeline.graph.run_query -- the route
handler's job is request/response shaping only; all real logic (retrieval,
verification, safety, evidence scoring) lives in the pipeline, which is
tested independently of FastAPI (see tests/test_pipeline_graph.py).
"""
from __future__ import annotations

import threading

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import CORPUS_DB_PATH
from app.corpus.repository import SQLiteCorpusRepository
from app.llm.provider import LLMProvider
from app.pipeline.graph import run_query

router = APIRouter(prefix="/api/v1", tags=["chat"])

# One repository + provider per process, not per request -- both hold a
# long-lived connection/cache that would be wasted work to reopen every call.
_repo: SQLiteCorpusRepository | None = None
_llm: LLMProvider | None = None

# FastAPI dispatches sync ('def') route handlers to a worker threadpool, so
# the single shared SQLite connection above CAN be touched by two requests
# on two different threads at once. sqlite3.Connection is not safe for
# genuinely concurrent use even with check_same_thread=False (see
# app/corpus/schema.py's get_connection). This lock serializes access at
# the actual concurrency boundary -- request handling -- rather than deep
# inside the repository, where dozens of call sites hold the connection
# across multiple .execute() calls and a lock on _conn() alone wouldn't
# cover the gap between them.
_db_lock = threading.Lock()


def _get_repo() -> SQLiteCorpusRepository:
    global _repo
    if _repo is None:
        _repo = SQLiteCorpusRepository(str(CORPUS_DB_PATH))
    return _repo


def _get_llm() -> LLMProvider:
    global _llm
    if _llm is None:
        _llm = LLMProvider()
    return _llm


class ChatRequest(BaseModel):
    message: str
    mode: str = "consultant"


class SourceOut(BaseModel):
    label: str
    title: str
    source_type: str
    act_name: str | None = None
    section_no: str | None = None
    text: str | None = None  # the exact section/judgment text, not a summary
    url: str | None = None   # official source URL, when known (see app/ingest/load_statutes.py)


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


# SECTION sources (bare-act text) are usually short -- show the exact,
# untruncated definition. JUDGMENT sources can run to tens of thousands of
# characters; "the exact text" there means an excerpt, not the whole
# document, since the point is showing what was actually cited, not
# reproducing a full judgment in a chat response.
_SECTION_TEXT_CAP = 4000
_JUDGMENT_TEXT_CAP = 1500


def _source_out(s, repo: SQLiteCorpusRepository) -> SourceOut:
    row = repo.get_source(s.source_id)
    cap = _SECTION_TEXT_CAP if s.source_type == "SECTION" else _JUDGMENT_TEXT_CAP
    text = row["full_text"][:cap] if row else s.text
    url = row["url"] if row else None
    return SourceOut(
        label=s.label, title=s.title, source_type=s.source_type,
        act_name=s.act_name, section_no=s.section_no, text=text, url=url,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # Locks for the whole pipeline call, LLM generation included, not just
    # the DB access -- coarser than necessary for a multi-user service (it
    # serializes concurrent requests behind each other's full LLM latency),
    # but this project is explicitly single-local-user scope (no auth/roles
    # until that's actually needed), so correctness over the SQLite race
    # wins over throughput no real user needs yet.
    with _db_lock:
        state = run_query(req.message, _get_repo(), _get_llm(), mode=req.mode)
        sources = [_source_out(s, _get_repo()) for s in state.retrieved_sources]
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
    )
