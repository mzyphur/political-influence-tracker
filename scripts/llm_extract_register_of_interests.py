#!/usr/bin/env python3
"""LLM-assisted deep extraction of House Register of Interests sections.

Stage 2 of the project's hybrid LLM pipeline. Reads section-level
text from `data/processed/house_interest_sections/<ts>.jsonl`
(produced by `backend/au_politics_money/ingest/house_interests.py`),
runs each section through `claude-sonnet-4-6` with the prompt at
`prompts/register_of_interests_extraction/v1.md`, and writes a
JSONL artifact under
`data/processed/llm_register_of_interests/`.

A separate loader (`scripts/load_llm_register_of_interests.py`)
lifts the JSONL into the `house_interest_record_llm` Postgres
table introduced by migration 040.

Reproducibility chain (matches Stages 1+3):

* Every API call is hash-cached at
  `data/raw/llm_extractions/register_of_interests_extraction/<sha256>.{input,output}.json`.
* Re-running with the same prompt version + same section input is
  a no-op (cache-hit on every call).
* Cost is logged per batch and at total — visible cap on spend.
* Every cached row carries `extraction_method =
  'llm_register_of_interests_v1'`.

Operational shape:

    cd <project root>
    backend/.venv/bin/dotenv -f backend/.env run -- \\
        backend/.venv/bin/python scripts/llm_extract_register_of_interests.py \\
            --jsonl data/processed/house_interest_sections/<ts>.jsonl \\
            --limit 200          # pilot; omit for full run
            --concurrency 50     # parallel API calls
"""

from __future__ import annotations

import argparse
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


PROMPT_VERSION = "register_of_interests_extraction_v1"
MODEL_ID = "claude-sonnet-4-6"
TASK_NAME = "register_of_interests_extraction"

PROMPT_PATH = PROJECT_ROOT / "prompts" / "register_of_interests_extraction" / "v1.md"


VALID_ITEM_TYPES: frozenset[str] = frozenset(
    {
        "shareholding", "real_estate", "directorship",
        "partnership", "liability", "investment",
        "other_asset", "gift", "sponsored_travel",
        "donation_received", "membership", "other_interest",
    }
)

VALID_COUNTERPARTY_TYPES: frozenset[str] = frozenset(
    {
        "company", "individual", "government",
        "foreign_government", "union", "association",
        "political_party", "charity", "unknown",
    }
)

VALID_DISPOSITIONS: frozenset[str] = frozenset(
    {
        "retained", "surrendered_displayed",
        "surrendered_donated", "unknown", "not_applicable",
    }
)


RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item_type", "counterparty_name",
                             "counterparty_type", "description",
                             "estimated_value_aud", "event_date",
                             "disposition", "confidence",
                             "evidence_excerpt"],
                "properties": {
                    "item_type": {
                        "type": "string",
                        "enum": sorted(VALID_ITEM_TYPES),
                    },
                    "counterparty_name": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "counterparty_type": {
                        "type": "string",
                        "enum": sorted(VALID_COUNTERPARTY_TYPES),
                    },
                    "description": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 300,
                    },
                    "estimated_value_aud": {
                        "type": ["number", "null"],
                    },
                    "event_date": {
                        "type": ["string", "null"],
                        "pattern": "^\\d{4}-\\d{2}-\\d{2}$",
                    },
                    "disposition": {
                        "type": "string",
                        "enum": sorted(VALID_DISPOSITIONS),
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "evidence_excerpt": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 200,
                    },
                },
            },
        },
    },
}


# Section numbers 1-3 are form preamble in the 48th-parliament
# layout — they never carry disclosure items. Skipping them at the
# driver layer saves ~25% of the API spend with zero risk (the
# prompt would also return `[]` for these but we'd pay for the call).
PREAMBLE_SECTION_NUMBERS = frozenset({"1", "2", "3"})

# Regex that matches a section's text being a clean nil-return.
# When ALL non-heading content lines say "Not Applicable" / "Nil"
# / "N/A" / blank, the section is empty. Skipping these at the
# driver layer means the LLM doesn't need to confirm them.
_NIL_RETURN_RE = re.compile(
    r"^(\s*(not\s+applicable|nil|n\.?\s*/?\s*a\.?|none|nil\s+return)\s*)+$",
    re.IGNORECASE | re.MULTILINE,
)


def _is_nil_return(section_text: str) -> bool:
    """Return True if the section text is structurally a nil return."""
    if not section_text or not section_text.strip():
        return True
    # Strip the leading section heading "1. Shareholdings..." line —
    # it's a heading, not content. Look at the body that follows.
    lines = section_text.strip().splitlines()
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    if not body:
        return True
    # Every non-heading line must be a "Not Applicable" or labelling
    # line ("Self", "Spouse/Partner", "Dependent Children", or a
    # form heading like "Name of company"). Look for at least one
    # plausibly-substantive line.
    substantive_lines = [
        line.strip()
        for line in body.splitlines()
        if line.strip()
        and not _NIL_RETURN_RE.fullmatch(line.strip())
        and line.strip().lower()
        not in {
            "self", "spouse", "spouse/", "partner", "spouse/partner",
            "dependent", "dependent children", "children",
            "name", "name of company", "name of company or companies",
            "address", "creditor", "nature of liability", "purpose",
        }
    ]
    return len(substantive_lines) == 0


def _load_system_instruction() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    marker = "## System instruction"
    start = text.find(marker)
    if start < 0:
        raise RuntimeError(
            f"Prompt v1 missing '{marker}' section: {PROMPT_PATH}"
        )
    rest = text[start + len(marker):]
    if rest.startswith(" (load-bearing)"):
        rest = rest[len(" (load-bearing)"):]
    rest = rest.lstrip("\n")
    end = rest.find("\n## ")
    if end >= 0:
        rest = rest[:end]
    return rest.strip()


def _build_user_message(section: dict[str, Any]) -> str:
    return (
        "Extract structured disclosure records from the following ONE "
        "section of an Australian House Register of Members' Interests "
        "PDF.\n\n"
        "Member context (DO NOT copy into output):\n"
        f"- member_name: {section.get('member_name') or 'unknown'}\n"
        f"- electorate: {section.get('electorate') or 'unknown'}\n"
        f"- state: {section.get('state') or 'unknown'}\n\n"
        "Section context:\n"
        f"- section_number: {section.get('section_number') or 'unknown'}\n"
        f"- section_title: {section.get('section_title') or 'unknown'}\n\n"
        "Section text (OCR-extracted, may contain artefacts):\n"
        '"""\n'
        f"{section.get('section_text') or ''}\n"
        '"""\n\n'
        "Apply the operating principles. If the section is a nil return, "
        'return {"items": []}.\n'
        "Call the `record_extraction` tool exactly once with the result."
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


def _is_skippable(section: dict[str, Any]) -> tuple[bool, str]:
    """Skip preamble sections (1-3) and structural nil-returns.

    Returns (skip, reason). When skipped at the driver layer, we don't
    pay for the API call but still emit a JSONL row marking the
    section as nil so the loader can record the "no items" outcome.
    """
    section_number = str(section.get("section_number") or "")
    if section_number in PREAMBLE_SECTION_NUMBERS:
        return True, "preamble_section"
    section_text = section.get("section_text") or ""
    if _is_nil_return(section_text):
        return True, "structural_nil_return"
    return False, ""


def _extract_one(
    client: LLMClient,
    *,
    section: dict[str, Any],
    system_instruction: str,
) -> tuple[LLMResponse, dict[str, Any]]:
    user_message = _build_user_message(section)
    response = client.call_json(
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        system_instruction=system_instruction,
        user_message=user_message,
        response_schema=RESPONSE_SCHEMA,
        temperature=0.0,
        max_tokens=2048,
    )
    parsed = response.parsed
    items = parsed.get("items") or []
    # Belt-and-braces validation on each item.
    for item in items:
        if item.get("item_type") not in VALID_ITEM_TYPES:
            raise ValueError(
                f"Invalid item_type {item.get('item_type')!r} for "
                f"source_id {section.get('source_id')!r}"
            )
        if item.get("counterparty_type") not in VALID_COUNTERPARTY_TYPES:
            raise ValueError(
                f"Invalid counterparty_type {item.get('counterparty_type')!r} for "
                f"source_id {section.get('source_id')!r}"
            )
        if item.get("disposition") not in VALID_DISPOSITIONS:
            raise ValueError(
                f"Invalid disposition {item.get('disposition')!r} for "
                f"source_id {section.get('source_id')!r}"
            )

    out_record = {
        "source_id": section.get("source_id"),
        "member_name": section.get("member_name"),
        "family_name": section.get("family_name"),
        "given_names": section.get("given_names"),
        "electorate": section.get("electorate"),
        "state": section.get("state"),
        "section_number": section.get("section_number"),
        "section_title": section.get("section_title"),
        "url": section.get("url"),
        "llm_model_id": response.model_id,
        "llm_prompt_version": PROMPT_VERSION,
        "llm_temperature": 0.0,
        "llm_response_sha256": response.sha256,
        "llm_input_tokens": response.input_tokens,
        "llm_output_tokens": response.output_tokens,
        "llm_cache_hit": response.cache_hit,
        "items": items,
        "extraction_method": "llm_register_of_interests_v1",
    }
    return response, out_record


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_jsonl(processed_dir: Path) -> Path | None:
    candidates = sorted(
        (processed_dir / "house_interest_sections").glob("*.jsonl"),
        reverse=True,
    )
    return candidates[0] if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "LLM-assisted deep extraction of House Register of Interests "
            "sections (Stage 2). Reads section-level text JSONL and "
            "extracts structured disclosure items via Claude Sonnet 4.6 "
            "+ the v1 prompt. Cache-first; re-runs are no-ops."
        )
    )
    parser.add_argument(
        "--jsonl", default=None,
        help=(
            "House register section JSONL to extract. If omitted, picks "
            "the most recent file under "
            "data/processed/house_interest_sections/."
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Maximum sections to extract per run (cache-aware).",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Override output directory for the JSONL/summary artefacts.",
    )
    parser.add_argument(
        "--concurrency", type=int, default=50,
        help=(
            "Number of concurrent API calls (default: 50). Sonnet 4.6 "
            "calls are slower than Haiku (~5s vs 2s); 50 concurrent at "
            "5s settles around 10 calls/sec which is fine for any tier."
        ),
    )
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        default=False,
        help=(
            "Emit JSONL rows for skipped sections (preamble + nil "
            "returns) with items=[]. Default: skipped sections are not "
            "emitted, saving disk + downstream load work."
        ),
    )
    args = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "ANTHROPIC_API_KEY must be set (loaded from backend/.env)",
            file=sys.stderr,
        )
        return 2

    if args.jsonl:
        jsonl_input = Path(args.jsonl).resolve()
    else:
        jsonl_input = _latest_jsonl(PROCESSED_DIR)
    if not jsonl_input or not jsonl_input.exists():
        print(
            f"House register sections JSONL not found: {jsonl_input}",
            file=sys.stderr,
        )
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROCESSED_DIR / "llm_register_of_interests"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_output = output_dir / f"{timestamp}.jsonl"
    summary_path = output_dir / f"{timestamp}.summary.json"

    print(f"Loading system instruction from {PROMPT_PATH}...")
    system_instruction = _load_system_instruction()

    client = LLMClient(task_name=TASK_NAME)

    print(f"Reading parsed sections from {jsonl_input}...")
    sections = _read_jsonl(jsonl_input)
    print(f"  {len(sections):,} register sections loaded.")

    if args.limit and args.limit > 0:
        sections = sections[: args.limit]
        print(f"  --limit applied: {len(sections):,} sections will be tagged.")

    started_at = time.monotonic()
    cache_hits = 0
    fresh_calls = 0
    item_type_distribution: dict[str, int] = {}
    counterparty_type_distribution: dict[str, int] = {}
    confidence_distribution: dict[str, int] = {}
    total_input_tokens = 0
    total_output_tokens = 0
    failed_count = 0
    skipped_count = 0
    total_items_extracted = 0

    output_lock = threading.Lock()
    counters_lock = threading.Lock()

    def _process_one(index_section: tuple[int, dict[str, Any]]) -> None:
        nonlocal cache_hits, fresh_calls, total_input_tokens
        nonlocal total_output_tokens, failed_count, skipped_count
        nonlocal total_items_extracted
        index, section = index_section
        skip, reason = _is_skippable(section)
        if skip:
            with counters_lock:
                skipped_count += 1
            if args.include_skipped:
                empty_record = {
                    "source_id": section.get("source_id"),
                    "member_name": section.get("member_name"),
                    "section_number": section.get("section_number"),
                    "section_title": section.get("section_title"),
                    "items": [],
                    "extraction_method": "driver_skipped",
                    "skip_reason": reason,
                }
                with output_lock:
                    out.write(json.dumps(empty_record, ensure_ascii=False))
                    out.write("\n")
            return
        try:
            response, out_record = _extract_one(
                client,
                section=section,
                system_instruction=system_instruction,
            )
        except Exception as exc:  # noqa: BLE001
            error_record = {
                "source_id": section.get("source_id"),
                "section_number": section.get("section_number"),
                "extraction_method": "llm_register_of_interests_v1",
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
            for item in out_record["items"]:
                total_items_extracted += 1
                item_type_distribution[item["item_type"]] = (
                    item_type_distribution.get(item["item_type"], 0) + 1
                )
                counterparty_type_distribution[item["counterparty_type"]] = (
                    counterparty_type_distribution.get(item["counterparty_type"], 0) + 1
                )
                confidence_distribution[item["confidence"]] = (
                    confidence_distribution.get(item["confidence"], 0) + 1
                )
            if response.cache_hit:
                cache_hits += 1
            else:
                fresh_calls += 1
                total_input_tokens += response.input_tokens or 0
                total_output_tokens += response.output_tokens or 0

    with jsonl_output.open("w", encoding="utf-8") as out:
        if args.concurrency <= 1:
            for index, section in enumerate(sections, start=1):
                _process_one((index, section))
                if index % 25 == 0 or index == len(sections):
                    elapsed = time.monotonic() - started_at
                    rate = index / elapsed if elapsed > 0 else 0
                    print(
                        f"  [{index:>5}/{len(sections)}] "
                        f"hits={cache_hits} fresh={fresh_calls} "
                        f"failed={failed_count} skipped={skipped_count} "
                        f"items={total_items_extracted} "
                        f"rate={rate:.2f}/s "
                        f"in={total_input_tokens:,} out={total_output_tokens:,}"
                    )
        else:
            with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
                futures = {
                    pool.submit(_process_one, (i + 1, s)): i
                    for i, s in enumerate(sections)
                }
                completed = 0
                for fut in as_completed(futures):
                    completed += 1
                    fut.result()
                    if completed % 25 == 0 or completed == len(sections):
                        elapsed = time.monotonic() - started_at
                        rate = completed / elapsed if elapsed > 0 else 0
                        print(
                            f"  [{completed:>5}/{len(sections)}] "
                            f"hits={cache_hits} fresh={fresh_calls} "
                            f"failed={failed_count} skipped={skipped_count} "
                            f"items={total_items_extracted} "
                            f"rate={rate:.2f}/s "
                            f"in={total_input_tokens:,} out={total_output_tokens:,}"
                        )

    elapsed = time.monotonic() - started_at
    # Sonnet 4.6 pricing: $3 / M input, $15 / M output (regular API).
    # Batches API: $1.50 / M input, $7.50 / M output (50% off).
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
        "section_count": len(sections),
        "cache_hits": cache_hits,
        "fresh_calls": fresh_calls,
        "failed_count": failed_count,
        "skipped_count": skipped_count,
        "total_items_extracted": total_items_extracted,
        "elapsed_seconds": round(elapsed, 2),
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "estimated_cost_usd_sonnet_4_6_regular": round(estimated_cost_usd, 4),
        "estimated_cost_usd_sonnet_4_6_batches_50pct": round(
            estimated_cost_usd * 0.5, 4
        ),
        "item_type_distribution": item_type_distribution,
        "counterparty_type_distribution": counterparty_type_distribution,
        "confidence_distribution": confidence_distribution,
        "jsonl_path": str(jsonl_output),
        "claim_discipline_caveat": (
            "These disclosure items are extracted by Claude Sonnet 4.6 "
            "under the v1 prompt at "
            "prompts/register_of_interests_extraction/v1.md. They are "
            "labelled with extraction_method = "
            "'llm_register_of_interests_v1' wherever they surface; the "
            "project's claim-discipline rule treats them as a separate "
            "evidence tier from rule-based parses. Each row's full "
            "input + output envelope is cached at "
            "data/raw/llm_extractions/register_of_interests_extraction/<sha256>.json "
            "so a researcher can reproduce any item without an API key. "
            "These are NEVER used for the project's byte-identical "
            "direct-money totals invariant."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print()
    print(f"Wrote extractions for {len(sections):,} sections to {jsonl_output}")
    print(
        f"Cache hits: {cache_hits:,}; fresh calls: {fresh_calls:,}; "
        f"failed: {failed_count:,}; skipped: {skipped_count:,}"
    )
    print(f"Items extracted: {total_items_extracted:,}")
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
