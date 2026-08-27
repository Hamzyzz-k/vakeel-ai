"""Download and parse a catalogue batch without activating it.

The report is evidence for the human review step: source resolution alone
is insufficient because a valid official PDF can still defeat the generic
section parser.

Run: python -m app.ingest.verify_statute_batch --tranche 1
"""
from __future__ import annotations

import argparse
import json

from app.ingest.load_statutes import (
    STATUTES_DIR,
    _section_key,
    extract_act_schedule,
    extract_pdf_text,
    extract_trailing_schedule,
    split_constitution_articles,
    split_into_rules,
    split_into_sections,
    split_limitation_schedule_articles,
)
from app.ingest.prepare_product_corpus import download_statute
from app.legal.statute_catalog import STATUTE_CATALOG


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tranche", type=int, choices=(1, 2, 3, 4), required=True)
    parser.add_argument("--include-ready", action="store_true")
    args = parser.parse_args()

    specs = [
        spec for spec in STATUTE_CATALOG
        if spec.tranche == args.tranche
        and spec.source_url
        and (args.include_ready or not spec.ingestion_enabled)
    ]
    report = []
    for spec in specs:
        try:
            path = download_statute(spec)
            full_text = extract_pdf_text(path)
            if spec.parser_profile == "constitution_articles":
                sections = split_constitution_articles(full_text)
            elif spec.instrument_kind == "rules":
                sections = split_into_rules(full_text)
            else:
                sections = split_into_sections(full_text)
            number_groups = [[number for number, _title, _text in sections if number]]
            if spec.parser_profile == "sections_and_limitation_schedule":
                schedule_articles = split_limitation_schedule_articles(full_text)
                sections = [*sections, *schedule_articles]
                number_groups.append([
                    number for number, _title, _text in schedule_articles if number
                ])
            elif spec.parser_profile in {"sections_and_schedule", "rules_and_schedule"} and extract_act_schedule(full_text):
                sections = [*sections, ("SCHEDULE", "Schedule", "")]
            elif spec.parser_profile == "sections_and_trailing_schedule":
                numbered = [number for number, _title, _text in sections if number]
                if numbered and extract_trailing_schedule(full_text, numbered[-1]):
                    sections = [*sections, ("SCHEDULE", "Schedule", "")]
            key_groups = [
                [_section_key(number) for number in numbers]
                for numbers in number_groups
            ]
            sequential = bool(key_groups[0]) and all(
                all(left < right for left, right in zip(keys, keys[1:]))
                for keys in key_groups
            )
            count_matches = (
                spec.expected_sections is not None
                and len(sections) == spec.expected_sections
            )
            if not sequential:
                status = "parser_review_required"
            elif spec.expected_sections is None:
                status = "candidate_parse_requires_review"
            elif not count_matches:
                status = "expected_count_mismatch"
            else:
                status = "verified"
            report.append({
                "key": spec.key,
                "status": status,
                "path": str(STATUTES_DIR / spec.filename),
                "section_count": len(sections),
                "first_section": sections[0][0] if sections else None,
                "last_section": sections[-1][0] if sections else None,
                "sequential": sequential,
                "sample_titles": [title for _number, title, _text in sections[:3]],
            })
        except Exception as exc:
            report.append({"key": spec.key, "status": "error", "error": str(exc)})
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
