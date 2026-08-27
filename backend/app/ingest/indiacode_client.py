"""Resolve official India Code records without trusting search snippets.

India Code runs DSpace.  An Act search result is only useful after walking
item -> ORIGINAL bundle -> English PDF bitstream.  Some duplicate catalogue
items have no PDF, so discovery must verify that full chain before enabling
ingestion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx


API_ROOT = "https://indiacode.gov.in/server/api"


@dataclass(frozen=True)
class ResolvedStatute:
    title: str
    item_uuid: str
    act_id: str | None
    bitstream_uuid: str
    bitstream_name: str

    @property
    def source_url(self) -> str:
        return f"{API_ROOT}/core/bitstreams/{self.bitstream_uuid}/content"


class IndiaCodeResolutionError(RuntimeError):
    pass


def _normalise_title(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _metadata_values(obj: dict[str, Any], field: str) -> list[str]:
    values = obj.get("metadata", {}).get(field, [])
    return [str(entry.get("value", "")).strip() for entry in values if entry.get("value")]


def _embedded(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get("_embedded", {}).get(key, [])
    return value if isinstance(value, list) else []


def _search_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    search = payload.get("_embedded", {}).get("searchResult", {})
    objects = search.get("_embedded", {}).get("objects", [])
    items = []
    for result in objects:
        item = result.get("_embedded", {}).get("indexableObject")
        if isinstance(item, dict):
            items.append(item)
    return items


def choose_exact_item(payload: dict[str, Any], expected_title: str) -> list[dict[str, Any]]:
    """Return exact-title candidates; duplicates are resolved by PDF checks."""
    expected = _normalise_title(expected_title)
    return [
        item for item in _search_items(payload)
        if item.get("type") in {None, "item"}
        if any(_normalise_title(title) == expected for title in _metadata_values(item, "dc.title"))
    ]


def choose_original_bundle(payload: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (bundle for bundle in _embedded(payload, "bundles") if str(bundle.get("name", "")).upper() == "ORIGINAL"),
        None,
    )


def choose_english_pdf(payload: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for bitstream in _embedded(payload, "bitstreams"):
        name = str(bitstream.get("name", ""))
        if not name.casefold().endswith(".pdf"):
            continue
        languages = [value.casefold() for value in _metadata_values(bitstream, "dc.title.language")]
        if "hindi" in languages:
            continue
        candidates.append(bitstream)
    if not candidates:
        return None

    def score(bitstream: dict[str, Any]) -> tuple[int, int]:
        languages = [value.casefold() for value in _metadata_values(bitstream, "dc.title.language")]
        name = str(bitstream.get("name", ""))
        return (1 if "english" in languages else 0, 0 if name.casefold().startswith("h") else 1)

    return max(candidates, key=score)


class IndiaCodeClient:
    def __init__(self, client: httpx.Client | None = None, timeout: float = 30.0):
        self._owns_client = client is None
        self.client = client or httpx.Client(
            base_url=API_ROOT,
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=10.0),
            headers={"User-Agent": "VakeelAI statute-source verifier/1.0"},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "IndiaCodeClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _get_json(self, path: str, **params: Any) -> dict[str, Any]:
        response = self.client.get(path, params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise IndiaCodeResolutionError(f"Unexpected response from {path}")
        return payload

    def resolve(self, title: str, collection_uuid: str | None = None) -> ResolvedStatute:
        search_params: dict[str, Any] = {
            "query": f'dc.title:"{title}"',
            "size": 20,
        }
        if collection_uuid:
            search_params["scope"] = collection_uuid
        search_payload = self._get_json(
            "/discover/search/objects",
            **search_params,
        )
        candidates = choose_exact_item(search_payload, title)
        if not candidates:
            raise IndiaCodeResolutionError(f"No exact India Code Act record found for {title!r}")

        failures: list[str] = []
        for item in candidates:
            item_uuid = str(item.get("uuid", ""))
            if not item_uuid:
                continue
            bundles = self._get_json(f"/core/items/{item_uuid}/bundles", size=20)
            original = choose_original_bundle(bundles)
            if not original or not original.get("uuid"):
                failures.append(f"{item_uuid}: no ORIGINAL bundle")
                continue
            bitstreams = self._get_json(f"/core/bundles/{original['uuid']}/bitstreams", size=20)
            pdf = choose_english_pdf(bitstreams)
            if not pdf or not pdf.get("uuid"):
                failures.append(f"{item_uuid}: no English PDF")
                continue
            act_ids = _metadata_values(item, "dc.identifier.act_id")
            canonical_titles = _metadata_values(item, "dc.title")
            return ResolvedStatute(
                title=canonical_titles[0] if canonical_titles else title,
                item_uuid=item_uuid,
                act_id=act_ids[0] if act_ids else None,
                bitstream_uuid=str(pdf["uuid"]),
                bitstream_name=str(pdf.get("name", "")),
            )

        detail = "; ".join(failures) or "records were incomplete"
        raise IndiaCodeResolutionError(f"Exact records for {title!r} had no usable official PDF: {detail}")
