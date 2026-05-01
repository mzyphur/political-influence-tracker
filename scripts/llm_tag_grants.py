#!/usr/bin/env python3
"""LLM-assisted topic tagging of GrantConnect grant awards.

Stage 3-grants parallel of Stage 3 contract topic tagging. Reads
parsed grant observation records from
`data/processed/grant_observations/<ts>.jsonl` (produced by
`backend.au_politics_money.ingest.grants`), runs each through
`claude-sonnet-4-6` with the prompt at
`prompts/grant_topic_tag/v1.md`, and writes a JSONL artifact
under `data/processed/llm_grant_topic_tags/`.

A separate loader (`scripts/load_llm_grant_topic_tags.py` —
TBD next batch) lifts the JSONL into the `llm_grant_topic_tag`
Postgres table introduced by migration 052.

Mirrors `scripts/llm_tag_austender_contracts.py` in shape and
discipline:

* Hash-cached at
  `data/raw/llm_extractions/grant_topic_tag/<sha256>.{input,output}.json`.
* Re-runs are no-ops on cache hits.
* Concurrency default 10 (Sonnet 4.6 TPM-aware).
* Strict tool-use schema enforcement.

Operational shape:

    cd <project root>
    backend/.venv/bin/dotenv -f backend/.env run -- \\
        backend/.venv/bin/python scripts/llm_tag_grants.py \\
            --jsonl data/processed/grant_observations/<ts>.jsonl \\
            --limit 200          # pilot first
            --concurrency 10
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


PROMPT_VERSION = "grant_topic_tag_v1"
MODEL_ID = "claude-sonnet-4-6"
TASK_NAME = "grant_topic_tag"

PROMPT_PATH = PROJECT_ROOT / "prompts" / "grant_topic_tag" / "v1.md"


VALID_SECTORS: frozenset[str] = frozenset(
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

VALID_GRANT_CLASSES: frozenset[str] = frozenset(
    {"services", "goods", "capital", "mixed"}
)


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sector", "policy_topics", "grant_class", "summary", "confidence"],
    "properties": {
        "sector": {"type": "string", "enum": sorted(VALID_SECTORS)},
        "policy_topics": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string", "enum": sorted(VALID_POLICY_TOPICS)},
        },
        "grant_class": {"type": "string", "enum": sorted(VALID_GRANT_CLASSES)},
        "summary": {"type": "string", "minLength": 1, "maxLength": 250},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
    },
}


_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str | None) -> str:
    if text is None:
        return ""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _load_system_instruction() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    marker = "## System instruction"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(f"Prompt v1 missing '{marker}' section: {PROMPT_PATH}")
    rest = text[start + len(marker):]
    if rest.startswith(" (load-bearing)"):
        rest = rest[len(" (load-bearing)"):]
    rest = rest.lstrip("\n")
    end = rest.find("\n## ")
    if end >= 0:
        rest = rest[:end]
    return rest.strip()


def _build_user_message(record: dict[str, Any]) -> str:
    agency_name = (record.get("agency") or {}).get("name") or "unknown"
    recipient = record.get("recipient") or {}
    recipient_name = recipient.get("name") or "unknown"
    recipient_abn = recipient.get("abn") or "unknown"
    grant_value_aud = (
        record.get("grant_value_aud") or record.get("funding_amount_aud") or "unknown"
    )
    grant_program = _strip_html(record.get("grant_program")) or "unknown"
    grant_activity = _strip_html(record.get("grant_activity")) or "unknown"
    description = _strip_html(record.get("description")) or "unknown"
    purpose = _strip_html(record.get("purpose")) or "unknown"
    return (
        "Tag this Australian Commonwealth grant award.\n\n"
        f"Agency: {agency_name}\n"
        f"Recipient: {recipient_name}\n"
        f"Recipient ABN: {recipient_abn}\n"
        f"Grant value (AUD): {grant_value_aud}\n"
        f"Grant program: {grant_program}\n"
        f"Grant activity: {grant_activity}\n"
        f"Description: {description}\n"
        f"Purpose: {purpose}\n\n"
        "Call the `record_extraction` tool once with:\n"
        "* sector (one of 40)\n"
        "* policy_topics (one or more of 24, max 4)\n"
        "* grant_class (one of services / goods / capital / mixed)\n"
        "* summary (≤25 words plain English)\n"
        "* confidence (high / medium / low)"
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
                print(f"  warn: skipping malformed JSON: {exc}", file=sys.stderr)
    return rows


def _is_skippable(record: dict[str, Any]) -> tuple[bool, str]:
    description = _strip_html(record.get("description"))
    purpose = _strip_html(record.get("purpose"))
    if len(description) < 3 and len(purpose) < 3:
        return True, "description_and_purpose_too_short"
    return False, ""


def _tag_one(
    client: LLMClient, *, record: dict[str, Any], system_instruction: str
) -> tuple[LLMResponse, dict[str, Any]]:
    user_message = _build_user_message(record)
    response = client.call_json(
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        system_instruction=system_instruction,
        user_message=user_message,
        response_schema=RESPONSE_SCHEMA,
        temperature=0.0,
        max_tokens=400,
    )
    parsed = response.parsed
    if parsed["sector"] not in VALID_SECTORS:
        raise ValueError(
            f"Invalid sector {parsed['sector']!r} for grant {record.get('grant_id')}"
        )
    if parsed["grant_class"] not in VALID_GRANT_CLASSES:
        raise ValueError(
            f"Invalid grant_class {parsed['grant_class']!r} for grant {record.get('grant_id')}"
        )
    invalid_topics = [t for t in parsed["policy_topics"] if t not in VALID_POLICY_TOPICS]
    if invalid_topics:
        raise ValueError(
            f"Invalid policy_topics {invalid_topics!r} for grant {record.get('grant_id')}"
        )

    grant_value_aud = (
        record.get("grant_value_aud") or record.get("funding_amount_aud")
    )
    out_record = {
        "grant_id": record.get("grant_id"),
        "parent_grant_id": record.get("parent_grant_id"),
        "notice_type": record.get("notice_type"),
        "agency_name": (record.get("agency") or {}).get("name"),
        "recipient_name": (record.get("recipient") or {}).get("name"),
        "recipient_abn": (record.get("recipient") or {}).get("abn"),
        "grant_value_aud": grant_value_aud,
        "grant_program": record.get("grant_program"),
        "grant_activity": record.get("grant_activity"),
        "llm_model_id": response.model_id,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_temperature": 0.0,
        "llm_response_sha256": response.sha256,
        "llm_input_tokens": response.input_tokens,
        "llm_output_tokens": response.output_tokens,
        "llm_cache_hit": response.cache_hit,
        "sector": parsed["sector"],
        "policy_topics": parsed["policy_topics"],
        "grant_class": parsed["grant_class"],
        "summary": parsed["summary"],
        "confidence": parsed["confidence"],
        "extraction_method": "llm_grant_topic_tag_v1",
    }
    return response, out_record


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_jsonl(processed_dir: Path) -> Path | None:
    candidates = sorted(
        (processed_dir / "grant_observations").glob("*.jsonl"), reverse=True
    )
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LLM-assisted topic tagging of GrantConnect grant awards "
            "(Stage 3-grants parallel). Reads parsed JSONL records and "
            "tags each with industry sector + policy topics + grant_class "
            "via Claude Sonnet 4.6 + the v1 prompt. Cache-first."
        )
    )
    parser.add_argument(
        "--jsonl", default=None,
        help="GrantConnect parsed JSONL to tag. Default: latest under data/processed/grant_observations/.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum grants to tag per run (cache-aware).",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Override output directory.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=10,
        help="Number of concurrent API calls (default 10; safe under Sonnet 4.6 TPM).",
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY must be set (loaded from backend/.env)", file=sys.stderr)
        return 2

    if args.jsonl:
        jsonl_input = Path(args.jsonl).resolve()
    else:
        jsonl_input = _latest_jsonl(PROCESSED_DIR)
    if not jsonl_input or not jsonl_input.exists():
        print(f"GrantConnect input JSONL not found: {jsonl_input}", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROCESSED_DIR / "llm_grant_topic_tags"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_output = output_dir / f"{timestamp}.jsonl"
    summary_path = output_dir / f"{timestamp}.summary.json"

    print(f"Loading system instruction from {PROMPT_PATH}...")
    system_instruction = _load_system_instruction()

    client = LLMClient(task_name=TASK_NAME)

    print(f"Reading parsed grants from {jsonl_input}...")
    grants = _read_jsonl(jsonl_input)
    print(f"  {len(grants):,} grant records loaded.")

    if args.limit and args.limit > 0:
        grants = grants[: args.limit]
        print(f"  --limit applied: {len(grants):,} grants will be tagged.")

    started_at = time.monotonic()
    cache_hits = 0
    fresh_calls = 0
    sector_distribution: dict[str, int] = {}
    confidence_distribution: dict[str, int] = {}
    grant_class_distribution: dict[str, int] = {}
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
        skip, _ = _is_skippable(record)
        if skip:
            with counters_lock:
                skipped_count += 1
            return
        try:
            response, out_record = _tag_one(
                client, record=record, system_instruction=system_instruction
            )
        except Exception as exc:  # noqa: BLE001
            error_record = {
                "grant_id": record.get("grant_id"),
                "extraction_method": "llm_grant_topic_tag_v1",
                "error": repr(exc),
            }
            with output_lock:
                out.write(json.dumps(error_record, ensure_ascii=False))
                out.write("\n")
            with counters_lock:
                failed_count += 1
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
            grant_class_distribution[out_record["grant_class"]] = (
                grant_class_distribution.get(out_record["grant_class"], 0) + 1
            )
            if response.cache_hit:
                cache_hits += 1
            else:
                fresh_calls += 1
                total_input_tokens += response.input_tokens or 0
                total_output_tokens += response.output_tokens or 0

    with jsonl_output.open("w", encoding="utf-8") as out:
        if args.concurrency <= 1:
            for index, record in enumerate(grants, start=1):
                _process_one((index, record))
                if index % 50 == 0 or index == len(grants):
                    elapsed = time.monotonic() - started_at
                    rate = index / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{index:>6}/{len(grants)}] hits={cache_hits} "
                        f"fresh={fresh_calls} failed={failed_count} skipped={skipped_count} "
                        f"rate={rate:.2f}/s in={total_input_tokens:,} out={total_output_tokens:,}"
                    )
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(_process_one, (i + 1, r)): i for i, r in enumerate(grants)
                }
                completed = 0
                for fut in as_completed(futures):
                    completed += 1
                    fut.result()
                    if completed % 50 == 0 or completed == len(grants):
                        elapsed = time.monotonic() - started_at
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(
                            f"  [{completed:>6}/{len(grants)}] hits={cache_hits} "
                            f"fresh={fresh_calls} failed={failed_count} skipped={skipped_count} "
                            f"rate={rate:.2f}/s in={total_input_tokens:,} out={total_output_tokens:,}"
                        )

    elapsed = time.monotonic() - started_at
    estimated_cost_usd = (
        (total_input_tokens / 1_000_000) * 3.0
        + (total_output_tokens / 1_000_000) * 15.0
    )
    summary = {
        "task_name": TASK_NAME,
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID,
        "generated_at": timestamp,
        "concurrency": args.concurrency,
        "input_jsonl": str(jsonl_input),
        "grant_count": len(grants),
        "cache_hits": cache_hits,
        "fresh_calls": fresh_calls,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "elapsed_seconds": round(elapsed, 2),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd_sonnet_4_6_regular": round(estimated_cost_usd, 4),
        "estimated_cost_usd_sonnet_4_6_batches_50pct": round(
            estimated_cost_usd * 0.5, 4
        ),
        "sector_distribution": sector_distribution,
        "confidence_distribution": confidence_distribution,
        "grant_class_distribution": grant_class_distribution,
        "jsonl_path": str(jsonl_output),
        "claim_discipline_caveat": (
            "These grant topic tags are produced by Claude Sonnet 4.6 "
            "under the v1 prompt at prompts/grant_topic_tag/v1.md. They are "
            "labelled with extraction_method = 'llm_grant_topic_tag_v1' "
            "wherever they surface; the project's claim-discipline rule "
            "treats them as a separate evidence tier from rule-based "
            "classifications. Each row's full input + output envelope is "
            "cached at data/raw/llm_extractions/grant_topic_tag/<sha256>.json "
            "so a researcher can reproduce any tag without an API key."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print(f"Wrote tags for {len(grants):,} grants to {jsonl_output}")
    print(
        f"Cache hits: {cache_hits:,}; fresh calls: {fresh_calls:,}; "
        f"failed: {failed_count:,}; skipped: {skipped_count:,}"
    )
    print(f"Tokens: in={total_input_tokens:,} out={total_output_tokens:,}")
    print(f"Estimated cost (regular API): ${estimated_cost_usd:.4f} USD")
    print(f"Summary: {summary_path}")
    return 0 if failed_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
