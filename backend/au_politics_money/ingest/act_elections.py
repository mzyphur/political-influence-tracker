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

SOURCE_DATASET = "act_elections_gift_returns"
STATE_SOURCE_DATASET = "act_elections_state_disclosures"
ANNUAL_SOURCE_DATASET = "act_elections_annual_returns"
GIFT_RETURNS_SOURCE_ID = "act_gift_returns_2025_2026"
ANNUAL_RETURNS_SOURCE_ID = "act_annual_returns_2024_2025"
PARSER_NAME = "act_gift_return_html_normalizer"
ANNUAL_PARSER_NAME = "act_annual_return_receipt_html_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "act_gift_returns_2025_2026_html"
ANNUAL_SOURCE_TABLE = "act_annual_returns_2024_2025_receipts_html"
FINANCIAL_YEAR = "2025-2026"
ANNUAL_FINANCIAL_YEAR = "2024-2025"
EXPECTED_HEADERS = (
    "from",
    "date reported to elections act",
    "date gift received",
    "amount",
    "type",
    "description of gift in kind",
)
ANNUAL_RECEIPT_HEADERS = ("received from", "address", "receipt type", "amount")
GIFT_RETURN_CAVEAT = (
    "Official Elections ACT gift-return page. Rows disclose gifts received of "
    "money or gifts-in-kind where a party grouping or non-party candidate "
    "grouping receives a gift, or cumulative gifts from a single donor, "
    "totalling $1,000 or more during the relevant period. Individual row "
    "amounts may be below $1,000 because the legal trigger can be cumulative. "
    "The source page states individual home addresses are not fully published "
    "online; suburb/postcode or post-office-box details may be the public "
    "address surface."
)
ANNUAL_RETURN_CAVEAT = (
    "Official Elections ACT 2024/2025 annual-return page. Detail rows disclose "
    "receipts totalling $1,000 or more for political parties, MLAs, non-party "
    "MLAs, and associated entities. Receipt rows can include gifts of money, "
    "gifts-in-kind, free facilities use, and other receipts. These rows are "
    "source-backed disclosure observations; they are not claims of wrongdoing, "
    "policy causation, or personal income."
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


def _money_string(value: str) -> str:
    cleaned = (value or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("Missing ACT gift-return amount")
    try:
        return str(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse ACT gift-return amount: {value!r}") from exc


def _date_string(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if not cleaned:
        return ""
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse ACT gift-return date: {value!r}")


def _cell_lines(cell: Tag) -> list[str]:
    return [
        line.strip()
        for line in cell.get_text("\n", strip=True).splitlines()
        if line.strip()
    ]


def _recipient_from_heading(heading: Tag) -> str:
    text = " ".join(heading.get_text(" ", strip=True).split())
    match = re.match(r"^Gifts received by\s+(.+)$", text, flags=re.IGNORECASE)
    if not match:
        raise ValueError(f"Unexpected ACT gift-return section heading: {text!r}")
    return match.group(1).strip()


def _flow_kind(gift_type: str) -> str:
    normalized = normalize_name(gift_type)
    if "kind" in normalized:
        return "act_gift_in_kind"
    return "act_gift_of_money"


def _annual_receipt_flow_kind(receipt_type: str) -> str:
    normalized = normalize_name(receipt_type)
    if "free facilities" in normalized:
        return "act_annual_free_facilities_use"
    if "kind" in normalized:
        return "act_annual_gift_in_kind"
    if "gift" in normalized and "money" in normalized:
        return "act_annual_gift_of_money"
    return "act_annual_receipt"


def _annual_transaction_kind(flow_kind: str) -> str:
    if flow_kind == "act_annual_gift_of_money":
        return "gift"
    if flow_kind in {"act_annual_gift_in_kind", "act_annual_free_facilities_use"}:
        return "gift_in_kind"
    return "receipt"


def _annual_amount_counting_role(flow_kind: str) -> str:
    if flow_kind == "act_annual_receipt":
        return "state_source_receipt_context_not_consolidated"
    return "single_observation"


def _source_name_and_identifier(value: str) -> tuple[str, dict[str, str]]:
    cleaned = " ".join((value or "").split())
    match = re.search(r"\b(ABN|ACN):?\s*([0-9 ]{9,})\b", cleaned, flags=re.IGNORECASE)
    identifier = {"raw": "", "kind": "", "value": ""}
    if match:
        identifier = {
            "raw": match.group(0).strip(),
            "kind": match.group(1).upper(),
            "value": re.sub(r"\D", "", match.group(2)),
        }
        cleaned = (cleaned[: match.start()] + cleaned[match.end() :]).strip()
    return cleaned or "Source not identified", identifier


def _annual_recipient_from_heading(heading_text: str) -> str:
    suffix = " - receipts totalling $1,000 or more"
    text = " ".join((heading_text or "").split())
    if not text.lower().endswith(suffix):
        raise ValueError(f"Unexpected ACT annual-return receipt heading: {text!r}")
    return text[: -len(suffix)].strip()


def _nearest_previous_heading_text(table: Tag, name: str) -> str:
    heading = table.find_previous(name)
    if not isinstance(heading, Tag):
        return ""
    return " ".join(heading.get_text(" ", strip=True).split())


def _stable_observation_key(parts: list[str]) -> str:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{ANNUAL_RETURNS_SOURCE_ID}:{digest}"


def _normalize_header(value: str) -> str:
    normalized = normalize_name(value).replace("-", " ")
    return " ".join(normalized.split())


def _validated_section_table(heading: Tag) -> Tag:
    for node in heading.find_all_next(["h2", "table"]):
        if not isinstance(node, Tag):
            continue
        if node.name == "h2":
            text = node.get_text(" ", strip=True)
            if text.lower().startswith("gifts received by "):
                break
        if node.name != "table":
            continue
        headers = tuple(_normalize_header(th.get_text(" ", strip=True)) for th in node.find_all("th"))
        if headers != EXPECTED_HEADERS:
            raise ValueError(
                "Unexpected ACT gift-return table headers: "
                f"expected={EXPECTED_HEADERS!r} actual={headers!r}"
            )
        return node
    recipient = _recipient_from_heading(heading)
    raise ValueError(f"ACT gift-return section has no validated table: {recipient}")


def _records_from_body(
    *,
    body: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    records: list[dict[str, Any]] = []
    row_number = 0
    for heading in soup.find_all("h2"):
        heading_text = heading.get_text(" ", strip=True)
        if not heading_text.lower().startswith("gifts received by "):
            continue
        recipient = _recipient_from_heading(heading)
        table = _validated_section_table(heading)
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if len(cells) != 6:
                raise ValueError(
                    f"ACT gift-return row for {recipient} has {len(cells)} cells, expected 6"
                )
            row_number += 1
            donor_lines = _cell_lines(cells[0])
            if not donor_lines:
                raise ValueError(f"ACT gift-return row {row_number} has no donor")
            donor_name = donor_lines[0]
            donor_address = "\n".join(donor_lines[1:])
            date_reported = _date_string(cells[1].get_text(" ", strip=True))
            date_received = _date_string(cells[2].get_text(" ", strip=True))
            amount = " ".join(cells[3].get_text(" ", strip=True).split())
            gift_type = " ".join(cells[4].get_text(" ", strip=True).split())
            description = " ".join(cells[5].get_text(" ", strip=True).split())
            amount_aud = _money_string(amount)
            flow_kind = _flow_kind(gift_type)
            original = {
                "recipient": recipient,
                "from": donor_lines,
                "date_reported_to_elections_act": date_reported,
                "date_gift_received": date_received,
                "amount": amount,
                "type": gift_type,
                "description_of_gift_in_kind": description,
            }
            records.append(
                {
                    "schema_version": "act_gift_return_money_flow_v1",
                    "source_dataset": SOURCE_DATASET,
                    "source_id": GIFT_RETURNS_SOURCE_ID,
                    "source_table": SOURCE_TABLE,
                    "source_row_number": str(row_number),
                    "normalizer_name": PARSER_NAME,
                    "normalizer_version": PARSER_VERSION,
                    "jurisdiction_name": "Australian Capital Territory",
                    "jurisdiction_level": "state",
                    "jurisdiction_code": "ACT",
                    "financial_year": FINANCIAL_YEAR,
                    "return_type": "ACT gift return",
                    "flow_kind": flow_kind,
                    "receipt_type": gift_type,
                    "disclosure_category": flow_kind,
                    "transaction_kind": "gift_in_kind" if flow_kind.endswith("in_kind") else "gift",
                    "source_raw_name": donor_name,
                    "recipient_raw_name": recipient,
                    "amount_aud": amount_aud,
                    "currency": "AUD",
                    "date": date_received,
                    "date_reported": date_reported,
                    "description": description,
                    "donor_address_public": donor_address,
                    "public_amount_counting_role": "single_observation",
                    "disclosure_system": "act_elections_financial_disclosure",
                    "disclosure_threshold": (
                        "ACT gift-return disclosure threshold: a gift, or cumulative "
                        "gifts from one donor, totalling $1,000 or more during the "
                        "relevant period."
                    ),
                    "evidence_status": "official_record_parsed",
                    "claim_boundary": (
                        "Source-backed ACT gift-return row. A gift-in-kind amount is a "
                        "reported value of a non-cash benefit, not a cash payment."
                    ),
                    "caveat": GIFT_RETURN_CAVEAT,
                    "source_metadata_path": str(source_metadata_path),
                    "source_metadata_sha256": source_metadata_sha256,
                    "source_body_path": str(source_body_path),
                    "source_body_sha256": source_body_sha256,
                    "original": original,
                }
            )
    if not records:
        raise ValueError("No ACT gift-return rows extracted")
    return records


def _annual_records_from_body(
    *,
    body: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    records: list[dict[str, Any]] = []
    row_number = 0
    for table in soup.find_all("table"):
        if not isinstance(table, Tag):
            continue
        header_row = table.find("tr")
        if not isinstance(header_row, Tag):
            continue
        headers = tuple(
            _normalize_header(th.get_text(" ", strip=True))
            for th in header_row.find_all("th")
        )
        if headers[:4] != ANNUAL_RECEIPT_HEADERS:
            continue
        heading_text = _nearest_previous_heading_text(table, "h4")
        recipient = _annual_recipient_from_heading(heading_text)
        entity_group = _nearest_previous_heading_text(table, "h2") or "ACT political entity"
        for row in table.select("tbody tr"):
            cells = row.find_all("td")
            if not cells:
                continue
            if len(cells) != 4:
                raise ValueError(
                    f"ACT annual-return receipt row for {recipient} has "
                    f"{len(cells)} cells, expected 4"
                )
            row_number += 1
            source_text = " ".join(cells[0].get_text(" ", strip=True).split())
            source_name, source_identifier = _source_name_and_identifier(source_text)
            address = " ".join(cells[1].get_text(" ", strip=True).split())
            receipt_type = " ".join(cells[2].get_text(" ", strip=True).split())
            amount_text = " ".join(cells[3].get_text(" ", strip=True).split())
            amount_aud = _money_string(amount_text)
            flow_kind = _annual_receipt_flow_kind(receipt_type)
            original = {
                "recipient": recipient,
                "entity_group": entity_group,
                "received_from": source_text,
                "address": address,
                "receipt_type": receipt_type,
                "amount": amount_text,
            }
            observation_key = _stable_observation_key(
                [
                    f"row:{row_number}",
                    recipient,
                    entity_group,
                    source_name,
                    source_identifier.get("value") or "",
                    address,
                    receipt_type,
                    amount_aud,
                ]
            )
            records.append(
                {
                    "schema_version": "act_annual_return_receipt_money_flow_v1",
                    "source_dataset": ANNUAL_SOURCE_DATASET,
                    "source_id": ANNUAL_RETURNS_SOURCE_ID,
                    "source_table": ANNUAL_SOURCE_TABLE,
                    "source_row_number": f"{ANNUAL_RETURNS_SOURCE_ID}:r{row_number}",
                    "normalizer_name": ANNUAL_PARSER_NAME,
                    "normalizer_version": PARSER_VERSION,
                    "observation_key": observation_key,
                    "jurisdiction_name": "Australian Capital Territory",
                    "jurisdiction_level": "state",
                    "jurisdiction_code": "ACT",
                    "financial_year": ANNUAL_FINANCIAL_YEAR,
                    "return_type": f"ACT annual return - {entity_group} receipts",
                    "recipient_context": entity_group,
                    "flow_kind": flow_kind,
                    "receipt_type": receipt_type,
                    "disclosure_category": flow_kind,
                    "transaction_kind": _annual_transaction_kind(flow_kind),
                    "source_raw_name": source_name,
                    "recipient_raw_name": recipient,
                    "amount_aud": amount_aud,
                    "currency": "AUD",
                    "date": "",
                    "date_reported": "",
                    "date_caveat": (
                        "The annual-return receipt detail table does not publish a "
                        "per-row receipt date in the online table; the financial "
                        "year is retained as the temporal context."
                    ),
                    "source_abn_or_acn": source_identifier,
                    "source_address_public": address,
                    "public_amount_counting_role": _annual_amount_counting_role(flow_kind),
                    "disclosure_system": "act_elections_financial_disclosure",
                    "disclosure_threshold": (
                        "ACT annual-return receipt detail threshold: receipts "
                        "totalling $1,000 or more are published in source tables."
                    ),
                    "evidence_status": "official_record_parsed",
                    "claim_boundary": ANNUAL_RETURN_CAVEAT,
                    "caveat": ANNUAL_RETURN_CAVEAT,
                    "source_metadata_path": str(source_metadata_path),
                    "source_metadata_sha256": source_metadata_sha256,
                    "source_body_path": str(source_body_path),
                    "source_body_sha256": source_body_sha256,
                    "original": original,
                }
            )
    if not records:
        raise ValueError("No ACT annual-return receipt rows extracted")
    return records


def normalize_act_gift_returns(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        try:
            metadata_path = _latest_metadata(GIFT_RETURNS_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            metadata_path = fetch_source(get_source(GIFT_RETURNS_SOURCE_ID), raw_dir=raw_dir)

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != GIFT_RETURNS_SOURCE_ID:
        raise ValueError(
            f"Expected {GIFT_RETURNS_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"ACT gift-return body hash mismatch: metadata={metadata['sha256']} "
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
    target_dir = processed_dir / "act_gift_return_money_flows"
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
        "source_id": GIFT_RETURNS_SOURCE_ID,
        "source_dataset": SOURCE_DATASET,
        "source_counts": {GIFT_RETURNS_SOURCE_ID: len(records)},
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "act_gift_return_money_flow_v1",
        "claim_boundary": GIFT_RETURN_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def normalize_act_annual_return_receipts(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        try:
            metadata_path = _latest_metadata(ANNUAL_RETURNS_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            metadata_path = fetch_source(
                get_source(ANNUAL_RETURNS_SOURCE_ID),
                raw_dir=raw_dir,
            )

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
            f"ACT annual-return body hash mismatch: metadata={metadata['sha256']} "
            f"actual={source_body_sha256}"
        )
    body = source_body_path.read_text(encoding="utf-8", errors="replace")
    records = _annual_records_from_body(
        body=body,
        source_metadata_path=metadata_path,
        source_body_path=source_body_path,
        source_metadata_sha256=source_metadata_sha256,
        source_body_sha256=source_body_sha256,
    )

    timestamp = _timestamp()
    target_dir = processed_dir / "act_annual_return_receipt_money_flows"
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
        "source_dataset": ANNUAL_SOURCE_DATASET,
        "source_counts": {ANNUAL_RETURNS_SOURCE_ID: len(records)},
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": ANNUAL_PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "act_annual_return_receipt_money_flow_v1",
        "claim_boundary": ANNUAL_RETURN_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
