"""Public, read-only catalogue endpoint used by the landing page."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.legal.statute_catalog import INGESTIBLE_STATUTES

router = APIRouter(prefix="/api/v1", tags=["coverage"])


class CoverageItem(BaseModel):
    key: str
    title: str
    domain: str
    jurisdiction: str
    instrument_kind: str
    provision_count: int | None
    source_url: str | None
    source_note: str | None


@router.get("/coverage", response_model=list[CoverageItem])
def coverage() -> list[CoverageItem]:
    return [CoverageItem(
        key=spec.key,
        title=spec.title,
        domain=spec.domain,
        jurisdiction=spec.jurisdiction,
        instrument_kind=spec.instrument_kind,
        provision_count=spec.expected_sections,
        source_url=spec.source_url,
        source_note=spec.source_note,
    ) for spec in INGESTIBLE_STATUTES]
