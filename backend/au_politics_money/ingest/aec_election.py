from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.aec_annual import (
    _latest_metadata,
    _read_csv_summary,
    _timestamp,
    parse_money,
)

PARSER_NAME = "aec_election_money_flow_normalizer"
PARSER_VERSION = "1"
SOURCE_DATASET = "aec_election"

PRIMARY_OBSERVATION_TABLE_PRIORITY = {
    "Senate Groups and Candidate Donations.csv": 10,
    "Third Party Return Donations Received.csv": 20,
    "Donor Donations Received.csv": 30,
    "Senate Groups and Candidate Discretionary Benefits.csv": 40,
    "Donor Donations Made.csv": 50,
    "Third Party Return Donations Made.csv": 60,
    "Media Advertisement Details.csv": 70,
}


def _iter_zip_csv_rows(
    zip_file: zipfile.ZipFile,
    name: str,
) -> tuple[int, dict[str, str]]:
    with zip_file.open(name) as raw_handle:
        text_handle = io.TextIOWrapper(raw_handle, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_handle)
        for row_number, row in enumerate(reader, start=2):
            yield row_number, {key: (value or "").strip() for key, value in row.items()}


def _base_record(
    *,
    source_table: str,
    row_number: int,
    row: dict[str, str],
    flow_kind: str,
    source_raw_name: str,
    recipient_raw_name: str,
    date: str,
    amount_aud: str,
    return_type: str,
    receipt_type: str,
    transaction_kind: str,
    source_role: str,
    recipient_role: str,
    source_identifier: str = "",
    recipient_identifier: str = "",
) -> dict[str, object]:
    return {
        "source_dataset": SOURCE_DATASET,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "source_table": source_table,
        "source_row_number": str(row_number),
        "flow_kind": flow_kind,
        "event_name": row.get("Event", ""),
        "financial_year": "",
        "return_type": return_type,
        "source_raw_name": source_raw_name,
        "recipient_raw_name": recipient_raw_name,
        "receipt_type": receipt_type,
        "transaction_kind": transaction_kind,
        "date": date,
        "amount_aud": amount_aud,
        "source_role": source_role,
        "recipient_role": recipient_role,
        "source_identifier": source_identifier,
        "recipient_identifier": recipient_identifier,
        "disclosure_system": "aec_election_financial_disclosure",
        "original": row,
    }


def _normalize_donor_donations_made(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Donor Donations Made.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_donor_donation_made",
        source_raw_name=row.get("Donor Name", ""),
        recipient_raw_name=row.get("Donated To", ""),
        date=row.get("Donated To Date Of Gift", ""),
        amount_aud=parse_money(row.get("Donated To Gift Value", "")),
        return_type="Election Donor Return",
        receipt_type="Donation Made",
        transaction_kind="election_donation",
        source_role="donor",
        recipient_role="candidate_party_or_group",
        source_identifier=row.get("Donor Code", ""),
    )


def _normalize_donor_donations_received(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Donor Donations Received.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_donor_donation_received",
        source_raw_name=row.get("Gift From Name", ""),
        recipient_raw_name=row.get("Donor Name", ""),
        date=row.get("Gift From Date Of Gift", ""),
        amount_aud=parse_money(row.get("Gift From Gift Value", "")),
        return_type="Election Donor Return",
        receipt_type="Donation Received",
        transaction_kind="election_donation",
        source_role="gift_provider",
        recipient_role="donor",
        recipient_identifier=row.get("Donor Code", ""),
    )


def _normalize_candidate_donations(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Senate Groups and Candidate Donations.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_candidate_or_senate_group_donation_received",
        source_raw_name=row.get("Donor Name", ""),
        recipient_raw_name=row.get("Name", ""),
        date=row.get("Date Of Gift", ""),
        amount_aud=parse_money(row.get("Gift Value", "")),
        return_type=f"Election {row.get('Return Type (Candidate/Senate Group)', '')} Return".strip(),
        receipt_type="Donation Received",
        transaction_kind="election_donation",
        source_role="donor",
        recipient_role=(row.get("Return Type (Candidate/Senate Group)", "") or "candidate_or_group"),
    )


def _normalize_candidate_benefits(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Senate Groups and Candidate Discretionary Benefits.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_candidate_or_senate_group_discretionary_benefit",
        source_raw_name=row.get("Discretionary Benefits Received From", ""),
        recipient_raw_name=row.get("Name", ""),
        date=row.get("Date", ""),
        amount_aud=parse_money(row.get("Amount", "")),
        return_type=f"Election {row.get('Return Type (Candidate/Senate Group)', '')} Return".strip(),
        receipt_type="Discretionary Benefit",
        transaction_kind="election_discretionary_benefit",
        source_role="benefit_provider",
        recipient_role=(row.get("Return Type (Candidate/Senate Group)", "") or "candidate_or_group"),
    )


def _normalize_third_party_donations_made(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Third Party Return Donations Made.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_third_party_donation_made",
        source_raw_name=row.get("Third Party Name", ""),
        recipient_raw_name=row.get("Name", ""),
        date=row.get("Date Of Donation", ""),
        amount_aud=parse_money(row.get("Donation Value", "")),
        return_type="Election Third Party Return",
        receipt_type="Donation Made",
        transaction_kind="election_donation",
        source_role="third_party",
        recipient_role="candidate_party_or_group",
        source_identifier=row.get("Third Party Code", ""),
        recipient_identifier=row.get("Client ID", ""),
    )


def _normalize_third_party_donations_received(
    row_number: int,
    row: dict[str, str],
) -> dict[str, object]:
    return _base_record(
        source_table="Third Party Return Donations Received.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_third_party_donation_received",
        source_raw_name=row.get("Donor Name", ""),
        recipient_raw_name=row.get("Third Party Name", ""),
        date=row.get("Date Of Gift", ""),
        amount_aud=parse_money(row.get("Gift Value", "")),
        return_type="Election Third Party Return",
        receipt_type="Donation Received",
        transaction_kind="election_donation",
        source_role="donor",
        recipient_role="third_party",
        source_identifier=row.get("Donor Id", ""),
        recipient_identifier=row.get("Third Party Code", ""),
    )


def _normalize_media_advertisement(row_number: int, row: dict[str, str]) -> dict[str, object]:
    return _base_record(
        source_table="Media Advertisement Details.csv",
        row_number=row_number,
        row=row,
        flow_kind="election_media_advertising_expenditure",
        source_raw_name=row.get("Advertiser", ""),
        recipient_raw_name=row.get("Business Name", "") or row.get("Name", ""),
        date=row.get("Date Run", ""),
        amount_aud=parse_money(row.get("Amount", "")),
        return_type=f"Election Media {row.get('Return Type', '')} Return".strip(),
        receipt_type="Media Advertisement",
        transaction_kind="election_media_advertising_expenditure",
        source_role=row.get("Advertiser Type", "") or "advertiser",
        recipient_role="media_provider",
        recipient_identifier=row.get("Media ID", ""),
    )


NORMALIZERS: dict[str, Callable[[int, dict[str, str]], dict[str, object]]] = {
    "Donor Donations Made.csv": _normalize_donor_donations_made,
    "Donor Donations Received.csv": _normalize_donor_donations_received,
    "Media Advertisement Details.csv": _normalize_media_advertisement,
    "Senate Groups and Candidate Discretionary Benefits.csv": _normalize_candidate_benefits,
    "Senate Groups and Candidate Donations.csv": _normalize_candidate_donations,
    "Third Party Return Donations Made.csv": _normalize_third_party_donations_made,
    "Third Party Return Donations Received.csv": _normalize_third_party_donations_received,
}


def _normalize_text(value: object) -> str:
    lowered = str(value or "").lower().strip()
    cleaned = "".join(character if character.isalnum() else " " for character in lowered)
    return " ".join(cleaned.split())


def _canonical_transaction_key_parts(record: dict[str, object]) -> dict[str, str]:
    return {
        "source_dataset": SOURCE_DATASET,
        "event_name": str(record.get("event_name") or ""),
        "transaction_kind": str(record.get("transaction_kind") or record.get("flow_kind") or ""),
        "date": str(record.get("date") or ""),
        "amount_aud": str(record.get("amount_aud") or ""),
        "source_normalized_name": _normalize_text(record.get("source_raw_name")),
        "recipient_normalized_name": _normalize_text(record.get("recipient_raw_name")),
    }


def _hash_key(payload: dict[str, str]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _is_dedup_eligible(record: dict[str, object]) -> bool:
    key_parts = _canonical_transaction_key_parts(record)
    return all(
        key_parts[field]
        for field in ("date", "amount_aud", "source_normalized_name", "recipient_normalized_name")
    )


def _observation_priority(record: dict[str, object]) -> tuple[int, int]:
    row_number = str(record.get("source_row_number") or "0")
    return (
        PRIMARY_OBSERVATION_TABLE_PRIORITY.get(str(record.get("source_table") or ""), 999),
        int(row_number) if row_number.isdigit() else 0,
    )


def _annotate_observation_groups(records: list[dict[str, object]]) -> dict[str, object]:
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        if _is_dedup_eligible(record):
            key_parts = _canonical_transaction_key_parts(record)
        else:
            key_parts = {
                "source_dataset": SOURCE_DATASET,
                "source_table": str(record.get("source_table") or ""),
                "source_row_number": str(record.get("source_row_number") or ""),
            }
        canonical_key = _hash_key(key_parts)
        record["canonical_transaction_key"] = canonical_key
        record["canonical_transaction_key_parts"] = key_parts
        groups[canonical_key].append(record)

    duplicate_group_count = 0
    duplicate_observation_count = 0
    for canonical_key, group_records in groups.items():
        source_tables = {str(record.get("source_table") or "") for record in group_records}
        has_cross_table_duplicate = len(group_records) > 1 and len(source_tables) > 1
        primary_record = min(group_records, key=_observation_priority)
        primary_table = str(primary_record.get("source_table") or "")
        primary_row_number = str(primary_record.get("source_row_number") or "")
        if has_cross_table_duplicate:
            duplicate_group_count += 1

        for index, record in enumerate(sorted(group_records, key=_observation_priority), start=1):
            if has_cross_table_duplicate and record is not primary_record:
                role = "duplicate_observation"
                duplicate_observation_count += 1
            elif has_cross_table_duplicate:
                role = "primary_transaction"
            else:
                role = "single_observation"
            record["public_amount_counting_role"] = role
            record["canonical_observation_count"] = len(group_records)
            record["canonical_observation_index"] = index
            record["canonical_primary_source_table"] = primary_table
            record["canonical_primary_source_row_number"] = primary_row_number
            record["canonical_duplicate_group_key"] = canonical_key if has_cross_table_duplicate else ""

    return {
        "canonical_transaction_count": len(groups),
        "duplicate_transaction_group_count": duplicate_group_count,
        "duplicate_observation_count": duplicate_observation_count,
    }


def summarize_aec_election_zip(
    source_id: str = "aec_download_all_election_data",
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
    target_dir = processed_dir / "aec_election"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}.schema_summary.json"
    payload = {
        "generated_at": timestamp,
        "source_metadata_path": str(metadata_path),
        "zip_path": str(zip_path),
        "table_count": len(table_summaries),
        "normalized_tables": sorted(NORMALIZERS),
        "tables": table_summaries,
    }
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path


def normalize_aec_election_money_flows(
    source_id: str = "aec_download_all_election_data",
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    zip_path = Path(metadata["body_path"])

    timestamp = _timestamp()
    target_dir = processed_dir / "aec_election_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    table_counts = {name: 0 for name in NORMALIZERS}
    skipped_tables: list[str] = []
    missing_amount_count = 0
    records: list[dict[str, object]] = []
    with zipfile.ZipFile(zip_path) as zip_file:
        names = set(zip_file.namelist())
        for name, normalizer in NORMALIZERS.items():
            if name not in names:
                skipped_tables.append(name)
                continue
            for row_number, row in _iter_zip_csv_rows(zip_file, name):
                record = normalizer(row_number, row)
                record["source_metadata_path"] = str(metadata_path)
                record["source_zip_path"] = str(zip_path)
                if not record["amount_aud"]:
                    missing_amount_count += 1
                table_counts[name] += 1
                records.append(record)

    observation_summary = _annotate_observation_groups(records)
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "source_metadata_path": str(metadata_path),
        "source_zip_path": str(zip_path),
        "jsonl_path": str(jsonl_path),
        "total_count": len(records),
        "missing_amount_count": missing_amount_count,
        **observation_summary,
        "table_counts": table_counts,
        "skipped_tables": skipped_tables,
        "aggregate_tables_intentionally_not_normalized": [
            "Donor Return.csv",
            "Media Returns.csv",
            "Senate Groups and Candidate Expenses.csv",
            "Senate Groups and Candidate Return Summary.csv",
            "Third Party Return Expenditure.csv",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
