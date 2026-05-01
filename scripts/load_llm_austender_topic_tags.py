#!/usr/bin/env python3
"""Load LLM-produced AusTender topic tags into the live database.

Reads the JSONL artifacts produced by `scripts/llm_tag_austender_contracts.py`
under `data/processed/llm_austender_topic_tags/` and upserts a row per
(contract_id, prompt_version) pair into `austender_contract_topic_tag`
(introduced by migration 039).

The LLM emits values that already match the DB CHECK constraints
(sector / policy_topics / procurement_class / confidence are all
schema-enum values from the v1 prompt), so unlike Stage 1 there are
no LLM→DB label mappings here. The loader is a straightforward
content-addressable upsert.

Operational shape:

    cd <project root>
    DATABASE_URL=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \\
        backend/.venv/bin/python scripts/load_llm_austender_topic_tags.py
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
    """Return all JSONL artifacts in the processed directory,
    sorted oldest-first so newer prompts overwrite older tags
    when the same contract appears in multiple artifacts.
    """
    return sorted(
        (processed_dir / "llm_austender_topic_tags").glob("*.jsonl")
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


def _upsert_tag(conn, record: dict[str, Any]) -> bool:
    """Insert or update one austender_contract_topic_tag row.
    Returns True if inserted/updated, False if skipped.
    """
    if record.get("error"):
        return False
    contract_id = record.get("contract_id")
    if not contract_id:
        return False

    sector = record.get("sector")
    policy_topics = record.get("policy_topics") or []
    procurement_class = record.get("procurement_class")
    summary = record.get("summary")
    confidence = record.get("confidence")
    prompt_version = (
        record.get("llm_prompt_version") or "austender_contract_topic_tag_v1"
    )
    extraction_method = (
        record.get("extraction_method") or "llm_austender_topic_tag_v1"
    )
    llm_model_id = record.get("llm_model_id")
    llm_response_sha256 = record.get("llm_response_sha256")
    llm_input_tokens = record.get("llm_input_tokens")
    llm_output_tokens = record.get("llm_output_tokens")
    llm_cache_hit = record.get("llm_cache_hit") or False

    # Build the metadata blob — contract context echoed back so a
    # reviewer can query the DB without re-joining to the parsed
    # AusTender JSONL.
    metadata = {
        "agency_name": record.get("agency_name"),
        "supplier_name": record.get("supplier_name"),
        "contract_value_aud": record.get("contract_value_aud"),
        "parent_contract_id": record.get("parent_contract_id"),
        "contract_notice_type": record.get("contract_notice_type"),
        "unspsc_code": record.get("unspsc_code"),
        "unspsc_title": record.get("unspsc_title"),
        "procurement_method": record.get("procurement_method"),
        "consultancy_flag": record.get("consultancy_flag"),
        "llm_temperature": record.get("llm_temperature"),
        "loader_loaded_at": datetime.now(timezone.utc).isoformat(),
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO austender_contract_topic_tag (
                contract_id, sector, policy_topics, procurement_class,
                summary, confidence, extraction_method, prompt_version,
                llm_model_id, llm_response_sha256, llm_input_tokens,
                llm_output_tokens, llm_cache_hit, metadata
            )
            VALUES (
                %(contract_id)s, %(sector)s, %(policy_topics)s,
                %(procurement_class)s, %(summary)s, %(confidence)s,
                %(extraction_method)s, %(prompt_version)s,
                %(llm_model_id)s, %(llm_response_sha256)s,
                %(llm_input_tokens)s, %(llm_output_tokens)s,
                %(llm_cache_hit)s, %(metadata)s
            )
            ON CONFLICT (contract_id, prompt_version) DO UPDATE SET
                sector = EXCLUDED.sector,
                policy_topics = EXCLUDED.policy_topics,
                procurement_class = EXCLUDED.procurement_class,
                summary = EXCLUDED.summary,
                confidence = EXCLUDED.confidence,
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
                "contract_id": contract_id,
                "sector": sector,
                "policy_topics": list(policy_topics),
                "procurement_class": procurement_class,
                "summary": summary,
                "confidence": confidence,
                "extraction_method": extraction_method,
                "prompt_version": prompt_version,
                "llm_model_id": llm_model_id,
                "llm_response_sha256": llm_response_sha256,
                "llm_input_tokens": llm_input_tokens,
                "llm_output_tokens": llm_output_tokens,
                "llm_cache_hit": llm_cache_hit,
                "metadata": Jsonb(metadata),
            },
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Load LLM-produced AusTender topic tags from JSONL artifacts "
            "into austender_contract_topic_tag. Idempotent on "
            "(contract_id, prompt_version)."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--jsonl-path",
        default=None,
        help=(
            "Specific JSONL file to load. If omitted, loads every "
            "JSONL under data/processed/llm_austender_topic_tags/ "
            "in oldest-first order."
        ),
    )
    parser.add_argument(
        "--processed-dir",
        default=str(PROCESSED_DIR),
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
        print("No LLM-tag JSONL artifacts found.")
        return 0

    print(f"Loading from {len(jsonl_files)} JSONL file(s):")
    for jsonl_path in jsonl_files:
        print(f"  - {jsonl_path}")

    total_loaded = 0
    total_failed = 0

    with psycopg.connect(args.database_url, autocommit=False) as conn:
        for jsonl_path in jsonl_files:
            file_loaded = 0
            file_failed = 0
            for line_no, record in _read_records(jsonl_path):
                try:
                    inserted = _upsert_tag(conn, record)
                except Exception as exc:  # noqa: BLE001
                    file_failed += 1
                    total_failed += 1
                    conn.rollback()
                    print(
                        f"  [{jsonl_path.name}:{line_no}] failed: {exc!r}",
                        file=sys.stderr,
                    )
                    continue
                if inserted:
                    file_loaded += 1
                    total_loaded += 1
            conn.commit()
            print(
                f"  {jsonl_path.name}: loaded={file_loaded:,} "
                f"failed={file_failed:,}"
            )

    print()
    print(f"Total loaded: {total_loaded:,}")
    print(f"Failed:       {total_failed:,}")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
