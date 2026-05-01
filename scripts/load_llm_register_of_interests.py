#!/usr/bin/env python3
"""Load LLM-extracted Register of Interests items into the live database.

Reads the JSONL artifacts produced by
`scripts/llm_extract_register_of_interests.py` under
`data/processed/llm_register_of_interests/` and upserts one row per
extracted item into `llm_register_of_interests_observation`
(introduced by migration 040).

Each input JSONL row carries `items: [...]` — the list of disclosure
items the LLM extracted from one section. The loader unpacks the
list, assigns a stable `item_index` (the array position within the
section), and upserts on (source_id, section_number, item_index,
prompt_version) so re-loading the same JSONL is idempotent.

Skipped sections (preamble + nil returns) emit no rows by design;
the absence of rows IS the data.

Operational shape:

    cd <project root>
    DATABASE_URL=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \\
        backend/.venv/bin/python scripts/load_llm_register_of_interests.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg  # type: ignore
from psycopg.types.json import Jsonb  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from au_politics_money.config import PROCESSED_DIR  # noqa: E402


def _select_jsonl_files(processed_dir: Path) -> list[Path]:
    return sorted(
        (processed_dir / "llm_register_of_interests").glob("*.jsonl")
    )


def _read_records(jsonl_path: Path):
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"  [{jsonl_path.name}:{line_no}] skipping malformed JSON: {exc}",
                    file=sys.stderr,
                )


def _upsert_items(conn, record: dict[str, Any]) -> int:
    """Upsert each item in the section's items array. Returns the
    number of rows inserted/updated.
    """
    if record.get("error"):
        return 0
    if record.get("extraction_method") == "driver_skipped":
        # Skipped sections (preamble or structural nil returns) emit
        # no rows.
        return 0

    source_id = record.get("source_id")
    section_number = str(record.get("section_number") or "")
    items = record.get("items") or []
    if not source_id or not section_number or not items:
        return 0

    prompt_version = (
        record.get("llm_prompt_version") or "register_of_interests_extraction_v1"
    )
    extraction_method = (
        record.get("extraction_method") or "llm_register_of_interests_v1"
    )
    llm_model_id = record.get("llm_model_id") or ""
    llm_response_sha256 = record.get("llm_response_sha256") or ""
    llm_input_tokens = record.get("llm_input_tokens")
    llm_output_tokens = record.get("llm_output_tokens")
    llm_cache_hit = record.get("llm_cache_hit") or False

    member_name = record.get("member_name")
    family_name = record.get("family_name")
    given_names = record.get("given_names")
    electorate = record.get("electorate")
    state = record.get("state")
    section_title = record.get("section_title")

    upserted = 0
    with conn.cursor() as cur:
        for item_index, item in enumerate(items):
            item_metadata = {
                "url": record.get("url"),
                "llm_temperature": record.get("llm_temperature"),
                "loader_loaded_at": datetime.now(timezone.utc).isoformat(),
            }
            cur.execute(
                """
                INSERT INTO llm_register_of_interests_observation (
                    source_id, section_number, item_index,
                    member_name, family_name, given_names,
                    electorate, state, section_title,
                    item_type, counterparty_name, counterparty_type,
                    description, estimated_value_aud, event_date,
                    disposition, confidence, evidence_excerpt,
                    extraction_method, prompt_version, llm_model_id,
                    llm_response_sha256, llm_input_tokens,
                    llm_output_tokens, llm_cache_hit, metadata
                )
                VALUES (
                    %(source_id)s, %(section_number)s, %(item_index)s,
                    %(member_name)s, %(family_name)s, %(given_names)s,
                    %(electorate)s, %(state)s, %(section_title)s,
                    %(item_type)s, %(counterparty_name)s, %(counterparty_type)s,
                    %(description)s, %(estimated_value_aud)s, %(event_date)s,
                    %(disposition)s, %(confidence)s, %(evidence_excerpt)s,
                    %(extraction_method)s, %(prompt_version)s, %(llm_model_id)s,
                    %(llm_response_sha256)s, %(llm_input_tokens)s,
                    %(llm_output_tokens)s, %(llm_cache_hit)s, %(metadata)s
                )
                ON CONFLICT (source_id, section_number, item_index, prompt_version)
                DO UPDATE SET
                    member_name = EXCLUDED.member_name,
                    family_name = EXCLUDED.family_name,
                    given_names = EXCLUDED.given_names,
                    electorate = EXCLUDED.electorate,
                    state = EXCLUDED.state,
                    section_title = EXCLUDED.section_title,
                    item_type = EXCLUDED.item_type,
                    counterparty_name = EXCLUDED.counterparty_name,
                    counterparty_type = EXCLUDED.counterparty_type,
                    description = EXCLUDED.description,
                    estimated_value_aud = EXCLUDED.estimated_value_aud,
                    event_date = EXCLUDED.event_date,
                    disposition = EXCLUDED.disposition,
                    confidence = EXCLUDED.confidence,
                    evidence_excerpt = EXCLUDED.evidence_excerpt,
                    extraction_method = EXCLUDED.extraction_method,
                    llm_model_id = EXCLUDED.llm_model_id,
                    llm_response_sha256 = EXCLUDED.llm_response_sha256,
                    llm_input_tokens = EXCLUDED.llm_input_tokens,
                    llm_output_tokens = EXCLUDED.llm_output_tokens,
                    llm_cache_hit = EXCLUDED.llm_cache_hit,
                    metadata = EXCLUDED.metadata,
                    updated_at = now()
                """,
                {
                    "source_id": source_id,
                    "section_number": section_number,
                    "item_index": item_index,
                    "member_name": member_name,
                    "family_name": family_name,
                    "given_names": given_names,
                    "electorate": electorate,
                    "state": state,
                    "section_title": section_title,
                    "item_type": item.get("item_type"),
                    "counterparty_name": item.get("counterparty_name"),
                    "counterparty_type": item.get("counterparty_type"),
                    "description": item.get("description"),
                    "estimated_value_aud": item.get("estimated_value_aud"),
                    "event_date": item.get("event_date"),
                    "disposition": item.get("disposition"),
                    "confidence": item.get("confidence"),
                    "evidence_excerpt": item.get("evidence_excerpt"),
                    "extraction_method": extraction_method,
                    "prompt_version": prompt_version,
                    "llm_model_id": llm_model_id,
                    "llm_response_sha256": llm_response_sha256,
                    "llm_input_tokens": llm_input_tokens,
                    "llm_output_tokens": llm_output_tokens,
                    "llm_cache_hit": llm_cache_hit,
                    "metadata": Jsonb(item_metadata),
                },
            )
            upserted += 1
    return upserted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Load LLM-extracted Register of Interests items from JSONL "
            "into llm_register_of_interests_observation. Idempotent on "
            "(source_id, section_number, item_index, prompt_version)."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--jsonl-path", default=None,
        help=(
            "Specific JSONL file to load. If omitted, loads every JSONL "
            "under data/processed/llm_register_of_interests/."
        ),
    )
    parser.add_argument(
        "--processed-dir", default=str(PROCESSED_DIR),
        help="Override the processed-data directory.",
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("DATABASE_URL must be set", file=sys.stderr)
        return 2

    processed_dir = Path(args.processed_dir).resolve()

    if args.jsonl_path:
        jsonl_files = [Path(args.jsonl_path).resolve()]
    else:
        jsonl_files = _select_jsonl_files(processed_dir)

    if not jsonl_files:
        print("No LLM-ROI JSONL artifacts found.")
        return 0

    print(f"Loading from {len(jsonl_files)} JSONL file(s):")
    for jsonl_path in jsonl_files:
        print(f"  - {jsonl_path}")

    total_items = 0
    total_failed = 0

    with psycopg.connect(args.database_url, autocommit=False) as conn:
        for jsonl_path in jsonl_files:
            file_items = 0
            file_failed = 0
            for line_no, record in _read_records(jsonl_path):
                try:
                    n = _upsert_items(conn, record)
                except Exception as exc:  # noqa: BLE001
                    file_failed += 1
                    total_failed += 1
                    conn.rollback()
                    print(
                        f"  [{jsonl_path.name}:{line_no}] failed: {exc!r}",
                        file=sys.stderr,
                    )
                    continue
                file_items += n
                total_items += n
            conn.commit()
            print(
                f"  {jsonl_path.name}: items_loaded={file_items:,} "
                f"failed={file_failed:,}"
            )

    print()
    print(f"Total items loaded: {total_items:,}")
    print(f"Failed:             {total_failed:,}")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
