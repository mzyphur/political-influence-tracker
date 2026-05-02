#!/usr/bin/env python3
"""LLM-assisted topic tagging of AusTender contract notices.

Stage 3 of the project's hybrid LLM pipeline. Reads parsed AusTender
contract notice records from
`data/processed/austender_contract_notices_historical/<ts>.jsonl`
(produced by `backend/au_politics_money/ingest/austender.py`),
runs each through `claude-haiku-4-5-20251001` with the prompt at
`prompts/austender_contract_topic_tag/v1.md`, and writes a JSONL
artifact under `data/processed/llm_austender_topic_tags/`.

A separate loader (`scripts/load_llm_austender_topic_tags.py`)
lifts the JSONL into the `austender_contract_topic_tag` Postgres
table introduced by migration 039.

Reproducibility chain (matches Stages 1+2):

* Every API call is hash-cached at
  `data/raw/llm_extractions/austender_contract_topic_tag/<sha256>.{input,output}.json`.
* Re-running with the same prompt version + same contract input is
  a no-op (cache-hit on every call).
* Cost is logged per batch and at total — visible cap on spend.
* Every cached row carries `extraction_method =
  'llm_austender_topic_tag_v1'`.

Operational shape:

    cd <project root>
    backend/.venv/bin/dotenv -f backend/.env run -- \\
        backend/.venv/bin/python scripts/llm_tag_austender_contracts.py \\
            --jsonl data/processed/austender_contract_notices_historical/<ts>.jsonl \\
            --limit 200          # pilot size; omit for full run
            --concurrency 100    # massive parallel; default per project lead

Pilot recommendation: run with `--limit 200` first, sanity-check
the output, then re-run without the limit for the full 73k+
historical corpus.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from au_politics_money.config import PROCESSED_DIR  # noqa: E402
from au_politics_money.llm import LLMClient, LLMResponse  # noqa: E402


DEFAULT_PROMPT_VERSION = "austender_contract_topic_tag_v2"
DEFAULT_MODEL_ID = "claude-sonnet-4-6"
TASK_NAME = "austender_contract_topic_tag"

# Backward-compat constants. Driver was originally Sonnet-only;
# Batch CC-15 added --model + --prompt-version flags so a single
# script supports v1 (Haiku 4.5, 33-sector), v2 (Sonnet 4.6,
# 33-sector), and v3 (40-sector w/ energy/mining splits — runs
# against either Haiku 4.5 or Sonnet 4.6). The Haiku-validation-
# pipeline (Stage 3 cost-down) uses --model claude-haiku-4-5-20251001
# --prompt-version v3.
MODEL_ID = DEFAULT_MODEL_ID
PROMPT_VERSION = DEFAULT_PROMPT_VERSION
PROMPT_PATH_V1 = PROJECT_ROOT / "prompts" / "austender_contract_topic_tag" / "v1.md"
PROMPT_PATH_V2 = PROJECT_ROOT / "prompts" / "austender_contract_topic_tag" / "v2.md"
PROMPT_PATH_V3 = PROJECT_ROOT / "prompts" / "austender_contract_topic_tag" / "v3.md"
PROMPT_PATH = PROMPT_PATH_V2  # default for legacy callers


# v1 / v2 use the 33-sector taxonomy.
VALID_SECTORS_V1_V2: frozenset[str] = frozenset(
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

# v3 adds the 8 energy + mining commodity sub-codes (40 total).
VALID_SECTORS_V3: frozenset[str] = frozenset(
    {
        "coal", "gas", "petroleum", "uranium", "fossil_fuels_other",
        "iron_ore", "critical_minerals", "mining_other",
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

# Backward-compat alias used by tests and tools that imported
# VALID_SECTORS without specifying a version.
VALID_SECTORS = VALID_SECTORS_V1_V2

VALID_POLICY_TOPICS: frozenset[str] = frozenset(
    {
        "defence_security", "health_aged_care",
        "infrastructure_transport", "it_digital",
        "education_skills", "social_services",
        "housing_homelessness", "energy_resources",
        "environment_climate", "agriculture_food",
        "immigration_border", "justice_legal",
        "tax_finance_treasury", "industry_innovation",
        "foreign_affairs_aid", "indigenous_affairs",
        "arts_culture", "employment_workplace",
        "science_research", "media_communications",
        "disability_carers", "women_gender",
        "regulation_compliance", "general_administration",
    }
)

VALID_PROCUREMENT_CLASSES: frozenset[str] = frozenset(
    {"services", "goods", "construction", "mixed"}
)


def _build_response_schema(prompt_version: str) -> dict[str, Any]:
    """Build the response schema for the requested prompt version.
    v1/v2 use 33-sector taxonomy; v3 uses 40-sector taxonomy."""
    sectors = (
        VALID_SECTORS_V3 if prompt_version.endswith("_v3") else VALID_SECTORS_V1_V2
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "sector",
            "policy_topics",
            "procurement_class",
            "summary",
            "confidence",
        ],
        "properties": {
            "sector": {"type": "string", "enum": sorted(sectors)},
            "policy_topics": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {"type": "string", "enum": sorted(VALID_POLICY_TOPICS)},
            },
            "procurement_class": {
                "type": "string",
                "enum": sorted(VALID_PROCUREMENT_CLASSES),
            },
            "summary": {"type": "string", "minLength": 1, "maxLength": 250},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        },
    }


# Backward-compat: legacy callers can still import RESPONSE_SCHEMA.
RESPONSE_SCHEMA: dict[str, Any] = _build_response_schema(DEFAULT_PROMPT_VERSION)


def _resolve_prompt_paths(prompt_version: str) -> tuple[str, Path, frozenset[str]]:
    """Map a prompt-version arg ('v1' / 'v2' / 'v3' or full task-name)
    to (full_prompt_version_string, prompt_md_path, valid_sectors)."""
    short = prompt_version.lower().lstrip("v")
    if prompt_version.endswith("_v3") or short == "3":
        return (
            "austender_contract_topic_tag_v3",
            PROMPT_PATH_V3,
            VALID_SECTORS_V3,
        )
    if prompt_version.endswith("_v2") or short == "2":
        return (
            "austender_contract_topic_tag_v2",
            PROMPT_PATH_V2,
            VALID_SECTORS_V1_V2,
        )
    return (
        "austender_contract_topic_tag_v1",
        PROMPT_PATH_V1,
        VALID_SECTORS_V1_V2,
    )


# Strip HTML tags + decode HTML entities. The AusTender CSV's
# `description` and `amendment_reason` columns occasionally carry
# `<p>...</p>` and the like. Preserves the inner text and whitespace.
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str:
    if text is None:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _load_system_instruction(prompt_path: Path | None = None) -> str:
    """Extract the load-bearing system instruction from the prompt
    markdown file. Defaults to the legacy PROMPT_PATH (v2) for
    backward compat; v3 / future versions pass `prompt_path` directly.
    """
    target = prompt_path if prompt_path is not None else PROMPT_PATH
    text = target.read_text(encoding="utf-8")
    marker = "## System instruction"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"Prompt missing '{marker}' section: {target}")
    rest = text[start + len(marker):]
    if rest.startswith(" (load-bearing)"):
        rest = rest[len(" (load-bearing)"):]
    rest = rest.lstrip("\n")
    end = rest.find("\n## ")
    if end >= 0:
        rest = rest[:end]
    return rest.strip()


def _build_user_message(record: dict[str, Any]) -> str:
    """Build the per-contract user message from a parsed AusTender
    JSONL row. Mirrors the user-message template in prompt v1.
    """
    agency_name = (record.get("agency") or {}).get("name") or "unknown"
    supplier_name = (record.get("supplier") or {}).get("name") or "unknown"
    description = _strip_html(record.get("description"))
    amendment_reason = _strip_html(record.get("amendment_reason"))
    if amendment_reason:
        # Surface amendment context to the model — useful when the
        # parent contract's description is sparse but the amendment
        # has new context.
        description = (
            f"{description} [Amendment reason: {amendment_reason}]"
            if description
            else f"[Amendment reason: {amendment_reason}]"
        )
    contract_value_aud = (
        record.get("contract_value_aud")
        or record.get("amendments_value_aud")
        or "unknown"
    )
    procurement_method = record.get("procurement_method") or "unknown"
    unspsc_code = record.get("unspsc_code") or "unknown"
    unspsc_title = record.get("unspsc_title") or "unknown"
    consultancy_flag = record.get("consultancy_flag")
    consultancy_str = (
        "true"
        if consultancy_flag is True
        else ("false" if consultancy_flag is False else "unknown")
    )
    return (
        "Tag this Australian Commonwealth contract notice.\n\n"
        f"Agency: {agency_name}\n"
        f"Supplier: {supplier_name}\n"
        f"Contract value (AUD): {contract_value_aud}\n"
        f"Procurement method: {procurement_method}\n"
        f"UNSPSC: {unspsc_code} — {unspsc_title}\n"
        f"Description: {description}\n"
        f"Consultancy flag (per source): {consultancy_str}\n\n"
        "Call the `record_extraction` tool once with:\n"
        "* sector (one of 33)\n"
        "* policy_topics (one or more of 24)\n"
        "* procurement_class (one of 4)\n"
        "* summary (≤25 words plain English)\n"
        "* confidence (high/medium/low)"
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"  warn: skipping malformed JSON line: {exc}", file=sys.stderr)
    return rows


def _is_skippable(record: dict[str, Any]) -> tuple[bool, str]:
    """Skip records that don't have enough signal to tag. Empty or
    placeholder descriptions waste API calls."""
    description = _strip_html(record.get("description"))
    amendment_reason = _strip_html(record.get("amendment_reason"))
    if len(description) < 3 and len(amendment_reason) < 3:
        return True, "description_too_short"
    return False, ""


def _tag_one(
    client: LLMClient,
    *,
    record: dict[str, Any],
    system_instruction: str,
    model_id: str = DEFAULT_MODEL_ID,
    prompt_version: str = DEFAULT_PROMPT_VERSION,
    valid_sectors: frozenset[str] = VALID_SECTORS_V1_V2,
    response_schema: dict[str, Any] | None = None,
) -> tuple[LLMResponse, dict[str, Any]]:
    user_message = _build_user_message(record)
    schema = (
        response_schema if response_schema is not None
        else _build_response_schema(prompt_version)
    )
    response = client.call_json(
        model_id=model_id,
        prompt_version=prompt_version,
        system_instruction=system_instruction,
        user_message=user_message,
        response_schema=schema,
        temperature=0.0,
        max_tokens=400,
    )
    parsed = response.parsed
    # Belt-and-braces validation. The Anthropic tool_use schema
    # check is server-side; we re-check enums here so the project's
    # reproducibility chain doesn't depend on the API alone.
    if parsed["sector"] not in valid_sectors:
        raise ValueError(
            f"Invalid sector {parsed['sector']!r} for "
            f"contract {record.get('contract_id')}"
        )
    if parsed["procurement_class"] not in VALID_PROCUREMENT_CLASSES:
        raise ValueError(
            f"Invalid procurement_class {parsed['procurement_class']!r} for "
            f"contract {record.get('contract_id')}"
        )
    invalid_topics = [
        t for t in parsed["policy_topics"] if t not in VALID_POLICY_TOPICS
    ]
    if invalid_topics:
        raise ValueError(
            f"Invalid policy_topics {invalid_topics!r} for "
            f"contract {record.get('contract_id')}"
        )

    contract_value_aud = (
        record.get("contract_value_aud")
        or record.get("amendments_value_aud")
    )
    out_record = {
        "contract_id": record.get("contract_id"),
        "parent_contract_id": record.get("parent_contract_id"),
        "contract_notice_type": record.get("contract_notice_type"),
        "agency_name": (record.get("agency") or {}).get("name"),
        "supplier_name": (record.get("supplier") or {}).get("name"),
        "contract_value_aud": contract_value_aud,
        "unspsc_code": record.get("unspsc_code"),
        "unspsc_title": record.get("unspsc_title"),
        "procurement_method": record.get("procurement_method"),
        "consultancy_flag": record.get("consultancy_flag"),
        "llm_model_id": response.model_id,
        "llm_prompt_version": prompt_version,
        "llm_temperature": 0.0,
        "llm_response_sha256": response.sha256,
        "llm_input_tokens": response.input_tokens,
        "llm_output_tokens": response.output_tokens,
        "llm_cache_hit": response.cache_hit,
        "sector": parsed["sector"],
        "policy_topics": parsed["policy_topics"],
        "procurement_class": parsed["procurement_class"],
        "summary": parsed["summary"],
        "confidence": parsed["confidence"],
        "extraction_method": f"llm_{prompt_version}",
    }
    return response, out_record


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_jsonl(processed_dir: Path) -> Path | None:
    """Return the most recent AusTender JSONL artifact, or None."""
    candidates = sorted(
        (processed_dir / "austender_contract_notices_historical").glob(
            "*.jsonl"
        ),
        reverse=True,
    )
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LLM-assisted topic tagging of AusTender contract notices "
            "(Stage 3). Reads parsed JSONL records and tags each with "
            "industry sector + policy topics + procurement class via "
            "Claude Haiku 4.5 + the v1 prompt. Cache-first; re-runs are "
            "no-ops."
        )
    )
    parser.add_argument(
        "--jsonl",
        default=None,
        help=(
            "AusTender parsed JSONL to tag. If omitted, picks the most "
            "recent file under "
            "data/processed/austender_contract_notices_historical/."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum contracts to tag per run (cache-aware).",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Override output directory for the JSONL/summary artefacts.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=10,
        help=(
            "Number of concurrent API calls (default: 10). Empirically: "
            "v1 pilot at concurrency=50 hit Haiku's 450k input-tokens-per-"
            "minute rate limit (17/500 contracts errored); concurrency=8 "
            "stayed under the cap. Sonnet 4.6 has higher TPM ceilings "
            "(800k–2M depending on tier) but the prudent default is 10. "
            "For full-scale runs use Anthropic Batches API instead."
        ),
    )
    parser.add_argument(
        "--skip-cache-hits",
        action="store_true",
        default=False,
        help=(
            "When set, contracts whose envelope hash is already cached "
            "are not re-emitted to the JSONL (saves disk on full re-runs)."
        ),
    )
    parser.add_argument(
        "--prompt-version", default="v2",
        choices=["v1", "v2", "v3"],
        help=(
            "Prompt version to use. v1=33-sector Haiku-era; v2=33-sector "
            "Sonnet upgrade; v3=40-sector with energy/mining commodity splits."
            " Default: v2."
        ),
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL_ID,
        help=(
            "Anthropic model id. Default: claude-sonnet-4-6. For "
            "Haiku-validation-pipeline runs use claude-haiku-4-5-20251001."
        ),
    )
    parser.add_argument(
        "--start-offset", type=int, default=0,
        help=(
            "Skip the first N contracts in the input JSONL. Combined with "
            "--limit, lets the driver process slices of the corpus (e.g., "
            "--start-offset 200 --limit 1000 = contracts 201..1200)."
        ),
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY must be set (loaded from backend/.env)",
            file=sys.stderr,
        )
        return 2

    # Resolve prompt-version + model.
    prompt_version, prompt_path, valid_sectors = _resolve_prompt_paths(
        args.prompt_version
    )
    response_schema = _build_response_schema(prompt_version)
    model_id = args.model

    if args.jsonl:
        jsonl_input = Path(args.jsonl).resolve()
    else:
        jsonl_input = _latest_jsonl(PROCESSED_DIR)
    if not jsonl_input or not jsonl_input.exists():
        print(
            f"AusTender input JSONL not found: {jsonl_input}", file=sys.stderr
        )
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROCESSED_DIR / "llm_austender_topic_tags"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_output = output_dir / f"{timestamp}.jsonl"
    summary_path = output_dir / f"{timestamp}.summary.json"

    print(
        f"Loading system instruction (prompt {prompt_version}, "
        f"model {model_id}) from {prompt_path}..."
    )
    system_instruction = _load_system_instruction(prompt_path)

    client = LLMClient(task_name=TASK_NAME)

    print(f"Reading parsed contracts from {jsonl_input}...")
    contracts = _read_jsonl(jsonl_input)
    print(f"  {len(contracts):,} contract notices loaded.")

    if args.start_offset and args.start_offset > 0:
        contracts = contracts[args.start_offset:]
        print(f"  --start-offset {args.start_offset} applied: {len(contracts):,} remain.")
    if args.limit and args.limit > 0:
        contracts = contracts[: args.limit]
        print(f"  --limit applied: {len(contracts):,} contracts will be tagged.")

    started_at = time.monotonic()
    cache_hits = 0
    fresh_calls = 0
    sector_distribution: dict[str, int] = {}
    confidence_distribution: dict[str, int] = {}
    procurement_distribution: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    failed_count = 0
    skipped_count = 0

    output_lock = threading.Lock()
    counters_lock = threading.Lock()

    def _process_one(index_record: tuple[int, dict[str, Any]]) -> None:
        nonlocal cache_hits, fresh_calls, total_input_tokens
        nonlocal total_output_tokens, failed_count, skipped_count
        index, record = index_record
        skip, skip_reason = _is_skippable(record)
        if skip:
            with counters_lock:
                skipped_count += 1
            return
        try:
            response, out_record = _tag_one(
                client,
                record=record,
                system_instruction=system_instruction,
                model_id=model_id,
                prompt_version=prompt_version,
                valid_sectors=valid_sectors,
                response_schema=response_schema,
            )
        except Exception as exc:  # noqa: BLE001
            error_record = {
                "contract_id": record.get("contract_id"),
                "extraction_method": f"llm_{prompt_version}",
                "error": repr(exc),
            }
            with output_lock:
                out.write(json.dumps(error_record, ensure_ascii=False))
                out.write("\n")
            with counters_lock:
                failed_count += 1
            return
        if args.skip_cache_hits and response.cache_hit:
            with counters_lock:
                cache_hits += 1
            return
        with output_lock:
            out.write(json.dumps(out_record, ensure_ascii=False))
            out.write("\n")
        with counters_lock:
            sector_distribution[out_record["sector"]] = (
                sector_distribution.get(out_record["sector"], 0) + 1
            )
            confidence_distribution[out_record["confidence"]] = (
                confidence_distribution.get(out_record["confidence"], 0) + 1
            )
            procurement_distribution[out_record["procurement_class"]] = (
                procurement_distribution.get(out_record["procurement_class"], 0) + 1
            )
            if response.cache_hit:
                cache_hits += 1
            else:
                fresh_calls += 1
                total_input_tokens += response.input_tokens or 0
                total_output_tokens += response.output_tokens or 0

    with jsonl_output.open("w", encoding="utf-8") as out:
        if args.concurrency <= 1:
            for index, record in enumerate(contracts, start=1):
                _process_one((index, record))
                if index % 50 == 0 or index == len(contracts):
                    elapsed = time.monotonic() - started_at
                    rate = index / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{index:>6}/{len(contracts)}] "
                        f"hits={cache_hits} fresh={fresh_calls} "
                        f"failed={failed_count} skipped={skipped_count} "
                        f"rate={rate:.2f}/s "
                        f"in={total_input_tokens:,} out={total_output_tokens:,}"
                    )
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(_process_one, (i + 1, r)): i
                    for i, r in enumerate(contracts)
                }
                completed = 0
                for fut in as_completed(futures):
                    completed += 1
                    fut.result()
                    if completed % 50 == 0 or completed == len(contracts):
                        elapsed = time.monotonic() - started_at
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(
                            f"  [{completed:>6}/{len(contracts)}] "
                            f"hits={cache_hits} fresh={fresh_calls} "
                            f"failed={failed_count} skipped={skipped_count} "
                            f"rate={rate:.2f}/s "
                            f"in={total_input_tokens:,} out={total_output_tokens:,}"
                        )

    elapsed = time.monotonic() - started_at
    # Sonnet 4.6 pricing (v2 upgrade): $3 / M input, $15 / M output
    # regular API. Anthropic Batches API: $1.50 / M input, $7.50 / M
    # output (50% off). Cached input tokens cost 10% of regular
    # input rate (so ~$0.30 / M cached). For Haiku 4.5 the input
    # rate is $1/M and output is $5/M (1/3 of Sonnet); the
    # estimated cost columns reflect both.
    is_haiku = "haiku" in model_id.lower()
    if is_haiku:
        estimated_cost_usd = (
            (total_input_tokens / 1_000_000) * 1.0
            + (total_output_tokens / 1_000_000) * 5.0
        )
    else:
        estimated_cost_usd = (
            (total_input_tokens / 1_000_000) * 3.0
            + (total_output_tokens / 1_000_000) * 15.0
        )
    summary = {
        "task_name": TASK_NAME,
        "prompt_version": prompt_version,
        "model_id": model_id,
        "generated_at": timestamp,
        "concurrency": args.concurrency,
        "input_jsonl": str(jsonl_input),
        "start_offset": args.start_offset,
        "contract_count": len(contracts),
        "cache_hits": cache_hits,
        "fresh_calls": fresh_calls,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "elapsed_seconds": round(elapsed, 2),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd_regular": round(estimated_cost_usd, 4),
        "estimated_cost_usd_batches_50pct": round(estimated_cost_usd * 0.5, 4),
        "sector_distribution": sector_distribution,
        "confidence_distribution": confidence_distribution,
        "procurement_distribution": procurement_distribution,
        "jsonl_path": str(jsonl_output),
        "claim_discipline_caveat": (
            f"These contract topic tags are produced by {model_id} "
            f"under the {prompt_version} prompt at {prompt_path}. They "
            f"are labelled with extraction_method = "
            f"'llm_{prompt_version}' wherever they surface; the "
            "project's claim-discipline rule treats them as a separate "
            "evidence tier from rule-based classifications. Each row's "
            "full input + output envelope is cached at "
            "data/raw/llm_extractions/austender_contract_topic_tag/<sha256>.json "
            "so a researcher can reproduce any tag without an API key."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print(f"Wrote tags for {len(contracts):,} contracts to {jsonl_output}")
    print(
        f"Cache hits: {cache_hits:,}; fresh calls: {fresh_calls:,}; "
        f"failed: {failed_count:,}; skipped: {skipped_count:,}"
    )
    print(f"Tokens: in={total_input_tokens:,} out={total_output_tokens:,}")
    print(f"Estimated cost (regular API): ${estimated_cost_usd:.4f} USD")
    print(
        f"Estimated cost (Batches API, 50% off): "
        f"${estimated_cost_usd * 0.5:.4f} USD"
    )
    print(f"Summary: {summary_path}")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
