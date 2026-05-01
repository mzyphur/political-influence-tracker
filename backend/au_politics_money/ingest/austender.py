"""AusTender historical contract notice ingestion (Batch X / Y).

This module reads the yearly historical CSV files from data.gov.au's
"Historical Australian Government Contract Notice Data" dataset
(CKAN id ``5c7fa69b-b0e9-4553-b8df-2a022dd2e982``, CC-BY 3.0 AU)
and normalises each contract notice row into a stable JSONL record
plus a per-file summary JSON.

The full schema is documented in this module's docstring rather
than spread across many helpers, so a future loader can read this
file and know exactly what each JSONL record carries without
reverse-engineering. The current scope is **parser only** — the
loader (which lifts these records into ``influence_event`` plus
new ``entity`` rows for suppliers and agencies) lands in a
follow-up batch with its own schema migration.

**What the JSONL records DO carry (per contract notice row):**

- ``contract_id``: the AusTender CN identifier (e.g. ``"CN3350299"``).
  Stable; the natural primary key.
- ``parent_contract_id``: parent CN if this row is an amendment;
  ``None`` for new contracts.
- ``contract_notice_type``: ``"New"``, ``"Amendment"``, or
  ``"SON"`` (Standing Offer Notice).
- ``agency_name``, ``branch``, ``division``: the contracting
  Commonwealth agency / sub-unit.
- ``agency_ref_id``: agency's own internal contract reference
  (free text; not always populated).
- ``office_postcode``: the agency office's postcode.
- ``supplier_name``: contractor / vendor.
- ``supplier_abn``: contractor's ABN (only when ``supplier_abn_exempt``
  is "No"); the natural foreign key into the project's existing
  entity table for cross-source dedup.
- ``supplier_abn_exempt``: ``True`` when the agency claimed an
  ABN-exemption (e.g. for foreign suppliers, individuals).
- ``supplier_address``, ``supplier_suburb``, ``supplier_postcode``,
  ``supplier_state``, ``supplier_country``: contractor location.
- ``contract_value_aud``: the contract's reported value in AUD.
  Numeric. ``None`` when the source field is "NULL" or empty.
- ``amendments_value_aud``: the cumulative amendments value in AUD;
  same NULL semantics as ``contract_value_aud``.
- ``publish_date``, ``amendment_date``, ``start_date``,
  ``amendment_start_date``, ``end_date``: ISO-8601 dates parsed
  from the source's DD/MM/YYYY format. ``None`` when blank.
- ``description``: free-text contract description (the public-facing
  rationale field).
- ``amendment_reason``: free-text reason for amendment when present.
- ``unspsc_code``, ``unspsc_title``: UNSPSC industry classification.
- ``procurement_method``: ``"Open tender"``, ``"Limited tender"``,
  ``"Prequalified tender"``, etc.
- ``atm_id``: linked Approach to Market notice (when published).
- ``son_id``: linked Standing Offer Notice (when published).
- ``panel_arrangement``: panel category, when applicable.
- ``confidentiality_contract_flag`` / ``_reason``: agency claim that
  the contract is confidential under the Senate Order regime.
- ``confidentiality_outputs_flag`` / ``_reason``: agency claim that
  the outputs are confidential.
- ``consultancy_flag`` / ``_reason``: contract is for consultancy
  services (relevant for the "consultancy spending" public-interest
  reporting line).

**What the JSONL records DO NOT carry:**

- Personal-identifying information about supplier contact persons:
  the source CSV's "Contact Name" / "Contact Phone" fields are
  *deliberately* excluded from the normalised JSONL output. Those
  fields are public on the source page but not load-bearing for
  influence analysis, and dropping them at ingestion time keeps
  the JSONL artifact privacy-conservative even though the source
  is technically open.
- Per-contract goods/services beyond UNSPSC: the source publishes
  only the high-level UNSPSC rather than itemised line items.

**Claim-discipline framing.** AusTender contract data documents
public money flowing from a Commonwealth agency to a private
supplier under a procurement procedure. It is **not**:

- A donation, gift, or hospitality received by an MP
- A campaign-support record
- A party-mediated context record

When the loader ships, it will surface these rows under their own
``government_spending`` evidence family with an explicit caveat
that contract awards are not personal MP receipts. The records'
analytical value is cross-referencing supplier ABN against the
existing donor entity table so a public reader can see (e.g.) "this
supplier received $X in Commonwealth contracts AND also appears as
a $Y donor in AEC returns over the same period" — strictly as
labelled, separate-tier evidence with all four families never
summed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from au_politics_money.config import PROCESSED_DIR

# Larger than the default; some "Description" fields run long.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


PARSER_NAME = "austender_contract_notice_csv_normalizer"
PARSER_VERSION = "1"
SOURCE_DATASET = "austender_contract_notices_historical"
SOURCE_TABLE = "austender_contract_notices_historical_csv"
PROCESSED_SUBDIR = "austender_contract_notices_historical"

# Stable schema-version stamp on every JSONL record so downstream
# consumers can branch on parser revisions.
RECORD_SCHEMA_VERSION = "austender_v1"


@dataclass(frozen=True)
class _SourceColumns:
    """Column-name mapping. Captured here so we can adapt to small
    upstream changes (whitespace, capitalisation) without rewriting
    the parser.
    """

    agency_name: str = "Agency Name"
    contract_notice_type: str = "Contract Notice Type"
    parent_contract_id: str = "Parent Contract ID"
    contract_id: str = "Contract ID"
    publish_date: str = "Publish Date"
    amendment_date: str = "Amendment Date"
    start_date: str = "Start Date"
    amendment_start_date: str = "Amendment Start Date"
    end_date: str = "End Date"
    contract_value: str = "Contract Value"
    amendments_value: str = "Amendments Value"
    description: str = "Description"
    amendment_reason: str = "Amendment Reason"
    agency_ref_id: str = "Agency Ref ID"
    unspsc_code: str = "UNSPSC"
    unspsc_title: str = "UNSPSC Title"
    procurement_method: str = "Procurement Method"
    atm_id: str = "ATM ID"
    son_id: str = "SON ID"
    panel_arrangement: str = "Panel Arrangement"
    confidentiality_contract_flag: str = "Confidentiality Contract Flag"
    confidentiality_contract_reason: str = "Confidentiality Contract Reason"
    confidentiality_outputs_flag: str = "Confidentiality Outputs Flag"
    confidentiality_outputs_reason: str = "Confidentiality Outputs Reason"
    consultancy_flag: str = "Consultancy Flag"
    consultancy_reason: str = "Consultancy Reason"
    supplier_name: str = "Supplier Name"
    supplier_address: str = "Supplier Address"
    supplier_suburb: str = "Supplier Suburb"
    supplier_postcode: str = "Supplier Postcode"
    supplier_state: str = "Supplier State"
    supplier_country: str = "Supplier Country"
    supplier_abn_exempt: str = "Supplier ABN Exempt"
    supplier_abn: str = "Supplier ABN"
    branch: str = "Branch"
    division: str = "Division"
    office_postcode: str = "Office Postcode"


_COLS = _SourceColumns()


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clean_text(value: str | None) -> str | None:
    """Normalise whitespace and treat AusTender's literal "NULL"
    string as absent. The source CSV uses the four-character string
    ``NULL`` to mark missing values rather than empty fields.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.upper() == "NULL":
        return None
    return cleaned


def _parse_date(value: str | None) -> str | None:
    """Parse the source's DD/MM/YYYY date strings to ISO-8601.
    Returns ``None`` for blanks, the literal "NULL", or
    unparseable values. The source occasionally publishes
    YYYY-MM-DD style dates in older years; both are accepted.
    """
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    for layout in ("%d/%m/%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(cleaned, layout).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_money(value: str | None) -> str | None:
    """Parse a contract-value string to a string-form Decimal that
    JSONL consumers can re-parse without floating-point loss.
    Returns ``None`` for blanks / the literal "NULL".
    """
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    cleaned = cleaned.replace("$", "").replace(",", "")
    try:
        return str(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        return None


def _parse_bool_flag(value: str | None) -> bool | None:
    """Parse the source's "Yes"/"No" flag fields. Returns ``None``
    for blanks; the AusTender source uses "Yes"/"No" consistently.
    """
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if lowered in {"yes", "y", "true", "1"}:
        return True
    if lowered in {"no", "n", "false", "0"}:
        return False
    return None


def _normalise_abn(value: str | None) -> str | None:
    """Strip whitespace and dots from an ABN. Validates length but
    not check-digit; the loader is responsible for hard ABN
    validation when it ships.
    """
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    digits_only = "".join(ch for ch in cleaned if ch.isdigit())
    if len(digits_only) != 11:
        # AusTender rows occasionally publish a partial / placeholder
        # ABN; preserve the cleaned source-text rather than fabricate
        # one. Loader is responsible for downstream validation.
        return cleaned
    return digits_only


def _normalise_row(row: dict[str, str], *, line_no: int) -> dict[str, Any]:
    contract_id = _clean_text(row.get(_COLS.contract_id))
    publish_date = _parse_date(row.get(_COLS.publish_date))
    amendment_date = _parse_date(row.get(_COLS.amendment_date))
    contract_value = _parse_money(row.get(_COLS.contract_value))
    amendments_value = _parse_money(row.get(_COLS.amendments_value))
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "source_dataset": SOURCE_DATASET,
        "csv_line_no": line_no,
        "contract_id": contract_id,
        "parent_contract_id": _clean_text(row.get(_COLS.parent_contract_id)),
        "contract_notice_type": _clean_text(row.get(_COLS.contract_notice_type)),
        "agency": {
            "name": _clean_text(row.get(_COLS.agency_name)),
            "ref_id": _clean_text(row.get(_COLS.agency_ref_id)),
            "branch": _clean_text(row.get(_COLS.branch)),
            "division": _clean_text(row.get(_COLS.division)),
            "office_postcode": _clean_text(row.get(_COLS.office_postcode)),
        },
        "supplier": {
            "name": _clean_text(row.get(_COLS.supplier_name)),
            "abn": _normalise_abn(row.get(_COLS.supplier_abn)),
            "abn_exempt": _parse_bool_flag(row.get(_COLS.supplier_abn_exempt)),
            "address": _clean_text(row.get(_COLS.supplier_address)),
            "suburb": _clean_text(row.get(_COLS.supplier_suburb)),
            "postcode": _clean_text(row.get(_COLS.supplier_postcode)),
            "state": _clean_text(row.get(_COLS.supplier_state)),
            "country": _clean_text(row.get(_COLS.supplier_country)),
        },
        "contract_value_aud": contract_value,
        "amendments_value_aud": amendments_value,
        "publish_date": publish_date,
        "amendment_date": amendment_date,
        "start_date": _parse_date(row.get(_COLS.start_date)),
        "amendment_start_date": _parse_date(row.get(_COLS.amendment_start_date)),
        "end_date": _parse_date(row.get(_COLS.end_date)),
        "description": _clean_text(row.get(_COLS.description)),
        "amendment_reason": _clean_text(row.get(_COLS.amendment_reason)),
        "unspsc_code": _clean_text(row.get(_COLS.unspsc_code)),
        "unspsc_title": _clean_text(row.get(_COLS.unspsc_title)),
        "procurement_method": _clean_text(row.get(_COLS.procurement_method)),
        "atm_id": _clean_text(row.get(_COLS.atm_id)),
        "son_id": _clean_text(row.get(_COLS.son_id)),
        "panel_arrangement": _clean_text(row.get(_COLS.panel_arrangement)),
        "confidentiality_contract_flag": _parse_bool_flag(
            row.get(_COLS.confidentiality_contract_flag)
        ),
        "confidentiality_contract_reason": _clean_text(
            row.get(_COLS.confidentiality_contract_reason)
        ),
        "confidentiality_outputs_flag": _parse_bool_flag(
            row.get(_COLS.confidentiality_outputs_flag)
        ),
        "confidentiality_outputs_reason": _clean_text(
            row.get(_COLS.confidentiality_outputs_reason)
        ),
        "consultancy_flag": _parse_bool_flag(row.get(_COLS.consultancy_flag)),
        "consultancy_reason": _clean_text(row.get(_COLS.consultancy_reason)),
    }


def normalise_csv(
    csv_path: Path,
    *,
    output_dir: Path | None = None,
    fiscal_year_label: str | None = None,
) -> Path:
    """Read an AusTender historical CSV and produce a JSONL file +
    a summary JSON next to it. Returns the path to the JSONL file.

    The summary JSON captures aggregate statistics suitable for
    embedding in dashboards or in the project's `/api/coverage`
    endpoint when the loader ships:

    * total contract notice rows
    * total reported value (AUD, summed across all rows with a
      non-null Contract Value)
    * row counts by Contract Notice Type (New / Amendment / SON)
    * top 20 agencies by row count and by reported value
    * top 20 suppliers by row count and by reported value
    * UNSPSC industry distribution (top 20 codes)
    * confidentiality / consultancy flag rates
    * publish-date span and date-coverage gaps
    """
    output_dir = output_dir or (PROCESSED_DIR / PROCESSED_SUBDIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _timestamp()
    jsonl_path = output_dir / f"{timestamp}.jsonl"
    summary_path = output_dir / f"{timestamp}.summary.json"

    row_count = 0
    type_counter: Counter[str] = Counter()
    agency_row_counter: Counter[str] = Counter()
    supplier_row_counter: Counter[str] = Counter()
    supplier_value_totals: dict[str, Decimal] = {}
    agency_value_totals: dict[str, Decimal] = {}
    unspsc_counter: Counter[str] = Counter()
    procurement_method_counter: Counter[str] = Counter()
    consultancy_yes = 0
    confidentiality_contract_yes = 0
    confidentiality_outputs_yes = 0
    abn_exempt_yes = 0
    rows_with_value = 0
    rows_with_publish_date = 0
    total_value = Decimal("0")
    earliest_publish: str | None = None
    latest_publish: str | None = None

    csv_sha256 = _sha256_of(csv_path)
    csv_size_bytes = csv_path.stat().st_size

    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        with jsonl_path.open("w", encoding="utf-8") as out:
            for line_no, row in enumerate(reader, start=2):
                normalised = _normalise_row(row, line_no=line_no)
                out.write(json.dumps(normalised, ensure_ascii=False))
                out.write("\n")

                row_count += 1
                cn_type = normalised["contract_notice_type"] or "Unknown"
                type_counter[cn_type] += 1
                agency_name = normalised["agency"]["name"]
                supplier_name = normalised["supplier"]["name"]
                if agency_name:
                    agency_row_counter[agency_name] += 1
                if supplier_name:
                    supplier_row_counter[supplier_name] += 1
                value_str = normalised["contract_value_aud"]
                if value_str is not None:
                    try:
                        value = Decimal(value_str)
                    except InvalidOperation:
                        value = None
                    if value is not None:
                        rows_with_value += 1
                        total_value += value
                        if agency_name:
                            agency_value_totals[agency_name] = (
                                agency_value_totals.get(agency_name, Decimal("0"))
                                + value
                            )
                        if supplier_name:
                            supplier_value_totals[supplier_name] = (
                                supplier_value_totals.get(
                                    supplier_name, Decimal("0")
                                )
                                + value
                            )
                publish_date = normalised["publish_date"]
                if publish_date:
                    rows_with_publish_date += 1
                    if earliest_publish is None or publish_date < earliest_publish:
                        earliest_publish = publish_date
                    if latest_publish is None or publish_date > latest_publish:
                        latest_publish = publish_date
                unspsc = normalised["unspsc_title"]
                if unspsc:
                    unspsc_counter[unspsc] += 1
                proc = normalised["procurement_method"]
                if proc:
                    procurement_method_counter[proc] += 1
                if normalised["consultancy_flag"] is True:
                    consultancy_yes += 1
                if normalised["confidentiality_contract_flag"] is True:
                    confidentiality_contract_yes += 1
                if normalised["confidentiality_outputs_flag"] is True:
                    confidentiality_outputs_yes += 1
                if normalised["supplier"]["abn_exempt"] is True:
                    abn_exempt_yes += 1

    summary: dict[str, Any] = {
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "schema_version": RECORD_SCHEMA_VERSION,
        "generated_at": timestamp,
        "source_dataset": SOURCE_DATASET,
        "fiscal_year_label": fiscal_year_label,
        "input_csv_path": str(csv_path),
        "input_csv_size_bytes": csv_size_bytes,
        "input_csv_sha256": csv_sha256,
        "jsonl_path": str(jsonl_path),
        "row_count": row_count,
        "rows_with_contract_value": rows_with_value,
        "rows_with_publish_date": rows_with_publish_date,
        "total_reported_value_aud": str(total_value),
        "publish_date_span": {
            "earliest": earliest_publish,
            "latest": latest_publish,
        },
        "contract_notice_type_counts": dict(type_counter),
        "procurement_method_counts": dict(procurement_method_counter),
        "consultancy_flag_yes_count": consultancy_yes,
        "confidentiality_contract_flag_yes_count": confidentiality_contract_yes,
        "confidentiality_outputs_flag_yes_count": confidentiality_outputs_yes,
        "supplier_abn_exempt_yes_count": abn_exempt_yes,
        "top_agencies_by_row_count": _top_n(agency_row_counter, 20),
        "top_agencies_by_value_aud": _top_n_decimal(agency_value_totals, 20),
        "top_suppliers_by_row_count": _top_n(supplier_row_counter, 20),
        "top_suppliers_by_value_aud": _top_n_decimal(supplier_value_totals, 20),
        "top_unspsc_titles_by_row_count": _top_n(unspsc_counter, 20),
        "claim_discipline_caveat": (
            "AusTender contract notice records document public money "
            "flowing from a Commonwealth agency to a private supplier "
            "under a procurement procedure. They are NOT a donation, "
            "gift, hospitality, campaign-support record, or party-"
            "mediated context record. The project's loader will "
            "surface these rows under their own government_spending "
            "evidence family with explicit caveats; no cross-family "
            "summing."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonl_path


def _top_n(counter: Counter[str], n: int) -> list[dict[str, Any]]:
    return [
        {"key": key, "count": count}
        for key, count in counter.most_common(n)
    ]


def _top_n_decimal(
    totals: dict[str, Decimal], n: int
) -> list[dict[str, Any]]:
    return [
        {"key": key, "total_aud": str(value)}
        for key, value in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]
    ]


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_archive_dir(archive_dir: Path) -> Path:
    """Convenience: take a `data/raw/<source>/<timestamp>/` directory
    that has a ``resource.csv`` file (as written by
    ``scripts/fetch_data_gov_au_resource.sh``) and run ``normalise_csv``
    against it.
    """
    csv_path = archive_dir / "resource.csv"
    if not csv_path.exists():
        raise FileNotFoundError(
            f"AusTender archive directory missing resource.csv: {archive_dir}"
        )
    metadata_path = archive_dir / "metadata.json"
    fiscal_year_label: str | None = None
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as fh:
            metadata = json.load(fh)
        fiscal_year_label = metadata.get("resource_name")
    return normalise_csv(csv_path, fiscal_year_label=fiscal_year_label)


__all__: Iterable[str] = (
    "normalise_csv",
    "normalise_archive_dir",
    "PARSER_NAME",
    "PARSER_VERSION",
    "RECORD_SCHEMA_VERSION",
    "SOURCE_DATASET",
)
