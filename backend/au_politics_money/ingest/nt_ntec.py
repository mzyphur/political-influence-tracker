from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.official_identifiers import normalize_name
from au_politics_money.ingest.sources import get_source

SOURCE_DATASET = "nt_ntec_annual_returns_gifts"
ANNUAL_GIFTS_SOURCE_ID = "nt_ntec_annual_returns_gifts_2024_2025"
PARSER_NAME = "nt_ntec_annual_gift_html_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "nt_ntec_annual_returns_gifts_2024_2025_html"
FINANCIAL_YEAR = "2024-2025"
FLOW_KIND = "nt_annual_gift"
EXPECTED_GIFT_HEADERS = ("received from", "address", "amount")
GIFT_RETURN_CAVEAT = (
    "Official NTEC 2024-2025 annual gift-return page. Rows disclose gifts "
    "received over the threshold in the annual disclosure period. Amounts are "
    "source-backed donor-to-recipient gift observations, not allegations of "
    "wrongdoing, causation, quid pro quo, or improper influence. The NTEC source "
    "does not provide per-row gift dates in these recipient-side tables; the "
    "reported date is the return received date where available."
)
ANNUAL_RETURNS_SOURCE_DATASET = "nt_ntec_annual_returns"
ANNUAL_RETURNS_SOURCE_ID = "nt_ntec_annual_returns_2024_2025"
ANNUAL_RETURNS_PARSER_NAME = "nt_ntec_annual_return_financial_html_normalizer"
ANNUAL_RETURNS_SOURCE_TABLE = "nt_ntec_annual_returns_2024_2025_html"
ANNUAL_RECEIPT_FLOW_KIND = "nt_annual_receipt"
ANNUAL_DEBT_FLOW_KIND = "nt_annual_debt"
DONOR_RETURN_DONATION_FLOW_KIND = "nt_donor_return_donation"
EXPECTED_RECEIPT_HEADERS = ("received from", "address", "receipt type", "amount")
EXPECTED_DEBT_HEADERS = ("name", "address", "amount")
EXPECTED_DONOR_RETURN_HEADERS = ("name", "date", "amount")
ANNUAL_RETURN_CAVEAT = (
    "Official NTEC 2024-2025 annual return page. Rows disclose recipient-side "
    "receipts and debts over $1,500, plus donor-side annual donation return "
    "tables. Amounts are source-backed disclosure observations, not allegations "
    "of wrongdoing, causation, quid pro quo, or improper influence. These rows "
    "can overlap with NTEC annual gift-return rows, donor-side returns, or "
    "Commonwealth disclosure records, so they are visible as NT state/local "
    "source records but excluded from consolidated reported amount totals until "
    "cross-source deduplication exists."
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted((raw_dir / source_id).glob("*/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No metadata found for source {source_id}")
    return candidates[0]


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _normalize_header(value: str) -> str:
    return _clean_text(normalize_name(value).replace("-", " "))


def _money_string(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        raise ValueError("Missing NTEC annual gift amount")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse NTEC annual gift amount: {value!r}") from exc
    return str(-amount if negative else amount)


def _date_string(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse NTEC date: {value!r}")


def _cells(row: Tag) -> list[str]:
    return [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]


def _previous_heading(table: Tag) -> str:
    heading = table.find_previous(["h2", "h3", "h4"])
    return _clean_text(heading.get_text(" ", strip=True)) if isinstance(heading, Tag) else ""


def _recipient_from_heading(heading: str) -> str:
    match = re.match(
        r"^(.+?)\s+-\s+Gifts received over the threshold in the disclosure period$",
        heading,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unexpected NTEC annual gift heading: {heading!r}")
    return _clean_text(match.group(1))


def _subject_from_heading(heading: str, suffix: str) -> str:
    match = re.match(
        rf"^(.+?)\s+[-–]\s+{re.escape(suffix)}$",
        heading,
        flags=re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Unexpected NTEC annual return heading: {heading!r}")
    return _clean_text(match.group(1))


def _date_or_period(value: str) -> tuple[str, str, str]:
    cleaned = _clean_text(value)
    if not cleaned:
        return "", "", "Date not published in the NTEC source table."
    if re.fullmatch(r"\d{4}\s*[/–-]\s*\d{4}", cleaned):
        return "", cleaned, f"NTEC source reports annual period {cleaned}, not a date."
    return _date_string(cleaned), "", ""


def _return_received_dates(soup: BeautifulSoup) -> dict[str, str]:
    dates: dict[str, str] = {}
    for table in soup.find_all("table"):
        rows = [_cells(row) for row in table.find_all("tr")]
        if not rows:
            continue
        headers = tuple(_normalize_header(cell) for cell in rows[0])
        if headers not in {
            ("name", "date received"),
            ("electorate", "name", "party", "date received"),
        }:
            continue
        for row in rows[1:]:
            if len(row) == 2:
                name, received = row
            elif len(row) >= 4:
                name, received = row[1], row[3]
            else:
                continue
            if normalize_name(name) == "totals":
                continue
            if name and received:
                dates[normalize_name(name)] = _date_string(received)
    return dates


def _last_updated(soup: BeautifulSoup) -> str:
    text = soup.get_text("\n", strip=True)
    match = re.search(r"Last updated:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", text)
    return _date_string(match.group(1)) if match else ""


def _gift_tables(soup: BeautifulSoup) -> list[tuple[int, str, Tag]]:
    tables: list[tuple[int, str, Tag]] = []
    for table_index, table in enumerate(soup.find_all("table"), start=1):
        heading = _previous_heading(table)
        if "gifts received over the threshold in the disclosure period" not in heading.casefold():
            continue
        rows = [_cells(row) for row in table.find_all("tr")]
        if not rows:
            continue
        headers = tuple(_normalize_header(cell) for cell in rows[0])
        if headers[:3] != EXPECTED_GIFT_HEADERS:
            raise ValueError(
                f"Unexpected NTEC annual gift headers for {heading!r}: {headers!r}"
            )
        tables.append((table_index, _recipient_from_heading(heading), table))
    if not tables:
        raise ValueError("No NTEC annual gift recipient tables found")
    return tables


def _records_from_body(
    *,
    body: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    return_dates = _return_received_dates(soup)
    last_updated = _last_updated(soup)
    records: list[dict[str, Any]] = []
    for table_index, recipient, table in _gift_tables(soup):
        rows = [_cells(row) for row in table.find_all("tr")]
        recipient_key = normalize_name(recipient)
        date_reported = return_dates.get(recipient_key, "")
        table_records: list[dict[str, Any]] = []
        table_amount_total = Decimal("0")
        source_table_total: Decimal | None = None
        for row_index, row in enumerate(rows[1:], start=2):
            if len(row) < 3:
                raise ValueError(
                    f"NTEC annual gift row for {recipient} has {len(row)} cells, expected 3"
                )
            donor, address, amount = row[:3]
            if normalize_name(donor) in {"total", "totals"}:
                source_table_total = Decimal(_money_string(amount))
                continue
            if not donor:
                raise ValueError(f"NTEC annual gift row {table_index}:{row_index} has no donor")
            amount_aud = _money_string(amount)
            table_amount_total += Decimal(amount_aud)
            source_row_number = f"t{table_index}:r{row_index}:{hashlib.sha1(donor.encode('utf-8')).hexdigest()[:8]}"
            table_records.append(
                {
                    "schema_version": "nt_ntec_annual_gift_money_flow_v1",
                    "source_dataset": SOURCE_DATASET,
                    "source_id": ANNUAL_GIFTS_SOURCE_ID,
                    "source_table": SOURCE_TABLE,
                    "source_row_number": source_row_number,
                    "normalizer_name": PARSER_NAME,
                    "normalizer_version": PARSER_VERSION,
                    "jurisdiction_name": "Northern Territory",
                    "jurisdiction_level": "state",
                    "jurisdiction_code": "NT",
                    "financial_year": FINANCIAL_YEAR,
                    "return_type": "NTEC annual gift return",
                    "flow_kind": FLOW_KIND,
                    "receipt_type": "Gift received over threshold",
                    "disclosure_category": FLOW_KIND,
                    "transaction_kind": "gift",
                    "source_raw_name": donor,
                    "recipient_raw_name": recipient,
                    "amount_aud": amount_aud,
                    "currency": "AUD",
                    "date": "",
                    "date_reported": date_reported,
                    "description": (
                        f"NTEC annual gift over threshold from {donor} to {recipient}; "
                        "per-row gift date not published in this table."
                    ),
                    "donor_address_public": address,
                    "doc_last_updated": last_updated,
                    "date_caveat": (
                        "NTEC return received date, not gift transaction date."
                        if date_reported
                        else "Per-row gift date not published by the NTEC source table."
                    ),
                    "public_amount_counting_role": (
                        "jurisdictional_cross_disclosure_observation"
                    ),
                    "cross_source_dedupe_status": (
                        "not_deduplicated_against_commonwealth_or_donor_returns"
                    ),
                    "amount_counting_caveat": (
                        "Use in NT state/local source-family totals. Do not include "
                        "in consolidated reported money totals until cross-source "
                        "deduplication against Commonwealth and donor-side returns "
                        "has been completed."
                    ),
                    "disclosure_system": "nt_ntec_financial_disclosure",
                    "disclosure_threshold": (
                        "NTEC annual gift-return threshold: gifts received over the "
                        "threshold in the annual disclosure period; current source "
                        "page labels the detailed tables as over-threshold gifts."
                    ),
                    "evidence_status": "official_record_parsed",
                    "claim_boundary": GIFT_RETURN_CAVEAT,
                    "caveat": GIFT_RETURN_CAVEAT,
                    "source_metadata_path": str(source_metadata_path),
                    "source_metadata_sha256": source_metadata_sha256,
                    "source_body_path": str(source_body_path),
                    "source_body_sha256": source_body_sha256,
                    "original": {
                        "recipient": recipient,
                        "received_from": donor,
                        "address": address,
                        "amount": amount,
                        "table_index": table_index,
                        "row_index": row_index,
                    },
                }
            )
        if source_table_total is not None and table_amount_total != source_table_total:
            raise ValueError(
                "NTEC annual gift table total mismatch for "
                f"{recipient}: rows={table_amount_total} source_total={source_table_total}"
            )
        for record in table_records:
            record["source_table_total_validated"] = source_table_total is not None
            if source_table_total is not None:
                record["source_table_total_aud"] = str(source_table_total)
        records.extend(table_records)
    if not records:
        raise ValueError("No NTEC annual gift rows extracted")
    return records


def _annual_return_records_from_body(
    *,
    body: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    return_dates = _return_received_dates(soup)
    last_updated = _last_updated(soup)
    records: list[dict[str, Any]] = []
    for table_index, table in enumerate(soup.find_all("table"), start=1):
        heading = _previous_heading(table)
        heading_lower = heading.casefold()
        rows = [_cells(row) for row in table.find_all("tr")]
        if not rows:
            continue
        headers = tuple(_normalize_header(cell) for cell in rows[0])
        if "receipts of $1500 or more" in heading_lower:
            if headers[:4] != EXPECTED_RECEIPT_HEADERS:
                raise ValueError(f"Unexpected NTEC annual receipt headers: {headers!r}")
            recipient = _subject_from_heading(heading, "Receipts of $1500 or more")
            records.extend(
                _records_from_annual_amount_table(
                    rows=rows,
                    table_index=table_index,
                    source_subject_role="received_from",
                    recipient=recipient,
                    flow_kind=ANNUAL_RECEIPT_FLOW_KIND,
                    receipt_type="Receipt over $1,500",
                    transaction_kind="receipt",
                    return_type="NTEC annual return receipt table",
                    source_metadata_path=source_metadata_path,
                    source_body_path=source_body_path,
                    source_metadata_sha256=source_metadata_sha256,
                    source_body_sha256=source_body_sha256,
                    date_reported=return_dates.get(normalize_name(recipient), ""),
                    last_updated=last_updated,
                )
            )
        elif "debts of $1500 or more" in heading_lower:
            if headers[:3] != EXPECTED_DEBT_HEADERS:
                raise ValueError(f"Unexpected NTEC annual debt headers: {headers!r}")
            recipient = _subject_from_heading(heading, "Debts of $1500 or more")
            records.extend(
                _records_from_annual_amount_table(
                    rows=rows,
                    table_index=table_index,
                    source_subject_role="creditor",
                    recipient=recipient,
                    flow_kind=ANNUAL_DEBT_FLOW_KIND,
                    receipt_type="Debt over $1,500",
                    transaction_kind="debt",
                    return_type="NTEC annual return debt table",
                    source_metadata_path=source_metadata_path,
                    source_body_path=source_body_path,
                    source_metadata_sha256=source_metadata_sha256,
                    source_body_sha256=source_body_sha256,
                    date_reported=return_dates.get(normalize_name(recipient), ""),
                    last_updated=last_updated,
                )
            )
        elif "donations made to political parties and candidates" in heading_lower:
            if headers[:3] != EXPECTED_DONOR_RETURN_HEADERS:
                raise ValueError(f"Unexpected NTEC donor return headers: {headers!r}")
            donor = _subject_from_heading(
                heading,
                "Donations made to political parties and candidates",
            )
            records.extend(
                _records_from_donor_return_table(
                    rows=rows,
                    table_index=table_index,
                    donor=donor,
                    source_metadata_path=source_metadata_path,
                    source_body_path=source_body_path,
                    source_metadata_sha256=source_metadata_sha256,
                    source_body_sha256=source_body_sha256,
                    last_updated=last_updated,
                )
            )
    if not records:
        raise ValueError("No NTEC annual return financial rows extracted")
    return records


def _base_annual_record(
    *,
    flow_kind: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
    last_updated: str,
) -> dict[str, Any]:
    return {
        "schema_version": "nt_ntec_annual_return_money_flow_v1",
        "source_dataset": ANNUAL_RETURNS_SOURCE_DATASET,
        "source_id": ANNUAL_RETURNS_SOURCE_ID,
        "source_table": ANNUAL_RETURNS_SOURCE_TABLE,
        "normalizer_name": ANNUAL_RETURNS_PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "jurisdiction_name": "Northern Territory",
        "jurisdiction_level": "state",
        "jurisdiction_code": "NT",
        "financial_year": FINANCIAL_YEAR,
        "flow_kind": flow_kind,
        "disclosure_category": flow_kind,
        "currency": "AUD",
        "doc_last_updated": last_updated,
        "public_amount_counting_role": "jurisdictional_cross_disclosure_observation",
        "cross_source_dedupe_status": (
            "not_deduplicated_against_ntec_gift_or_commonwealth_returns"
        ),
        "amount_counting_caveat": (
            "Use in NT state/local source-row displays. Do not include in "
            "consolidated reported money totals until cross-source deduplication "
            "against NTEC gift tables, donor-side returns, and Commonwealth returns "
            "has been completed."
        ),
        "disclosure_system": "nt_ntec_financial_disclosure",
        "evidence_status": "official_record_parsed",
        "claim_boundary": ANNUAL_RETURN_CAVEAT,
        "caveat": ANNUAL_RETURN_CAVEAT,
        "source_metadata_path": str(source_metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
    }


def _records_from_annual_amount_table(
    *,
    rows: list[list[str]],
    table_index: int,
    source_subject_role: str,
    recipient: str,
    flow_kind: str,
    receipt_type: str,
    transaction_kind: str,
    return_type: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
    date_reported: str,
    last_updated: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    table_amount_total = Decimal("0")
    source_table_total: Decimal | None = None
    for row_index, row in enumerate(rows[1:], start=2):
        if len(row) < 3:
            raise ValueError(f"NTEC annual return row {table_index}:{row_index} is too short")
        source_name, address = row[0], row[1]
        row_receipt_type = row[2] if len(row) >= 4 else receipt_type
        amount = row[3] if len(row) >= 4 else row[2]
        if normalize_name(source_name) in {"total", "totals"}:
            source_table_total = Decimal(_money_string(amount))
            continue
        amount_aud = _money_string(amount)
        table_amount_total += Decimal(amount_aud)
        source_row_number = (
            f"t{table_index}:r{row_index}:"
            f"{hashlib.sha1(source_name.encode('utf-8')).hexdigest()[:8]}"
        )
        record = _base_annual_record(
            flow_kind=flow_kind,
            source_metadata_path=source_metadata_path,
            source_body_path=source_body_path,
            source_metadata_sha256=source_metadata_sha256,
            source_body_sha256=source_body_sha256,
            last_updated=last_updated,
        )
        record.update(
            {
                "source_row_number": source_row_number,
                "return_type": return_type,
                "receipt_type": row_receipt_type or receipt_type,
                "transaction_kind": transaction_kind,
                "source_raw_name": source_name,
                "recipient_raw_name": recipient,
                "amount_aud": amount_aud,
                "date": "",
                "date_reported": date_reported,
                "date_caveat": (
                    "NTEC return received date, not transaction date."
                    if date_reported
                    else "Transaction date not published by the NTEC source table."
                ),
                "description": (
                    f"NTEC annual return {transaction_kind} from {source_name} "
                    f"to {recipient}; exact transaction date not published in this table."
                ),
                "counterparty_address_public": address,
                "original": {
                    "recipient": recipient,
                    source_subject_role: source_name,
                    "address": address,
                    "receipt_type": row_receipt_type,
                    "amount": amount,
                    "table_index": table_index,
                    "row_index": row_index,
                },
            }
        )
        records.append(record)
    _validate_table_total(records, table_amount_total, source_table_total, recipient)
    return records


def _records_from_donor_return_table(
    *,
    rows: list[list[str]],
    table_index: int,
    donor: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
    last_updated: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    table_amount_total = Decimal("0")
    source_table_total: Decimal | None = None
    for row_index, row in enumerate(rows[1:], start=2):
        if len(row) < 3:
            raise ValueError(f"NTEC donor return row {table_index}:{row_index} is too short")
        recipient, date_value, amount = row[:3]
        if normalize_name(recipient) in {"total", "totals"}:
            source_table_total = Decimal(_money_string(amount))
            continue
        amount_aud = _money_string(amount)
        table_amount_total += Decimal(amount_aud)
        date_received, reporting_period, date_caveat = _date_or_period(date_value)
        source_row_number = (
            f"t{table_index}:r{row_index}:"
            f"{hashlib.sha1(recipient.encode('utf-8')).hexdigest()[:8]}"
        )
        record = _base_annual_record(
            flow_kind=DONOR_RETURN_DONATION_FLOW_KIND,
            source_metadata_path=source_metadata_path,
            source_body_path=source_body_path,
            source_metadata_sha256=source_metadata_sha256,
            source_body_sha256=source_body_sha256,
            last_updated=last_updated,
        )
        record.update(
            {
                "source_row_number": source_row_number,
                "return_type": "NTEC donor annual return donation table",
                "receipt_type": "Donation made",
                "transaction_kind": "donation",
                "source_raw_name": donor,
                "recipient_raw_name": recipient,
                "amount_aud": amount_aud,
                "date": date_received,
                "date_caveat": date_caveat,
                "reporting_period": reporting_period or FINANCIAL_YEAR,
                "description": (
                    f"NTEC donor annual return donation from {donor} to {recipient}."
                ),
                "original": {
                    "donor": donor,
                    "recipient": recipient,
                    "date": date_value,
                    "amount": amount,
                    "table_index": table_index,
                    "row_index": row_index,
                },
            }
        )
        records.append(record)
    _validate_table_total(records, table_amount_total, source_table_total, donor)
    return records


def _validate_table_total(
    records: list[dict[str, Any]],
    table_amount_total: Decimal,
    source_table_total: Decimal | None,
    label: str,
) -> None:
    if source_table_total is None:
        raise ValueError(f"NTEC annual return table total missing for {label}")
    if source_table_total is not None and table_amount_total != source_table_total:
        raise ValueError(
            "NTEC annual return table total mismatch for "
            f"{label}: rows={table_amount_total} source_total={source_table_total}"
        )
    for record in records:
        record["source_table_total_validated"] = True
        record["source_table_total_aud"] = str(source_table_total)


def normalize_nt_ntec_annual_gifts(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        try:
            metadata_path = _latest_metadata(ANNUAL_GIFTS_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            metadata_path = fetch_source(get_source(ANNUAL_GIFTS_SOURCE_ID), raw_dir=raw_dir)

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != ANNUAL_GIFTS_SOURCE_ID:
        raise ValueError(
            f"Expected {ANNUAL_GIFTS_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"NTEC annual gift body hash mismatch: metadata={metadata['sha256']} "
            f"actual={source_body_sha256}"
        )
    body = source_body_path.read_text(encoding="utf-8", errors="replace")
    records = _records_from_body(
        body=body,
        source_metadata_path=metadata_path,
        source_body_path=source_body_path,
        source_metadata_sha256=source_metadata_sha256,
        source_body_sha256=source_body_sha256,
    )

    timestamp = _timestamp()
    target_dir = processed_dir / "nt_ntec_annual_gift_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"
    amount_total = Decimal("0")
    flow_counts: Counter[str] = Counter()
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            amount_total += Decimal(str(record["amount_aud"]))
            flow_counts[str(record["flow_kind"])] += 1
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_metadata_path": str(metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "source_id": ANNUAL_GIFTS_SOURCE_ID,
        "source_dataset": SOURCE_DATASET,
        "source_counts": {ANNUAL_GIFTS_SOURCE_ID: len(records)},
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "nt_ntec_annual_gift_money_flow_v1",
        "claim_boundary": GIFT_RETURN_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def normalize_nt_ntec_annual_returns(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        try:
            metadata_path = _latest_metadata(ANNUAL_RETURNS_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            metadata_path = fetch_source(get_source(ANNUAL_RETURNS_SOURCE_ID), raw_dir=raw_dir)

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != ANNUAL_RETURNS_SOURCE_ID:
        raise ValueError(
            f"Expected {ANNUAL_RETURNS_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"NTEC annual return body hash mismatch: metadata={metadata['sha256']} "
            f"actual={source_body_sha256}"
        )
    body = source_body_path.read_text(encoding="utf-8", errors="replace")
    records = _annual_return_records_from_body(
        body=body,
        source_metadata_path=metadata_path,
        source_body_path=source_body_path,
        source_metadata_sha256=source_metadata_sha256,
        source_body_sha256=source_body_sha256,
    )

    timestamp = _timestamp()
    target_dir = processed_dir / "nt_ntec_annual_return_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"
    amount_total = Decimal("0")
    flow_counts: Counter[str] = Counter()
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            amount_total += Decimal(str(record["amount_aud"]))
            flow_counts[str(record["flow_kind"])] += 1
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_metadata_path": str(metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "source_id": ANNUAL_RETURNS_SOURCE_ID,
        "source_dataset": ANNUAL_RETURNS_SOURCE_DATASET,
        "source_counts": {ANNUAL_RETURNS_SOURCE_ID: len(records)},
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": ANNUAL_RETURNS_PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "nt_ntec_annual_return_money_flow_v1",
        "claim_boundary": ANNUAL_RETURN_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
