from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from au_politics_money.config import PROCESSED_DIR, RAW_DIR


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted((raw_dir / source_id).glob("*/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No metadata found for source {source_id}")
    return candidates[0]


def _read_csv_summary(zip_file: zipfile.ZipFile, name: str, sample_size: int) -> dict[str, object]:
    with zip_file.open(name) as raw_handle:
        text_handle = io.TextIOWrapper(raw_handle, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_handle)
        columns = list(reader.fieldnames or [])
        sample_rows = []
        row_count = 0
        for row in reader:
            row_count += 1
            if len(sample_rows) < sample_size:
                sample_rows.append({key: (value or "") for key, value in row.items()})

    return {
        "file_name": name,
        "columns": columns,
        "column_count": len(columns),
        "row_count": row_count,
        "sample_rows": sample_rows,
    }


def parse_money(value: str) -> str:
    cleaned = (value or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return ""
    try:
        return str(Decimal(cleaned))
    except InvalidOperation:
        return ""


def _iter_zip_csv_rows(
    zip_file: zipfile.ZipFile,
    name: str,
) -> tuple[int, dict[str, str]]:
    with zip_file.open(name) as raw_handle:
        text_handle = io.TextIOWrapper(raw_handle, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_handle)
        for row_number, row in enumerate(reader, start=2):
            yield row_number, {key: (value or "").strip() for key, value in row.items()}


def _normalize_detailed_receipts(row_number: int, row: dict[str, str]) -> dict[str, str]:
    return {
        "source_table": "Detailed Receipts.csv",
        "source_row_number": str(row_number),
        "flow_kind": "detailed_receipt",
        "financial_year": row.get("Financial Year", ""),
        "return_type": row.get("Return Type", ""),
        "source_raw_name": row.get("Received From", ""),
        "recipient_raw_name": row.get("Recipient Name", ""),
        "receipt_type": row.get("Receipt Type", ""),
        "date": "",
        "amount_aud": parse_money(row.get("Value", "")),
        "original": row,
    }


def _normalize_donations_made(row_number: int, row: dict[str, str]) -> dict[str, str]:
    return {
        "source_table": "Donations Made.csv",
        "source_row_number": str(row_number),
        "flow_kind": "donation_made",
        "financial_year": row.get("Financial Year", ""),
        "return_type": "Annual Donor",
        "source_raw_name": row.get("Donor Name", ""),
        "recipient_raw_name": row.get("Donation Made To", ""),
        "receipt_type": "Donation Made",
        "date": row.get("Date", ""),
        "amount_aud": parse_money(row.get("Value", "")),
        "original": row,
    }


def _normalize_donor_donations_received(row_number: int, row: dict[str, str]) -> dict[str, str]:
    return {
        "source_table": "Donor Donations Received.csv",
        "source_row_number": str(row_number),
        "flow_kind": "donor_donation_received",
        "financial_year": row.get("Financial Year", ""),
        "return_type": "Annual Donor",
        "source_raw_name": row.get("Donation Received From", ""),
        "recipient_raw_name": row.get("Name", ""),
        "receipt_type": "Donation Received",
        "date": row.get("Date", ""),
        "amount_aud": parse_money(row.get("Value", "")),
        "original": row,
    }


def _normalize_third_party_donations_received(row_number: int, row: dict[str, str]) -> dict[str, str]:
    return {
        "source_table": "Third Party Donations Received.csv",
        "source_row_number": str(row_number),
        "flow_kind": "third_party_donation_received",
        "financial_year": row.get("Financial Year", ""),
        "return_type": "Third Party",
        "source_raw_name": row.get("Donation Received From", ""),
        "recipient_raw_name": row.get("Name", ""),
        "receipt_type": "Donation Received",
        "date": row.get("Date", ""),
        "amount_aud": parse_money(row.get("Value", "")),
        "original": row,
    }


def summarize_aec_annual_zip(
    source_id: str = "aec_download_all_annual_data",
    sample_size: int = 3,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])

    with zipfile.ZipFile(zip_path) as zip_file:
        table_summaries = [
            _read_csv_summary(zip_file, name, sample_size)
            for name in sorted(zip_file.namelist())
            if name.lower().endswith(".csv")
        ]

    timestamp = _timestamp()
    target_dir = processed_dir / "aec_annual"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}.schema_summary.json"
    payload = {
        "generated_at": timestamp,
        "source_metadata_path": str(metadata_path),
        "zip_path": str(zip_path),
        "table_count": len(table_summaries),
        "tables": table_summaries,
    }
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path


def normalize_aec_annual_money_flows(
    source_id: str = "aec_download_all_annual_data",
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])

    normalizers = {
        "Detailed Receipts.csv": _normalize_detailed_receipts,
        "Donations Made.csv": _normalize_donations_made,
        "Donor Donations Received.csv": _normalize_donor_donations_received,
        "Third Party Donations Received.csv": _normalize_third_party_donations_received,
    }

    timestamp = _timestamp()
    target_dir = processed_dir / "aec_annual_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    table_counts = {name: 0 for name in normalizers}
    total_count = 0
    missing_amount_count = 0
    with zipfile.ZipFile(zip_path) as zip_file, jsonl_path.open("w", encoding="utf-8") as handle:
        for name, normalizer in normalizers.items():
            if name not in zip_file.namelist():
                continue
            for row_number, row in _iter_zip_csv_rows(zip_file, name):
                record = normalizer(row_number, row)
                record["source_metadata_path"] = str(metadata_path)
                record["source_zip_path"] = str(zip_path)
                if not record["amount_aud"]:
                    missing_amount_count += 1
                table_counts[name] += 1
                total_count += 1
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_metadata_path": str(metadata_path),
        "source_zip_path": str(zip_path),
        "jsonl_path": str(jsonl_path),
        "total_count": total_count,
        "missing_amount_count": missing_amount_count,
        "table_counts": table_counts,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
