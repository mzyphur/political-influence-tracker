#!/usr/bin/env python3
"""Load LLM-produced entity classifications into the live database.

Reads the JSONL artifacts produced by `scripts/llm_classify_entities.py`
under `data/processed/llm_entity_classifications/` and:

1. Inserts an `entity_industry_classification` row per record with
   `method = 'model_assisted'`, the prompt-mapped `confidence` value
   (`high` → `fuzzy_high`, `medium` → `fuzzy_high`, `low` →
   `fuzzy_low`), the `evidence_note` from the LLM, and a metadata
   blob carrying the SHA-256 of the cached LLM response, the prompt
   version, the model id, and the LLM's raw confidence label.

2. Promotes the `entity.entity_type` from `'unknown'` to the
   LLM-classified type ONLY when the LLM's confidence is `high` AND
   the new type is NOT `'unknown'`. We're conservative: a
   medium/low-confidence reclassification stays in
   `entity_industry_classification` (so the surface is available)
   but doesn't override the catch-all `entity_type` until a human
   reviewer confirms.

Mappings applied at the loader layer (so the LLM's user-friendly
schema doesn't have to know about the DB's stricter check
constraints):

* LLM `confidence` values → DB `confidence` values:
  - `high` → `fuzzy_high`
  - `medium` → `fuzzy_high` (still confident enough)
  - `low`  → `fuzzy_low`

* LLM `entity_type` values → DB `entity_type` values:
  - `charity` → `association` (no separate charity type in DB)
  - `education_institution` → `association`
  - All other 12 LLM types map 1:1 to DB types.

Operational shape:

    cd <project root>
    DATABASE_URL=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \\
        backend/.venv/bin/python scripts/load_llm_entity_classifications.py
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


# Mapping from the LLM's user-friendly confidence labels to the
# project's existing entity_industry_classification.confidence
# CHECK-constrained values.
LLM_TO_DB_CONFIDENCE: dict[str, str] = {
    "high": "fuzzy_high",
    "medium": "fuzzy_high",
    "low": "fuzzy_low",
}

# Mapping from the LLM's user-friendly entity_type labels to the
# project's existing `entity` table values. The DB doesn't have
# `charity` or `education_institution` as distinct types — both
# fold into `association` per the project's existing taxonomy.
LLM_TO_DB_ENTITY_TYPE: dict[str, str] = {
    "company": "company",
    "trust": "trust",
    "association": "association",
    "union": "union",
    "political_party": "political_party",
    "associated_entity": "associated_entity",
    "third_party": "third_party",
    "significant_third_party": "significant_third_party",
    "lobbyist_organisation": "lobbyist_organisation",
    "individual": "individual",
    "government": "government",
    "foreign_government": "foreign_government",
    "charity": "association",  # collapse to association
    "education_institution": "association",  # collapse to association
    "unknown": "unknown",
}

# Only promote entity_type from 'unknown' to the LLM-classified
# type when the LLM signalled high confidence — medium/low stays
# in the entity_industry_classification table but doesn't move
# the entity_type field.
PROMOTE_ENTITY_TYPE_CONFIDENCE_THRESHOLD: frozenset[str] = frozenset({"high"})


def _select_jsonl_files(processed_dir: Path) -> list[Path]:
    """Return all JSONL artifacts in the processed directory,
    sorted oldest-first so newer prompts overwrite older
    classifications when the same entity appears in multiple
    artifacts.
    """
    return sorted((processed_dir / "llm_entity_classifications").glob("*.jsonl"))


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


def _upsert_classification(
    conn,
    record: dict[str, Any],
) -> tuple[bool, bool]:
    """Insert or update an entity_industry_classification row + (when
    confidence is high) promote the entity.entity_type from
    'unknown' to the LLM-classified type. Returns
    (classification_inserted_or_updated, entity_type_promoted).
    """
    if record.get("error"):
        # Skip rows that the classification script flagged as failed.
        return False, False
    entity_id = record.get("entity_id")
    if not entity_id:
        return False, False
    public_sector = record.get("public_sector") or "unknown"
    llm_entity_type = record.get("new_entity_type") or "unknown"
    db_entity_type = LLM_TO_DB_ENTITY_TYPE.get(llm_entity_type, "unknown")
    llm_confidence = record.get("confidence") or "low"
    db_confidence = LLM_TO_DB_CONFIDENCE.get(llm_confidence, "fuzzy_low")
    evidence_note = record.get("evidence_note") or ""

    # Build the metadata blob that captures the full extraction
    # provenance — sha256 of cached LLM response, prompt version,
    # model id, original LLM confidence label, original LLM
    # entity_type before mapping. Lets a reviewer reconstruct the
    # exact API call from the cache directory.
    metadata = {
        "extraction_method": record.get("extraction_method")
        or "llm_entity_industry_classification_v1",
        "llm_model_id": record.get("llm_model_id"),
        "llm_prompt_version": record.get("llm_prompt_version"),
        "llm_temperature": record.get("llm_temperature"),
        "llm_response_sha256": record.get("llm_response_sha256"),
        "llm_input_tokens": record.get("llm_input_tokens"),
        "llm_output_tokens": record.get("llm_output_tokens"),
        "llm_cache_hit": record.get("llm_cache_hit"),
        "llm_confidence_label": llm_confidence,
        "llm_entity_type_label": llm_entity_type,
        "previous_entity_type_so_far": record.get("previous_entity_type"),
        "loader_loaded_at": datetime.now(timezone.utc).isoformat(),
    }

    with conn.cursor() as cur:
        # Upsert the entity_industry_classification row.
        # Uniqueness across (entity_id, method) so re-loading the same
        # JSONL is idempotent. We use ON CONFLICT DO UPDATE to refresh
        # the row when the LLM returns a different sector for the
        # same entity_id (e.g. after a prompt revision).
        cur.execute(
            """
            INSERT INTO entity_industry_classification (
                entity_id, public_sector, method, confidence, evidence_note,
                metadata
            )
            VALUES (
                %(entity_id)s, %(public_sector)s, 'model_assisted',
                %(confidence)s, %(evidence_note)s, %(metadata)s
            )
            ON CONFLICT (entity_id, method) DO UPDATE SET
                public_sector = EXCLUDED.public_sector,
                confidence = EXCLUDED.confidence,
                evidence_note = EXCLUDED.evidence_note,
                metadata = EXCLUDED.metadata
            """,
            {
                "entity_id": entity_id,
                "public_sector": public_sector,
                "confidence": db_confidence,
                "evidence_note": evidence_note,
                "metadata": Jsonb(metadata),
            },
        )

        # Conditional entity_type promotion. Only when confidence is
        # high AND the new type is not 'unknown'.
        promoted = False
        if (
            llm_confidence in PROMOTE_ENTITY_TYPE_CONFIDENCE_THRESHOLD
            and db_entity_type != "unknown"
        ):
            cur.execute(
                """
                UPDATE entity
                SET entity_type = %s
                WHERE id = %s
                  AND entity_type = 'unknown'
                """,
                (db_entity_type, entity_id),
            )
            promoted = cur.rowcount > 0

    return True, promoted


def _ensure_entity_industry_unique_index(conn) -> None:
    """The entity_industry_classification table doesn't ship a
    UNIQUE (entity_id, method) constraint by default; without it,
    ON CONFLICT in the upsert above would fail. Create one if it
    doesn't exist. Idempotent.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                entity_industry_classification_entity_method_uniq
            ON entity_industry_classification (entity_id, method)
            """
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Load LLM-produced entity classifications from JSONL "
            "artifacts into entity_industry_classification + "
            "promote entity.entity_type when high-confidence."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--jsonl-path",
        default=None,
        help=(
            "Specific JSONL file to load. If omitted, loads every "
            "JSONL under data/processed/llm_entity_classifications/ "
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
        print("No LLM-classification JSONL artifacts found.")
        return 0

    print(f"Loading from {len(jsonl_files)} JSONL file(s):")
    for jsonl_path in jsonl_files:
        print(f"  - {jsonl_path}")

    total_loaded = 0
    total_promoted = 0
    total_failed = 0

    with psycopg.connect(args.database_url, autocommit=False) as conn:
        _ensure_entity_industry_unique_index(conn)
        conn.commit()

        for jsonl_path in jsonl_files:
            file_loaded = 0
            file_promoted = 0
            file_failed = 0
            for line_no, record in _read_records(jsonl_path):
                # Use a SAVEPOINT per row so that a single failing
                # entity_type promotion (e.g. UniqueViolation on
                # entity_normalized_type_idx) only rolls back that
                # one row, not all the previous successful upserts
                # in the current file's transaction.
                with conn.cursor() as cur:
                    cur.execute("SAVEPOINT row_attempt")
                try:
                    inserted, promoted = _upsert_classification(conn, record)
                except Exception as exc:  # noqa: BLE001
                    file_failed += 1
                    total_failed += 1
                    with conn.cursor() as cur:
                        cur.execute("ROLLBACK TO SAVEPOINT row_attempt")
                    print(
                        f"  [{jsonl_path.name}:{line_no}] failed: {exc!r}",
                        file=sys.stderr,
                    )
                    continue
                with conn.cursor() as cur:
                    cur.execute("RELEASE SAVEPOINT row_attempt")
                if inserted:
                    file_loaded += 1
                    total_loaded += 1
                if promoted:
                    file_promoted += 1
                    total_promoted += 1
            conn.commit()
            print(
                f"  {jsonl_path.name}: loaded={file_loaded:,} "
                f"entity_type_promoted={file_promoted:,} "
                f"failed={file_failed:,}"
            )

    print()
    print(f"Total loaded:                    {total_loaded:,}")
    print(f"Entity type promoted from unknown: {total_promoted:,}")
    print(f"Failed:                          {total_failed:,}")
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
