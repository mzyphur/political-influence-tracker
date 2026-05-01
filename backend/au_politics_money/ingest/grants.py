"""GrantConnect federal-grant CSV ingestion (Batch CC).

Reads CSV exports from the Department of Finance's GrantConnect
public dataset on data.gov.au (CKAN id is documented in
``docs/data_sources.md``; CC BY 3.0 AU licence) and normalises each
grant award row into a stable JSONL record + per-file summary JSON.

Schema is intentionally aligned with
``au_politics_money.ingest.austender`` so the cross-correlation
views (`v_sector_money_outflow`, etc.) can join contracts and
grants on the same sector / agency / recipient axes without bespoke
adapters per source.

**What the JSONL records DO carry (per grant award row):**

- ``grant_id``: GrantConnect identifier (e.g. ``"GA12345"``).
  Stable; the natural primary key.
- ``parent_grant_id``: parent identifier if this row is a
  variation; ``None`` otherwise.
- ``notice_type``: ``"New"`` / ``"Variation"`` / etc.
- ``agency_name``, ``branch``, ``division``: the awarding
  Commonwealth agency / sub-unit.
- ``agency_ref_id``, ``office_postcode``: agency context.
- ``recipient_name``: grant recipient (organisation or individual).
- ``recipient_abn``: recipient's ABN.
- ``recipient_address``, ``recipient_suburb``,
  ``recipient_postcode``, ``recipient_state``,
  ``recipient_country``: recipient location.
- ``grant_value_aud``: total grant value (numeric, AUD).
- ``funding_amount_aud``: actual funding amount disbursed (often
  same as grant_value_aud; can differ for multi-year grants).
- ``publish_date``, ``decision_date``, ``start_date``, ``end_date``:
  ISO-8601 dates parsed from the source's DD/MM/YYYY format.
- ``description``, ``purpose``: free-text grant description and
  purpose statement.
- ``grant_program``, ``grant_activity``, ``cfda_code``: program /
  activity classification.
- ``location_postcode``, ``location_suburb``, ``location_state``:
  location of the grant activity (when distinct from recipient).
- ``schema_version``: ``"grants_v1"``.
- ``source_dataset``, ``csv_line_no``: provenance.

**What the JSONL records do NOT carry yet:**

- LLM topic tags (those land in a follow-up Stage-3-grants run via
  ``scripts/llm_tag_grants.py`` mirroring the AusTender tagger).
- DB row ids (the loader assigns those).
- Cross-link to the grant recipient's entity_id (resolved at
  load time via ABN match).
"""

from __future__ import annotations

import csv
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION: str = "grants_v1"
SOURCE_DATASET: str = "grantconnect_grant_awards"


@dataclass(frozen=True)
class GrantsParseSummary:
    """Lightweight per-CSV summary written alongside the JSONL."""

    schema_version: str
    source_dataset: str
    source_csv_path: str
    csv_line_count: int
    record_count: int
    failed_rows: int
    earliest_publish_date: str | None
    latest_publish_date: str | None
    distinct_agencies: int
    distinct_recipients: int
    total_grant_value_aud: str
    top_agencies: list[dict[str, Any]]
    top_recipients: list[dict[str, Any]]


# Canonical column-name aliases. The GrantConnect CSV schema has
# changed minor names over the years; the parser tolerates the
# common variants.
_COLUMN_ALIASES: dict[str, list[str]] = {
    "grant_id": ["GrantID", "Grant Award ID", "Grant ID"],
    "parent_grant_id": ["ParentGrantID", "Parent Grant ID"],
    "notice_type": ["NoticeType", "Notice Type"],
    "agency_name": ["AgencyName", "Department/Agency", "Agency"],
    "agency_ref_id": ["AgencyRefID", "Agency Reference ID"],
    "agency_branch": ["AgencyBranch", "Branch"],
    "agency_division": ["AgencyDivision", "Division"],
    "agency_office_postcode": ["AgencyOfficePostcode", "Office Postcode"],
    "recipient_name": ["RecipientName", "Grantee Name", "Recipient"],
    "recipient_abn": ["RecipientABN", "ABN"],
    "recipient_address": ["RecipientAddress", "Address"],
    "recipient_suburb": ["RecipientSuburb", "Suburb"],
    "recipient_postcode": ["RecipientPostcode", "Postcode"],
    "recipient_state": ["RecipientState", "State"],
    "recipient_country": ["RecipientCountry", "Country"],
    "grant_value_aud": [
        "GrantAmount",
        "Total Grant Value (AUD GST inc.)",
        "Total Grant Value (AUD)",
        "Value (AUD)",
    ],
    "funding_amount_aud": [
        "FundingAmount",
        "Total Funding (AUD)",
        "Funding (AUD)",
    ],
    "publish_date": ["PublishDate", "Publish Date"],
    "decision_date": ["DecisionDate", "Decision Date"],
    "start_date": ["StartDate", "Grant Start Date", "Start Date"],
    "end_date": ["EndDate", "Grant End Date", "End Date"],
    "grant_program": ["GrantProgram", "Program"],
    "grant_activity": ["GrantActivity", "Activity"],
    "description": ["Description", "Grant Description"],
    "purpose": ["Purpose", "Grant Purpose"],
    "cfda_code": ["CFDACode", "CFDA Code"],
    "location_postcode": ["LocationPostcode", "Activity Postcode"],
    "location_suburb": ["LocationSuburb", "Activity Suburb"],
    "location_state": ["LocationState", "Activity State"],
}


_NULL_TOKENS: set[str] = {"", "NULL", "Null", "null", "N/A", "n/a"}
_DATE_FORMATS: list[str] = [
    "%d/%m/%Y",
    "%Y-%m-%d",
    "%d-%m-%Y",
    "%m/%d/%Y",
]
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped in _NULL_TOKENS:
        return None
    # Strip any HTML tags (some descriptions carry markup) and
    # decode entities.
    cleaned = _HTML_TAG_RE.sub(" ", stripped)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def _parse_date(value: str | None) -> date | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _parse_money(value: str | None) -> Decimal | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    cleaned = cleaned.replace("$", "").replace(",", "").replace(" ", "")
    if cleaned.upper() in {"NIL", "TBA", "TBD", "INDETERMINATE"}:
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_abn(value: str | None) -> str | None:
    """Normalise an ABN: strip spaces, remove non-digits, keep only
    11-digit results. Australian ABNs are 11 digits; anything else
    is preserved as-is for downstream resolution.
    """
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    digits = re.sub(r"\D+", "", cleaned)
    if len(digits) == 11:
        return digits
    return cleaned  # preserve non-standard for review


def _resolve_column(headers: list[str], canonical: str) -> str | None:
    """Return the actual header name in the CSV that matches one of
    the known aliases for `canonical`. None if no alias matches.
    """
    aliases = _COLUMN_ALIASES.get(canonical, [])
    lower_map = {h.lower().strip(): h for h in headers}
    for alias in aliases:
        actual = lower_map.get(alias.lower().strip())
        if actual:
            return actual
    return None


def _normalise_row(
    row: dict[str, str], column_map: dict[str, str | None], csv_line_no: int
) -> dict[str, Any]:
    """Convert one CSV row into the stable JSONL record shape."""

    def get(canonical: str) -> str | None:
        col = column_map.get(canonical)
        if col is None:
            return None
        return row.get(col)

    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_dataset": SOURCE_DATASET,
        "csv_line_no": csv_line_no,
        "grant_id": _clean_text(get("grant_id")),
        "parent_grant_id": _clean_text(get("parent_grant_id")),
        "notice_type": _clean_text(get("notice_type")),
        "agency": {
            "name": _clean_text(get("agency_name")),
            "ref_id": _clean_text(get("agency_ref_id")),
            "branch": _clean_text(get("agency_branch")),
            "division": _clean_text(get("agency_division")),
            "office_postcode": _clean_text(get("agency_office_postcode")),
        },
        "recipient": {
            "name": _clean_text(get("recipient_name")),
            "abn": _parse_abn(get("recipient_abn")),
            "address": _clean_text(get("recipient_address")),
            "suburb": _clean_text(get("recipient_suburb")),
            "postcode": _clean_text(get("recipient_postcode")),
            "state": _clean_text(get("recipient_state")),
            "country": _clean_text(get("recipient_country")),
        },
        "grant_value_aud": _decimal_to_str(_parse_money(get("grant_value_aud"))),
        "funding_amount_aud": _decimal_to_str(_parse_money(get("funding_amount_aud"))),
        "publish_date": _date_to_str(_parse_date(get("publish_date"))),
        "decision_date": _date_to_str(_parse_date(get("decision_date"))),
        "start_date": _date_to_str(_parse_date(get("start_date"))),
        "end_date": _date_to_str(_parse_date(get("end_date"))),
        "grant_program": _clean_text(get("grant_program")),
        "grant_activity": _clean_text(get("grant_activity")),
        "description": _clean_text(get("description")),
        "purpose": _clean_text(get("purpose")),
        "cfda_code": _clean_text(get("cfda_code")),
        "location": {
            "postcode": _clean_text(get("location_postcode")),
            "suburb": _clean_text(get("location_suburb")),
            "state": _clean_text(get("location_state")),
        },
    }
    return record


def _decimal_to_str(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _date_to_str(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def normalise_csv(csv_path: Path) -> tuple[Iterable[dict[str, Any]], Path]:
    """Yield normalised JSONL records from one GrantConnect CSV.
    Returns the iterable + the input path for caller bookkeeping.
    """
    return (_iterate_csv(csv_path), csv_path)


def _iterate_csv(csv_path: Path) -> Iterable[dict[str, Any]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            return
        column_map = {
            canonical: _resolve_column(list(reader.fieldnames), canonical)
            for canonical in _COLUMN_ALIASES
        }
        for csv_line_no, row in enumerate(reader, start=2):  # 1=header
            record = _normalise_row(row, column_map, csv_line_no)
            if not record.get("grant_id"):
                # Skip rows without a stable identifier.
                continue
            yield record


def write_jsonl_with_summary(
    csv_path: Path,
    output_jsonl: Path,
    output_summary: Path,
) -> GrantsParseSummary:
    """Run the parser end-to-end: write JSONL + summary."""
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)

    records: list[dict[str, Any]] = []
    failed = 0
    publish_dates: list[date] = []
    agencies: dict[str, int] = {}
    recipients: dict[str, int] = {}
    total_grant_value: Decimal = Decimal(0)

    with output_jsonl.open("w", encoding="utf-8") as out_fh:
        for record in _iterate_csv(csv_path):
            try:
                out_fh.write(json.dumps(record, ensure_ascii=False))
                out_fh.write("\n")
                records.append(record)
                d = _parse_date(record.get("publish_date"))
                if d:
                    publish_dates.append(d)
                a = (record.get("agency") or {}).get("name")
                if a:
                    agencies[a] = agencies.get(a, 0) + 1
                r = (record.get("recipient") or {}).get("name")
                if r:
                    recipients[r] = recipients.get(r, 0) + 1
                v = record.get("grant_value_aud")
                if v:
                    try:
                        total_grant_value += Decimal(v)
                    except (InvalidOperation, ValueError):
                        pass
            except Exception:  # noqa: BLE001
                failed += 1

    csv_line_count = (
        records[-1].get("csv_line_no", 0) if records else 0
    )

    summary = GrantsParseSummary(
        schema_version=SCHEMA_VERSION,
        source_dataset=SOURCE_DATASET,
        source_csv_path=str(csv_path),
        csv_line_count=csv_line_count,
        record_count=len(records),
        failed_rows=failed,
        earliest_publish_date=(
            min(publish_dates).isoformat() if publish_dates else None
        ),
        latest_publish_date=(
            max(publish_dates).isoformat() if publish_dates else None
        ),
        distinct_agencies=len(agencies),
        distinct_recipients=len(recipients),
        total_grant_value_aud=str(total_grant_value),
        top_agencies=sorted(
            (
                {"agency_name": k, "count": v}
                for k, v in agencies.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )[:20],
        top_recipients=sorted(
            (
                {"recipient_name": k, "count": v}
                for k, v in recipients.items()
            ),
            key=lambda x: x["count"],
            reverse=True,
        )[:20],
    )

    output_summary.parent.mkdir(parents=True, exist_ok=True)
    output_summary.write_text(
        json.dumps(
            {
                "schema_version": summary.schema_version,
                "source_dataset": summary.source_dataset,
                "source_csv_path": summary.source_csv_path,
                "csv_line_count": summary.csv_line_count,
                "record_count": summary.record_count,
                "failed_rows": summary.failed_rows,
                "earliest_publish_date": summary.earliest_publish_date,
                "latest_publish_date": summary.latest_publish_date,
                "distinct_agencies": summary.distinct_agencies,
                "distinct_recipients": summary.distinct_recipients,
                "total_grant_value_aud": summary.total_grant_value_aud,
                "top_agencies": summary.top_agencies,
                "top_recipients": summary.top_recipients,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return summary
