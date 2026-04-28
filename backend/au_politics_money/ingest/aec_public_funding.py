from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.aec_annual import parse_money


PARSER_NAME = "aec_public_funding_normalizer"
PARSER_VERSION = "1"
SOURCE_DATASET = "aec_public_funding"
PUBLIC_FUNDING_SOURCE_ID = "aec_2025_federal_election_funding_finalised"
PUBLIC_FUNDING_SOURCE_NAME = "Australian Electoral Commission"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted((raw_dir / source_id).glob("*/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No metadata found for source {source_id}")
    return candidates[0]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _page_title(soup: BeautifulSoup) -> str:
    heading = soup.find(["h1", "title"])
    return _normalize_text(heading.get_text(" ", strip=True) if heading else "")


def _page_updated_date(soup: BeautifulSoup) -> str:
    text = soup.get_text("\n", strip=True)
    match = re.search(r"Updated:\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4})", text)
    if not match:
        return ""
    try:
        parsed = datetime.strptime(match.group(1), "%d %B %Y")
    except ValueError:
        return ""
    return parsed.strftime("%d/%m/%Y")


def _event_name_from_title(title: str) -> str:
    match = re.search(r"\b(20\d{2})\b", title)
    if not match:
        return "Federal Election"
    return f"{match.group(1)} Federal Election"


def _section_for_table(table) -> str:
    heading = table.find_previous(["h2", "h3", "h4"])
    return _normalize_text(heading.get_text(" ", strip=True) if heading else "")


def _funding_section_from_rows(rows: list[dict[str, str]], fallback: str) -> str:
    if not rows:
        return fallback
    keys = set(rows[0])
    if "Political Party" in keys:
        return "Political parties"
    if "Independent Candidate" in keys:
        return "Independent Candidates"
    return fallback


def _table_rows(table) -> list[dict[str, str]]:
    headers = [
        _normalize_text(cell.get_text(" ", strip=True))
        for cell in table.find_all("th")
    ]
    if not headers:
        first_row = table.find("tr")
        if first_row:
            headers = [
                _normalize_text(cell.get_text(" ", strip=True))
                for cell in first_row.find_all(["td", "th"])
            ]
    if not headers:
        return []

    rows: list[dict[str, str]] = []
    for tr in table.find_all("tr"):
        cells = [_normalize_text(cell.get_text(" ", strip=True)) for cell in tr.find_all("td")]
        if not cells or len(cells) < 2:
            continue
        row = {headers[index]: value for index, value in enumerate(cells[: len(headers)])}
        rows.append(row)
    return rows


def _funding_record(
    *,
    row_number: int,
    section: str,
    name: str,
    amount: str,
    event_name: str,
    updated_date: str,
    original: dict[str, str],
) -> dict[str, object]:
    section_lower = section.lower()
    recipient_role = (
        "independent_candidate" if "independent candidate" in section_lower else "political_party"
    )
    tier = (
        "independent_candidate_public_funding_paid"
        if recipient_role == "independent_candidate"
        else "party_aggregate_public_funding_paid"
    )
    amount_aud = parse_money(amount)
    if amount and not amount_aud:
        raise ValueError(
            "Could not parse AEC public funding amount "
            f"{amount!r} for {name!r} in {section!r}"
        )
    return {
        "source_dataset": SOURCE_DATASET,
        "source_table": section,
        "source_row_number": str(row_number),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "flow_kind": "election_public_funding_paid",
        "event_name": event_name,
        "financial_year": "",
        "return_type": "Election Funding Payment Summary",
        "source_raw_name": PUBLIC_FUNDING_SOURCE_NAME,
        "recipient_raw_name": name,
        "receipt_type": "Election Public Funding",
        "transaction_kind": "election_public_funding",
        "date": updated_date,
        "amount_aud": amount_aud,
        "source_role": "public_funding_payer",
        "recipient_role": recipient_role,
        "disclosure_system": "aec_public_funding",
        "public_amount_counting_role": "single_observation",
        "attribution_tier": tier,
        "campaign_support_attribution": {
            "tier": tier,
            "not_personal_receipt": True,
            "public_funding": True,
            "notes": [
                "AEC election public funding payment; campaign-support context, not a political donation or gift."
            ],
        },
        "original": original,
    }


def normalize_aec_public_funding(
    source_id: str = PUBLIC_FUNDING_SOURCE_ID,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata["body_path"])
    soup = BeautifulSoup(body_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    title = _page_title(soup)
    event_name = _event_name_from_title(title)
    updated_date = _page_updated_date(soup)

    records: list[dict[str, object]] = []
    table_counts: dict[str, int] = {}
    for table in soup.find_all("table"):
        rows = _table_rows(table)
        section = _funding_section_from_rows(rows, _section_for_table(table))
        section_lower = section.lower()
        if "political part" not in section_lower and "independent candidate" not in section_lower:
            continue
        table_count = 0
        for row in rows:
            name = row.get("Political Party") or row.get("Independent Candidate") or ""
            amount = row.get("Total Election Funding Paid") or ""
            if not name or name.lower() == "total":
                continue
            table_count += 1
            records.append(
                _funding_record(
                    row_number=table_count + 1,
                    section=section,
                    name=name,
                    amount=amount,
                    event_name=event_name,
                    updated_date=updated_date,
                    original=row,
                )
            )
        if table_count:
            table_counts[section] = table_count

    if not records:
        raise RuntimeError(
            "No AEC public funding rows extracted from "
            f"{body_path}; page structure may have changed."
        )

    timestamp = _timestamp()
    target_dir = processed_dir / "aec_public_funding_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            record["source_metadata_path"] = str(metadata_path)
            record["source_body_path"] = str(body_path)
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_metadata_path": str(metadata_path),
        "source_body_path": str(body_path),
        "jsonl_path": str(jsonl_path),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "event_name": event_name,
        "updated_date": updated_date,
        "total_count": len(records),
        "missing_amount_count": sum(1 for record in records if not record["amount_aud"]),
        "table_counts": table_counts,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
