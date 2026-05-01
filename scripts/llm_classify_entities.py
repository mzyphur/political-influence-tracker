#!/usr/bin/env python3
"""LLM-assisted classification of unclassified entities.

Stage 1 of the project's hybrid LLM pipeline. Reads entities whose
deterministic classifier returned `entity_type='unknown'` from the
live database, runs each through `claude-sonnet-4-6` with the
prompt at `prompts/entity_industry_classification/v1.md`, and
writes a JSONL artifact under
`data/processed/llm_entity_classifications/`. A separate loader
(landing in this same batch) lifts the JSONL into
`entity_classification` rows.

Reproducibility chain:

* Every API call is hash-cached at
  `data/raw/llm_extractions/entity_industry_classification/<sha256>.{input,output}.json`.
* Re-running with the same prompt version + same entity inputs is
  a no-op (cache-hit on every call).
* Cost is logged per batch and at total — visible cap on spend.

Operational shape:

    cd <project root>
    backend/.venv/bin/dotenv -f backend/.env run -- \\
        backend/.venv/bin/python scripts/llm_classify_entities.py \\
            --limit 200          # pilot size; omit for full run
            --min-event-count 1  # skip entities never observed
            --min-source-document-count 1

The `--limit` flag bounds the number of entities classified per
run (cache-aware: cached entities are free re-runs). For the
pilot, run with `--limit 200` first, sanity-check the output
under `data/processed/llm_entity_classifications/`, then re-run
without the limit for the full 28k.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# psycopg is the project's standard DB client; same version backs
# au_politics_money.db.load.
import psycopg  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from au_politics_money.config import PROCESSED_DIR  # noqa: E402
from au_politics_money.llm import LLMClient, LLMResponse  # noqa: E402


DEFAULT_PROMPT_VERSION = "entity_industry_classification_v1"
MODEL_ID = "claude-sonnet-4-6"
TASK_NAME = "entity_industry_classification"

# v2 (2026-05-01): expanded 40-sector taxonomy with energy + mining
# splits. Selected via --prompt-version v2 (or "entity_industry_classification_v2").
# Runtime config:
PROMPT_PATH_V1 = PROJECT_ROOT / "prompts" / "entity_industry_classification" / "v1.md"
PROMPT_PATH_V2 = PROJECT_ROOT / "prompts" / "entity_industry_classification" / "v2.md"

# Backward-compat alias (existing imports may reference PROMPT_PATH).
PROMPT_PATH = PROMPT_PATH_V1
PROMPT_VERSION = DEFAULT_PROMPT_VERSION


VALID_PUBLIC_SECTORS_V1: frozenset[str] = frozenset(
    {
        "fossil_fuels", "mining", "renewable_energy",
        "property_development", "construction", "gambling",
        "alcohol", "tobacco", "finance", "superannuation",
        "insurance", "banking", "technology", "telecoms",
        "defence", "consulting", "law", "accounting",
        "healthcare", "pharmaceuticals", "education",
        "media", "sport_entertainment", "transport",
        "aviation", "agriculture", "unions",
        "business_associations", "charities_nonprofits",
        "foreign_government", "government_owned",
        "political_entity", "individual_uncoded", "unknown",
    }
)

# v2 taxonomy: fossil_fuels split into 5 sub-codes; mining split
# into 3 sub-codes. v1 codes (`fossil_fuels`, `mining`) are NOT
# valid in v2 — the model is instructed to pick a specific
# commodity sub-code or use the residual. Schema 043 keeps both
# v1 and v2 codes valid in the DB CHECK constraints.
VALID_PUBLIC_SECTORS_V2: frozenset[str] = frozenset(
    {
        # Energy + mining splits (NEW in v2)
        "coal", "gas", "petroleum", "uranium", "fossil_fuels_other",
        "iron_ore", "critical_minerals", "mining_other",
        # Unchanged from v1
        "renewable_energy", "property_development", "construction",
        "gambling", "alcohol", "tobacco", "finance",
        "superannuation", "insurance", "banking", "technology",
        "telecoms", "defence", "consulting", "law", "accounting",
        "healthcare", "pharmaceuticals", "education", "media",
        "sport_entertainment", "transport", "aviation",
        "agriculture", "unions", "business_associations",
        "charities_nonprofits", "foreign_government",
        "government_owned", "political_entity",
        "individual_uncoded", "unknown",
    }
)

# Backward-compat alias used by tests and tools that import
# VALID_PUBLIC_SECTORS without specifying a version.
VALID_PUBLIC_SECTORS = VALID_PUBLIC_SECTORS_V1

VALID_ENTITY_TYPES: frozenset[str] = frozenset(
    {
        "company", "trust", "association", "union",
        "political_party", "associated_entity", "third_party",
        "significant_third_party", "lobbyist_organisation",
        "individual", "government", "foreign_government",
        "charity", "education_institution", "unknown",
    }
)


def _build_response_schema(prompt_version: str) -> dict[str, Any]:
    """Build the response schema for a given prompt version.
    v1 uses the 33-sector taxonomy; v2 uses the 40-sector taxonomy.
    """
    sectors = (
        VALID_PUBLIC_SECTORS_V2
        if prompt_version.endswith("_v2")
        else VALID_PUBLIC_SECTORS_V1
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "public_sector",
            "entity_type",
            "confidence",
            "evidence_note",
        ],
        "properties": {
            "public_sector": {"type": "string", "enum": sorted(sectors)},
            "entity_type": {"type": "string", "enum": sorted(VALID_ENTITY_TYPES)},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "evidence_note": {
                "type": "string",
                "description": (
                    "1-2 sentences explaining why this sector and not "
                    "another. Mention specific signals from the name."
                ),
            },
        },
    }


# Backward-compat: the v1 schema is still exported as
# RESPONSE_SCHEMA for any callers that expect the constant.
RESPONSE_SCHEMA: dict[str, Any] = _build_response_schema(
    DEFAULT_PROMPT_VERSION
)


def _load_system_instruction(prompt_path: Path | None = None) -> str:
    """Extract the load-bearing system instruction from the prompt
    markdown file. Defaults to v1 path; v2 / future versions pass
    `prompt_path` explicitly.

    The prompt file is the source of truth; this script reads it
    at runtime so a prompt update lands without requiring a code
    change.
    """
    target = prompt_path if prompt_path is not None else PROMPT_PATH
    text = target.read_text(encoding="utf-8")
    marker = "## System instruction"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(
            f"Prompt missing '{marker}' section: {target}"
        )
    rest = text[start + len(marker):]
    if rest.startswith(" (load-bearing)"):
        rest = rest[len(" (load-bearing)"):]
    rest = rest.lstrip("\n")
    end = rest.find("\n## ")
    if end >= 0:
        rest = rest[:end]
    return rest.strip()


def _resolve_prompt_paths(prompt_version: str) -> tuple[str, Path, frozenset[str]]:
    """Map a prompt-version arg ('v1' / 'v2' / full task-name) to
    (full_prompt_version_string, prompt_md_path, valid_sectors_set).
    """
    short = prompt_version.lower().lstrip("v")
    if prompt_version.endswith("_v2") or short == "2":
        return (
            "entity_industry_classification_v2",
            PROMPT_PATH_V2,
            VALID_PUBLIC_SECTORS_V2,
        )
    return (
        "entity_industry_classification_v1",
        PROMPT_PATH_V1,
        VALID_PUBLIC_SECTORS_V1,
    )


def _build_user_message(
    canonical_name: str,
    entity_type_so_far: str,
    additional_context: str,
) -> str:
    return (
        "Classify the following Australian public-record entity "
        "into one of the 32 sector codes listed in the system "
        "instruction.\n\n"
        f"Entity name (canonical):\n{canonical_name}\n\n"
        "Optional context (from the project's existing entity record):\n"
        f"- entity_type so far: {entity_type_so_far}\n"
        f"- additional context: {additional_context}\n\n"
        "If the name is opaque or ambiguous, return `unknown` "
        "with low confidence rather than guessing.\n\n"
        "Call the `record_extraction` tool once with the result."
    )


def _select_unclassified_entities(
    conn,
    *,
    limit: int | None,
    min_event_count: int,
    min_source_document_count: int,
) -> list[dict[str, Any]]:
    """Return entities marked entity_type='unknown' in the live DB,
    enriched with event-count + source-document-count metadata.

    Filtering by ``min_event_count`` / ``min_source_document_count``
    avoids spending API calls on entities that never appeared as
    sources/recipients in any record (i.e. dead-weight rows).
    """
    sql = """
        WITH event_counts AS (
            SELECT
                entity_id,
                count(*) AS event_count,
                count(DISTINCT source_document_id) AS source_document_count
            FROM (
                SELECT source_entity_id   AS entity_id, source_document_id
                FROM influence_event
                WHERE source_entity_id IS NOT NULL
                UNION ALL
                SELECT recipient_entity_id AS entity_id, source_document_id
                FROM influence_event
                WHERE recipient_entity_id IS NOT NULL
            ) AS event_links
            WHERE entity_id IS NOT NULL
            GROUP BY entity_id
        )
        SELECT
            entity.id,
            entity.canonical_name,
            entity.normalized_name,
            entity.entity_type,
            entity.metadata,
            COALESCE(event_counts.event_count, 0) AS event_count,
            COALESCE(event_counts.source_document_count, 0) AS source_document_count
        FROM entity
        LEFT JOIN event_counts ON event_counts.entity_id = entity.id
        WHERE entity.entity_type = 'unknown'
          AND entity.canonical_name IS NOT NULL
          AND entity.canonical_name <> ''
          AND COALESCE(event_counts.event_count, 0) >= %s
          AND COALESCE(event_counts.source_document_count, 0) >= %s
        ORDER BY
            COALESCE(event_counts.event_count, 0) DESC,
            entity.id
        """
    params: list[Any] = [min_event_count, min_source_document_count]
    if limit is not None and limit > 0:
        sql += "\nLIMIT %s"
        params.append(limit)

    with conn.cursor() as cur:
        cur.execute(sql, tuple(params))
        columns = [d.name for d in cur.description]
        return [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]


def _classify_one(
    client: LLMClient,
    *,
    entity: dict[str, Any],
    system_instruction: str,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    valid_sectors: frozenset[str] = VALID_PUBLIC_SECTORS_V1,
    response_schema: dict[str, Any] | None = None,
) -> tuple[LLMResponse, dict[str, Any]]:
    canonical_name = entity["canonical_name"]
    entity_type_so_far = entity["entity_type"] or "unknown"
    additional_context_parts: list[str] = []
    metadata = entity.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("organisation_type"):
            additional_context_parts.append(
                f"organisation_type: {metadata['organisation_type']}"
            )
        if metadata.get("registered_country"):
            additional_context_parts.append(
                f"registered_country: {metadata['registered_country']}"
            )
        if metadata.get("abn"):
            additional_context_parts.append(f"abn: {metadata['abn']}")
    if not additional_context_parts:
        additional_context_parts.append("none")
    user_message = _build_user_message(
        canonical_name=canonical_name,
        entity_type_so_far=entity_type_so_far,
        additional_context=" | ".join(additional_context_parts),
    )
    schema = response_schema if response_schema is not None else _build_response_schema(prompt_version)
    response = client.call_json(
        model_id=MODEL_ID,
        prompt_version=prompt_version,
        system_instruction=system_instruction,
        user_message=user_message,
        response_schema=schema,
        temperature=0.0,
        max_tokens=512,
    )
    parsed = response.parsed
    # Server-side enum validation should already have caught these,
    # but belt-and-braces.
    if parsed["public_sector"] not in valid_sectors:
        raise ValueError(
            f"Invalid public_sector {parsed['public_sector']!r} returned for "
            f"entity {entity['id']} ({canonical_name})"
        )
    if parsed["entity_type"] not in VALID_ENTITY_TYPES:
        raise ValueError(
            f"Invalid entity_type {parsed['entity_type']!r} returned for "
            f"entity {entity['id']} ({canonical_name})"
        )
    record = {
        "entity_id": entity["id"],
        "canonical_name": canonical_name,
        "normalized_name": entity["normalized_name"],
        "previous_entity_type": entity_type_so_far,
        "event_count": entity["event_count"],
        "source_document_count": entity["source_document_count"],
        "llm_model_id": response.model_id,
        "llm_prompt_version": prompt_version,
        "llm_temperature": 0.0,
        "llm_response_sha256": response.sha256,
        "llm_input_tokens": response.input_tokens,
        "llm_output_tokens": response.output_tokens,
        "llm_cache_hit": response.cache_hit,
        "public_sector": parsed["public_sector"],
        "new_entity_type": parsed["entity_type"],
        "confidence": parsed["confidence"],
        "evidence_note": parsed["evidence_note"],
        "extraction_method": f"llm_{prompt_version}",
    }
    return response, record


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LLM-assisted entity industry classification (Stage 1). "
            "Reads entities marked entity_type='unknown' from the live "
            "database and classifies them via Claude Sonnet 4.6 with "
            "the v1 prompt. Cache-first; re-runs are no-ops."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum entities to classify per run (cache-aware).",
    )
    parser.add_argument(
        "--min-event-count", type=int, default=1,
        help="Skip entities with fewer than this many influence_event "
        "appearances (default: 1).",
    )
    parser.add_argument(
        "--min-source-document-count", type=int, default=1,
        help="Skip entities seen in fewer than this many source documents "
        "(default: 1).",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Override output directory for the JSONL/summary artefacts.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=8,
        help=(
            "Number of concurrent API calls (default: 8). The Anthropic "
            "API allows ~50 req/sec for default tier; 8 concurrent calls "
            "with ~3.5s API latency lands at ~2.3 calls/sec which stays "
            "well within rate limits and is ~10x faster than serial. "
            "Use --concurrency 1 to revert to fully sequential."
        ),
    )
    parser.add_argument(
        "--prompt-version", default="v1",
        choices=["v1", "v2"],
        help=(
            "Prompt version to use. v1 = 33-sector taxonomy "
            "(prompts/entity_industry_classification/v1.md); v2 = "
            "40-sector taxonomy with energy + mining splits "
            "(prompts/entity_industry_classification/v2.md). "
            "Default: v1."
        ),
    )
    args = parser.parse_args(argv)

    # Resolve prompt-version to (full_string, prompt_path, valid_sectors).
    prompt_version, prompt_path, valid_sectors = _resolve_prompt_paths(args.prompt_version)
    response_schema = _build_response_schema(prompt_version)

    if not args.database_url:
        print("DATABASE_URL must be set (export, or pass --database-url)", file=sys.stderr)
        return 2
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY must be set (loaded from backend/.env)", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROCESSED_DIR / "llm_entity_classifications"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_path = output_dir / f"{timestamp}.jsonl"
    summary_path = output_dir / f"{timestamp}.summary.json"

    print(f"Loading system instruction (prompt {prompt_version}) from {prompt_path}...")
    system_instruction = _load_system_instruction(prompt_path)

    client = LLMClient(task_name=TASK_NAME)

    print(f"Connecting to {args.database_url[:60]}...")
    with psycopg.connect(args.database_url, autocommit=False) as conn:
        entities = _select_unclassified_entities(
            conn,
            limit=args.limit,
            min_event_count=args.min_event_count,
            min_source_document_count=args.min_source_document_count,
        )
    print(
        f"Selected {len(entities):,} unclassified entities "
        f"(min_event_count={args.min_event_count}, "
        f"min_source_document_count={args.min_source_document_count})."
    )
    if not entities:
        print("No work to do.")
        return 0

    started_at = time.monotonic()
    cache_hits = 0
    fresh_calls = 0
    sector_distribution: dict[str, int] = {}
    confidence_distribution: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    failed_count = 0

    # Locks so the worker threads can update shared counters + the
    # output JSONL safely. The Anthropic SDK is thread-safe (uses
    # an httpx client internally) so multiple threads can call
    # client.call_json concurrently. The cache layer is also
    # thread-safe (filesystem writes via .tmp + rename are atomic).
    output_lock = threading.Lock()
    counters_lock = threading.Lock()

    def _process_one(index_entity: tuple[int, dict[str, Any]]) -> None:
        nonlocal cache_hits, fresh_calls, total_input_tokens
        nonlocal total_output_tokens, failed_count
        index, entity = index_entity
        try:
            response, record = _classify_one(
                client,
                entity=entity,
                system_instruction=system_instruction,
                prompt_version=prompt_version,
                valid_sectors=valid_sectors,
                response_schema=response_schema,
            )
        except Exception as exc:  # noqa: BLE001
            error_record = {
                "entity_id": entity["id"],
                "canonical_name": entity["canonical_name"],
                "extraction_method": f"llm_{prompt_version}",
                "error": repr(exc),
            }
            with output_lock:
                out.write(json.dumps(error_record, ensure_ascii=False))
                out.write("\n")
            with counters_lock:
                failed_count += 1
            return
        with output_lock:
            out.write(json.dumps(record, ensure_ascii=False))
            out.write("\n")
        with counters_lock:
            sector_distribution[record["public_sector"]] = (
                sector_distribution.get(record["public_sector"], 0) + 1
            )
            confidence_distribution[record["confidence"]] = (
                confidence_distribution.get(record["confidence"], 0) + 1
            )
            if response.cache_hit:
                cache_hits += 1
            else:
                fresh_calls += 1
                total_input_tokens += response.input_tokens or 0
                total_output_tokens += response.output_tokens or 0

    with jsonl_path.open("w", encoding="utf-8") as out:
        if args.concurrency <= 1:
            for index, entity in enumerate(entities, start=1):
                _process_one((index, entity))
                if index % 25 == 0 or index == len(entities):
                    elapsed = time.monotonic() - started_at
                    rate = index / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{index:>5}/{len(entities)}] "
                        f"hits={cache_hits} fresh={fresh_calls} "
                        f"failed={failed_count} "
                        f"rate={rate:.2f}/s "
                        f"in={total_input_tokens:,} out={total_output_tokens:,}"
                    )
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(_process_one, (i + 1, e)): i
                    for i, e in enumerate(entities)
                }
                completed = 0
                for fut in as_completed(futures):
                    completed += 1
                    fut.result()
                    if completed % 25 == 0 or completed == len(entities):
                        elapsed = time.monotonic() - started_at
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(
                            f"  [{completed:>5}/{len(entities)}] "
                            f"hits={cache_hits} fresh={fresh_calls} "
                            f"failed={failed_count} "
                            f"rate={rate:.2f}/s "
                            f"in={total_input_tokens:,} out={total_output_tokens:,}"
                        )

    elapsed = time.monotonic() - started_at
    estimated_cost_usd = (
        (total_input_tokens / 1_000_000) * 3.0
        + (total_output_tokens / 1_000_000) * 15.0
    )
    summary = {
        "task_name": TASK_NAME,
        "prompt_version": prompt_version,
        "model_id": MODEL_ID,
        "generated_at": timestamp,
        "concurrency": args.concurrency,
        "entity_count": len(entities),
        "cache_hits": cache_hits,
        "fresh_calls": fresh_calls,
        "failed_count": failed_count,
        "elapsed_seconds": round(elapsed, 2),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd_sonnet_4_6": round(estimated_cost_usd, 4),
        "sector_distribution": sector_distribution,
        "confidence_distribution": confidence_distribution,
        "jsonl_path": str(jsonl_path),
        "claim_discipline_caveat": (
            "These classifications are produced by Claude Sonnet 4.6 "
            "under the v1 prompt at "
            "prompts/entity_industry_classification/v1.md. They are "
            "labelled with extraction_method = "
            "'llm_entity_industry_classification_v1' wherever they "
            "surface; the project's claim-discipline rule treats them "
            "as a separate evidence tier from rule-based "
            "classifications. Each row's full input + output envelope "
            "is cached at "
            "data/raw/llm_extractions/entity_industry_classification/<sha256>.json "
            "so a researcher can reproduce any classification without "
            "an API key."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print(f"Wrote {len(entities):,} classifications to {jsonl_path}")
    print(f"Cache hits: {cache_hits:,}; fresh calls: {fresh_calls:,}; "
          f"failed: {failed_count:,}")
    print(f"Tokens: in={total_input_tokens:,} out={total_output_tokens:,}")
    print(f"Estimated fresh-call cost: ${estimated_cost_usd:.2f} USD")
    print(f"Summary: {summary_path}")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
