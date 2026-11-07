"""
Document upload + analysis endpoint (spec section 21).

Deliberately no LLM call in this phase: extraction is PyMuPDF, topic
detection and missing-clause flagging are regex, and "relevant law" is the
same deterministic retrieval the chat pipeline uses. This means there is no
prompt-injection surface to defend here at all (spec section 39's concern
about documents containing "ignore previous instructions"-style text) --
not because it was mitigated, but because no LLM ever sees the uploaded
text in this phase. If a future phase adds LLM-based clause explanation,
that prompt must follow the same evidence-not-instruction framing already
used in app/pipeline/graph.py's REASONING_PROMPT_TEMPLATE.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.api.chat import _get_repo
from app.documents.analyzer import analyze_document
from app.documents.extractor import extract_document

router = APIRouter(prefix="/api/v1", tags=["documents"])
logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB -- generous for a contract/notice, not for a mistake
_MAX_TEXT_UPLOAD_BYTES = 2 * 1024 * 1024
_READ_CHUNK_BYTES = 1024 * 1024
_ALLOWED_SUFFIXES = (".pdf", ".txt")


class ClauseOut(BaseModel):
    number: int | None
    heading: str | None
    text: str
    detected_topics: list[str]
    relevant_source_ids: list[str]


class DocumentAnalysisOut(BaseModel):
    filename: str
    n_pages: int
    n_clauses: int
    detected_topics: list[str]
    missing_topics: list[str]
    clauses: list[ClauseOut]


@router.post("/documents/upload", response_model=DocumentAnalysisOut)
async def upload_document(file: UploadFile = File(...)) -> DocumentAnalysisOut:
    filename = Path(file.filename or "upload").name
    if not filename.lower().endswith(_ALLOWED_SUFFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(_ALLOWED_SUFFIXES)}")

    chunks: list[bytes] = []
    total_bytes = 0
    while chunk := await file.read(_READ_CHUNK_BYTES):
        total_bytes += len(chunk)
        if total_bytes > _MAX_UPLOAD_BYTES:
            await file.close()
            raise HTTPException(status_code=413, detail=f"File exceeds {_MAX_UPLOAD_BYTES // (1024*1024)}MB limit")
        chunks.append(chunk)
    await file.close()
    file_bytes = b"".join(chunks)
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if filename.lower().endswith(".pdf") and not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="File extension is PDF but the content is not a valid PDF")
    if filename.lower().endswith(".txt"):
        if total_bytes > _MAX_TEXT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Text files are limited to 2MB")
        if b"\x00" in file_bytes[:4096]:
            raise HTTPException(status_code=400, detail="Binary content is not accepted as a text document")

    # This handler is async (the upload is read with await), so anything
    # blocking must leave the event loop. PDF parsing is CPU-bound and
    # analysis runs SQLite queries; run inline, either one stalls every
    # other request, /health included, until it finishes.
    try:
        doc = await run_in_threadpool(extract_document, file_bytes, filename)
    except Exception as exc:  # noqa: BLE001 -- a corrupt/unreadable upload is a client error, not a crash
        # The parser's own message names library internals; keep it in the
        # server log and give the client a plain reason.
        logger.warning("Could not extract text from an upload: %s: %s", type(exc).__name__, exc)
        raise HTTPException(
            status_code=422,
            detail="Could not read this file. It may be corrupted or password-protected.",
        ) from exc

    if not doc.full_text.strip():
        raise HTTPException(status_code=422, detail="No extractable text found -- this may be a scanned image PDF (OCR is not supported in this phase)")

    # _get_repo() may build the repository (schema init) on first use, so it
    # runs inside the worker thread too.
    analysis = await run_in_threadpool(lambda: analyze_document(doc, _get_repo()))

    return DocumentAnalysisOut(
        filename=filename,
        n_pages=analysis.n_pages,
        n_clauses=analysis.n_clauses,
        detected_topics=analysis.detected_topics,
        missing_topics=analysis.missing_topics,
        clauses=[
            ClauseOut(number=c.number, heading=c.heading, text=c.text,
                      detected_topics=c.detected_topics, relevant_source_ids=c.relevant_source_ids)
            for c in analysis.clauses
        ],
    )
