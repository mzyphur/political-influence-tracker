#!/usr/bin/env python3
"""Export the contract × donor cross-source correlation as a JSON
+ CSV report under `data/processed/contract_donor_overlap/`.

This is the project's headline analytical surface: entities that
BOTH (a) received Australian Government contracts (LLM-tagged in
`austender_contract_topic_tag`) AND (b) appear as donors / gift-
givers / hosts in `influence_event` (deterministic disclosure
data).

Claim discipline:
  * The contract data is LLM-tagged (evidence tier 2).
  * The donation/gift data is deterministic-source-backed (tier 1).
  * NEVER sum contract-receipts + donations into a single number.
  * Public surfaces preserve the tier labels.

Operational shape:

    cd <project root>
    DATABASE_URL=postgresql://au_politics:change-me-local-only@127.0.0.1:54329/au_politics \\
        backend/.venv/bin/python scripts/report_contract_donor_overlap.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg  # type: ignore

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from au_politics_money.config import PROCESSED_DIR  # noqa: E402


def _coerce(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat") and callable(value.isoformat):
        return value.isoformat()
    if isinstance(value, list):
        return [_coerce(v) for v in value]
    if isinstance(value, dict):
        return {k: _coerce(v) for k, v in value.items()}
    return value


def _query(conn) -> list[dict[str, Any]]:
    sql = """
    SELECT
        supplier_name,
        supplier_normalized,
        contract_prompt_version,
        contract_count,
        distinct_contract_ids,
        total_contract_value_aud,
        contract_sectors,
        contract_policy_topics,
        contract_agencies,
        matched_entity_id,
        matched_entity_canonical_name,
        matched_entity_type,
        donor_event_count,
        money_event_count,
        campaign_support_event_count,
        private_interest_event_count,
        benefit_event_count,
        access_event_count,
        organisational_role_event_count,
        donor_total_money_aud,
        donor_total_campaign_support_aud,
        donor_event_families,
        donor_earliest_event_date,
        donor_latest_event_date,
        contract_evidence_tier,
        donor_evidence_tier,
        claim_discipline_note
    FROM v_contract_donor_overlap
    WHERE contract_prompt_version = (
        SELECT prompt_version FROM austender_contract_topic_tag
        WHERE prompt_version LIKE 'austender_contract_topic_tag_v%'
        ORDER BY (regexp_replace(prompt_version, '\\D', '', 'g'))::int DESC,
                 prompt_version DESC
        LIMIT 1
    )
    ORDER BY total_contract_value_aud DESC NULLS LAST,
             donor_total_money_aud DESC NULLS LAST
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def _summary_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate stats across the full overlap set."""
    if not rows:
        return {
            "row_count": 0,
            "summary": "No overlapping suppliers found.",
        }
    total_contract_value = sum(
        (r.get("total_contract_value_aud") or 0) for r in rows
    )
    total_donor_money = sum(
        (r.get("donor_total_money_aud") or 0) for r in rows
    )
    total_campaign_support = sum(
        (r.get("donor_total_campaign_support_aud") or 0) for r in rows
    )
    sector_counts: dict[str, int] = {}
    for r in rows:
        for s in (r.get("contract_sectors") or []):
            if s:
                sector_counts[s] = sector_counts.get(s, 0) + 1
    return {
        "row_count": len(rows),
        "total_contract_value_aud": float(total_contract_value),
        "total_donor_money_aud": float(total_donor_money),
        "total_donor_campaign_support_aud": float(total_campaign_support),
        "sector_distribution": dict(
            sorted(sector_counts.items(), key=lambda kv: -kv[1])
        ),
        "claim_discipline_note": (
            "Contract values (LLM-tagged, evidence tier 2) and donor "
            "amounts (deterministic-source-backed, evidence tier 1) "
            "are NOT summed. They are reported side-by-side as separate "
            "aggregates. No causation is implied; the overlap is a "
            "cross-source temporal correlation only."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Export the contract × donor cross-source correlation "
            "as a JSON + CSV report."
        )
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument(
        "--output-dir", default=None,
        help=(
            "Override the output directory. Default: "
            "data/processed/contract_donor_overlap/"
        ),
    )
    args = parser.parse_args(argv)

    if not args.database_url:
        print("DATABASE_URL must be set", file=sys.stderr)
        return 2

    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir
        else PROCESSED_DIR / "contract_donor_overlap"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"{timestamp}.json"
    csv_path = output_dir / f"{timestamp}.csv"
    summary_path = output_dir / f"{timestamp}.summary.json"

    print(f"Querying v_contract_donor_overlap from {args.database_url[:60]}...")
    with psycopg.connect(args.database_url, autocommit=False) as conn:
        rows = _query(conn)

    print(f"  {len(rows):,} overlapping suppliers found.")

    rows_serialisable = [_coerce(r) for r in rows]
    json_path.write_text(
        json.dumps(rows_serialisable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if rows:
        with csv_path.open("w", encoding="utf-8", newline="") as csvfile:
            csv_columns = list(rows[0].keys())
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for row in rows_serialisable:
                # Flatten array columns to comma-separated strings for
                # CSV friendliness.
                flat = {
                    k: (",".join(str(x) for x in v) if isinstance(v, list) else v)
                    for k, v in row.items()
                }
                writer.writerow(flat)

    summary = _summary_stats(rows)
    summary["generated_at"] = timestamp
    summary["json_path"] = str(json_path)
    summary["csv_path"] = str(csv_path)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"Wrote {json_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")
    if rows:
        print()
        print("Top 10 overlapping suppliers by contract value:")
        for r in rows[:10]:
            supplier = r.get("supplier_name") or "?"
            contract_value = r.get("total_contract_value_aud") or 0
            money_total = r.get("donor_total_money_aud") or 0
            event_count = r.get("donor_event_count") or 0
            print(
                f"  {supplier:>50}  contracts=${float(contract_value):>14,.0f}  "
                f"donations=${float(money_total):>11,.0f}  events={event_count}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
