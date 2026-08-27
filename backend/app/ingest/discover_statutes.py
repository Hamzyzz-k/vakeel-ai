"""Print verified India Code metadata for planned catalogue entries.

This command is intentionally read-only.  A maintainer reviews the output,
checks parser quality, and only then copies identifiers into the catalogue
and enables ingestion.

Run: python -m app.ingest.discover_statutes --tranche 1
"""
from __future__ import annotations

import argparse
import json

from app.ingest.indiacode_client import IndiaCodeClient
from app.legal.statute_catalog import STATUTE_CATALOG


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tranche", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--include-ready", action="store_true")
    args = parser.parse_args()

    specs = [
        spec for spec in STATUTE_CATALOG
        if spec.tranche == args.tranche
        and (args.include_ready or not spec.ingestion_enabled)
    ]
    results = []
    with IndiaCodeClient() as client:
        for spec in specs:
            try:
                resolved = client.resolve(spec.discovery_title, spec.collection_uuid)
                results.append({
                    "key": spec.key,
                    "status": "resolved",
                    "title": resolved.title,
                    "act_id": resolved.act_id,
                    "item_uuid": resolved.item_uuid,
                    "bitstream_uuid": resolved.bitstream_uuid,
                    "bitstream_name": resolved.bitstream_name,
                    "source_url": resolved.source_url,
                })
            except Exception as exc:
                results.append({"key": spec.key, "status": "error", "error": str(exc)})

    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
