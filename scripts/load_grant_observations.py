#!/usr/bin/env python3
"""Load GrantConnect grant observation JSONL into Postgres.

Reads JSONL files produced by `backend.au_politics_money.ingest.grants`
under `data/processed/grant_observations/<ts>.jsonl` and upserts each
row into the `grant_observation` table introduced by migration 052.

Cross-correlation prep: at load time, we don't yet match
recipients to existing `entity` rows — that's the next batch's
work. The grant rows live in their own table; the LLM topic
tagger (Stage 3-grants parallel, future batch) populates
`llm_grant_topic_tag` which the per-sector views aggregate via
`v_sector_grant_aggregates` + `v_sector_money_outflow`.

Operational shape:

    cd <project root>
    DATABASE_URL=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \\
        backend/.venv/bin/python scripts/load_grant_observations.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg  # type: ignore
from psycopg.types.json import Jsonb  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from au_politics_money.config import PROCESSED_DIR  # noqa: E402


def _select_jsonl_files(processed_dir: Path) -> list[Path]:
    return sorted((processed_dir / "grant_observations").glob("*.jsonl"))


def _read_records(jsonl_path: Path):
    with jsonl_path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                yield line_no, json.loads(line)
            except json.JSONDecodeError as exc:
                print(
                    f"  [{jsonl_path.name}:{line_no}] skipping malformed: {exc}",
                    file=sys.stderr,
                )


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _upsert_grant(conn, record: dict[str, Any]) -> bool:
    grant_id = record.get("grant_id")
    if not grant_id:
        return False

    agency = record.get("agency") or {}
    recipient = record.get("recipient") or {}
    location = record.get("location") or {}

    metadata = {
        "loader_loaded_at": datetime.now(timezone.utc).isoformat(),
        "csv_line_no": record.get("csv_line_no"),
        # Echo recipient/agency name into metadata too so the
        # cross-correlation views can read it without a JSON
        # path query each time.
        "recipient_name": recipient.get("name"),
        "agency_name": agency.get("name"),
        "grant_value_aud": record.get("grant_value_aud"),
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO grant_observation (
                grant_id, parent_grant_id, notice_type,
                agency_name, agency_ref_id, agency_branch,
                agency_division, agency_office_postcode,
                recipient_name, recipient_abn, recipient_address,
                recipient_suburb, recipient_postcode, recipient_state,
                recipient_country,
                grant_value_aud, funding_amount_aud,
                publish_date, decision_date, start_date, end_date,
                grant_program, grant_activity, description, purpose,
                cfda_code,
                location_postcode, location_suburb, location_state,
                source_dataset, schema_version, metadata
            )
            VALUES (
                %(grant_id)s, %(parent_grant_id)s, %(notice_type)s,
                %(agency_name)s, %(agency_ref_id)s, %(agency_branch)s,
                %(agency_division)s, %(agency_office_postcode)s,
                %(recipient_name)s, %(recipient_abn)s, %(recipient_address)s,
                %(recipient_suburb)s, %(recipient_postcode)s, %(recipient_state)s,
                %(recipient_country)s,
                %(grant_value_aud)s, %(funding_amount_aud)s,
                %(publish_date)s, %(decision_date)s, %(start_date)s, %(end_date)s,
                %(grant_program)s, %(grant_activity)s, %(description)s, %(purpose)s,
                %(cfda_code)s,
                %(location_postcode)s, %(location_suburb)s, %(location_state)s,
                %(source_dataset)s, %(schema_version)s, %(metadata)s
            )
            ON CONFLICT (grant_id) DO UPDATE SET
                parent_grant_id = EXCLUDED.parent_grant_id,
                notice_type = EXCLUDED.notice_type,
                agency_name = EXCLUDED.agency_name,
                agency_ref_id = EXCLUDED.agency_ref_id,
                agency_branch = EXCLUDED.agency_branch,
                agency_division = EXCLUDED.agency_division,
                agency_office_postcode = EXCLUDED.agency_office_postcode,
                recipient_name = EXCLUDED.recipient_name,
                recipient_abn = EXCLUDED.recipient_abn,
                recipient_address = EXCLUDED.recipient_address,
                recipient_suburb = EXCLUDED.recipient_suburb,
                recipient_postcode = EXCLUDED.recipient_postcode,
                recipient_state = EXCLUDED.recipient_state,
                recipient_country = EXCLUDED.recipient_country,
                grant_value_aud = EXCLUDED.grant_value_aud,
                funding_amount_aud = EXCLUDED.funding_amount_aud,
                publish_date = EXCLUDED.publish_date,
                decision_date = EXCLUDED.decision_date,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                grant_program = EXCLUDED.grant_program,
                grant_activity = EXCLUDED.grant_activity,
                description = EXCLUDED.description,
                purpose = EXCLUDED.purpose,
                cfda_code = EXCLUDED.cfda_code,
                location_postcode = EXCLUDED.location_postcode,
                location_suburb = EXCLUDED.location_suburb,
                location_state = EXCLUDED.location_state,
                source_dataset = EXCLUDED.source_dataset,
                schema_version = EXCLUDED.schema_version,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            {
                "grant_id": grant_id,
                "parent_grant_id": record.get("parent_grant_id"),
                "notice_type": record.get("notice_type"),
                "agency_name": agency.get("name"),
                "agency_ref_id": agency.get("ref_id"),
                "agency_branch": agency.get("branch"),
                "agency_division": agency.get("division"),
                "agency_office_postcode": agency.get("office_postcode"),
                "recipient_name": recipient.get("name"),
                "recipient_abn": recipient.get("abn"),
                "recipient_address": recipient.get("address"),
                "recipient_suburb": recipient.get("suburb"),
                "recipient_postcode": recipient.get("postcode"),
                "recipient_state": recipient.get("state"),
                "recipient_country": recipient.get("country"),
                "grant_value_aud": _to_decimal(record.get("grant_value_aud")),
                "funding_amount_aud": _to_decimal(record.get("funding_amount_aud")),
                "publish_date": record.get("publish_date"),
                "decision_date": record.get("decision_date"),
                "start_date": record.get("start_date"),
                "end_date": record.get("end_date"),
                "grant_program": record.get("grant_program"),
                "grant_activity": record.get("grant_activity"),
                "description": record.get("description"),
                "purpose": record.get("purpose"),
                "cfda_code": record.get("cfda_code"),
                "location_postcode": location.get("postcode"),
                "location_suburb": location.get("suburb"),
                "location_state": location.get("state"),
                "source_dataset": record.get("source_dataset"),
                "schema_version": record.get("schema_version"),
                "metadata": Jsonb(metadata),
            },
        )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Load GrantConnect grant observations from JSONL "
            "artifacts into grant_observation. Idempotent on "
            "grant_id (ON CONFLICT UPDATE)."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--jsonl-path", default=None,
        help=(
            "Specific JSONL file to load. If omitted, loads every "
            "JSONL under data/processed/grant_observations/."
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
        print("No grant-observation JSONL artefacts found.")
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
                    inserted = _upsert_grant(conn, record)
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
