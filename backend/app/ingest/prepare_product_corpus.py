"""Gather the verified statute PDFs and build the deployable product corpus."""
from __future__ import annotations

import shutil
from pathlib import Path

import httpx

from app.config import BACKEND_ROOT
from app.ingest.load_statutes import STATUTES_DIR, main as load_statutes
from app.legal.statute_catalog import INGESTIBLE_STATUTES, StatuteSpec

_MAX_STATUTE_BYTES = 20 * 1024 * 1024
# Copies of the India Code PDFs shipped with the backend. Image builds use
# these instead of downloading: indiacode.gov.in started answering 401 to
# the build's plain HTTP client (2026-11-07), which failed every deploy.
# The download below remains for a statute that isn't bundled yet.
BUNDLED_STATUTES_DIR = BACKEND_ROOT / "statutes"


def download_statute(spec: StatuteSpec) -> Path:
    if not spec.source_url:
        raise ValueError(f"{spec.key} has no verified source URL")
    destination = STATUTES_DIR / spec.filename
    if destination.exists() and destination.read_bytes()[:5] == b"%PDF-":
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    bundled = BUNDLED_STATUTES_DIR / spec.filename
    if bundled.exists() and bundled.read_bytes()[:5] == b"%PDF-":
        shutil.copyfile(bundled, destination)
        return destination

    temporary = destination.with_suffix(".pdf.part")
    total = 0
    first_bytes = b""
    try:
        with httpx.stream("GET", spec.source_url, follow_redirects=True, timeout=60.0) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(64 * 1024):
                    total += len(chunk)
                    if total > _MAX_STATUTE_BYTES:
                        raise RuntimeError(f"{spec.filename} exceeded the download size limit")
                    if not first_bytes:
                        first_bytes = chunk[:5]
                    output.write(chunk)
        if first_bytes != b"%PDF-":
            raise RuntimeError(f"{spec.filename} did not return PDF content")
        temporary.replace(destination)
        return destination
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    for spec in INGESTIBLE_STATUTES:
        print(f"Preparing {spec.filename}")
        download_statute(spec)
    load_statutes()


if __name__ == "__main__":
    main()
