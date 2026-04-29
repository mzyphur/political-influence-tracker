from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.official_identifiers import normalize_name
from au_politics_money.ingest.sources import get_source

SOURCE_DATASET = "tas_tec_donations"
PARSER_NAME = "tas_tec_reportable_donation_table_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "tas_tec_reportable_political_donation_html_tables"
SCHEMA_VERSION = "tas_tec_reportable_donation_money_flow_v1"
EXPECTED_HEADERS = (
    "date of donation",
    "dollar value of donation",
    "name of recipient",
    "type of recipient",
    "name of donor",
    "abn or acn of donor",
    "donor declaration lodged",
    "recipient declaration lodged",
)
SOURCE_IDS = (
    "tas_tec_donations_monthly_table",
    "tas_tec_donations_seven_day_ha25_table",
    "tas_tec_donations_seven_day_lc26_table",
)
REPORTABLE_DONATION_CAVEAT = (
    "Official Tasmanian Electoral Commission reportable political donation "
    "table. Tasmania's Electoral Disclosure and Funding Act 2023 disclosure "
    "scheme commenced on 1 July 2025, so pre-regime gaps must not be read as "
    "zero influence. Rows disclose source-backed donor-to-recipient donation "
    "or reportable-loan observations and declaration-document status; they are "
    "not claims of wrongdoing, causation, quid pro quo, or improper influence."
)


@dataclass(frozen=True)
class TasTecDonationTableSpec:
    source_id: str
    report_label: str
    reporting_context: str
    financial_year: str
    event_name: str


TAS_TEC_DONATION_TABLES: tuple[TasTecDonationTableSpec, ...] = (
    TasTecDonationTableSpec(
        source_id="tas_tec_donations_monthly_table",
        report_label="Monthly disclosures",
        reporting_context="outside_election_period_monthly",
        financial_year="2025-2026",
        event_name="Monthly reportable political donations",
    ),
    TasTecDonationTableSpec(
        source_id="tas_tec_donations_seven_day_ha25_table",
        report_label="Seven-day disclosures: 2025 State election",
        reporting_context="2025_house_of_assembly_campaign_period",
        financial_year="2025-2026",
        event_name="2025 Tasmanian House of Assembly election",
    ),
    TasTecDonationTableSpec(
        source_id="tas_tec_donations_seven_day_lc26_table",
        report_label="Seven-day disclosures: 2026 Legislative Council elections",
        reporting_context="2026_legislative_council_campaign_period",
        financial_year="2025-2026",
        event_name="2026 Huon and Rosevears Legislative Council elections",
    ),
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
    return " ".join((value or "").replace("\xa0", " ").split())


def _normalize_header(value: str) -> str:
    return _clean_text(normalize_name(value).replace("-", " "))


def _money_string(value: str) -> tuple[str, bool]:
    cleaned = _clean_text(value)
    if not cleaned:
        raise ValueError("Missing TAS TEC donation amount")
    reportable_loan = "*" in cleaned
    cleaned = (
        cleaned.replace("$", "")
        .replace(",", "")
        .replace("*", "")
        .replace(" ", "")
        .strip()
    )
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse TAS TEC donation amount: {value!r}") from exc
    return str(-amount if negative else amount), reportable_loan


def _date_string(value: str, hidden_sort: str = "") -> str:
    hidden = _clean_text(hidden_sort)
    if re.fullmatch(r"\d{8}", hidden):
        return datetime.strptime(hidden, "%Y%m%d").date().isoformat()
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse TAS TEC donation date: {value!r}")


def _abn_or_acn(value: str, hidden_sort: str = "") -> dict[str, str]:
    raw = _clean_text(value)
    digits = re.sub(r"\D+", "", hidden_sort or raw)
    kind = ""
    if len(digits) == 11:
        kind = "ABN"
    elif len(digits) == 9:
        kind = "ACN"
    return {"raw": raw, "digits": digits, "kind": kind}


def _source_link_url(base_url: str, href: str) -> str:
    href = href.strip()
    parsed_base = urlparse(base_url)
    if href.startswith("data/") and "/data/" in parsed_base.path:
        href = href.removeprefix("data/")
    return urljoin(base_url, href)


def _declaration(cell: Tag, base_url: str) -> dict[str, str]:
    text = _clean_text(cell.get_text(" ", strip=True))
    link = cell.find("a", href=True)
    if isinstance(link, Tag):
        return {
            "status": "download_available",
            "label": _clean_text(link.get_text(" ", strip=True)) or "Download",
            "url": _source_link_url(base_url, str(link.get("href") or "")),
        }
    if normalize_name(text) == "failed to lodge":
        return {"status": "failed_to_lodge", "label": text, "url": ""}
    if text:
        return {"status": "published_text", "label": text, "url": ""}
    return {"status": "not_published_or_not_applicable", "label": "", "url": ""}


def _disclosure_record_id(
    source_id: str,
    source_row_number: str,
    donor_declaration: Mapping[str, str],
    recipient_declaration: Mapping[str, str],
    fallback_payload: str,
) -> str:
    for declaration in (donor_declaration, recipient_declaration):
        url = declaration.get("url") or ""
        if not url:
            continue
        name = Path(url).name
        match = re.match(r"^(edf-donation-[^-]+-\d+)-[dr]\.pdf$", name, flags=re.I)
        if match:
            return match.group(1)
    digest = hashlib.sha256(fallback_payload.encode("utf-8")).hexdigest()[:16]
    return f"{source_id}-row-{source_row_number}-{digest}"


def fetch_tas_tec_donation_tables(*, raw_dir: Path = RAW_DIR) -> dict[str, Path]:
    return {
        spec.source_id: fetch_source(get_source(spec.source_id), raw_dir=raw_dir)
        for spec in TAS_TEC_DONATION_TABLES
    }


def _records_from_table_body(
    *,
    spec: TasTecDonationTableSpec,
    metadata_path: Path,
    body_path: Path,
    metadata_sha256: str,
    body_sha256: str,
    body: str,
    source_url: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    table = soup.find("table")
    if not isinstance(table, Tag):
        raise ValueError(f"No TAS TEC donation table found for {spec.source_id}")
    headers = tuple(_normalize_header(th.get_text(" ", strip=True)) for th in table.find_all("th"))
    if headers != EXPECTED_HEADERS:
        raise ValueError(
            f"Unexpected TAS TEC donation headers for {spec.source_id}: "
            f"expected={EXPECTED_HEADERS!r} actual={headers!r}"
        )
    caption = _clean_text(table.find("caption").get_text(" ", strip=True)) if table.find("caption") else ""
    rows = table.select("tbody tr")
    if len(rows) <= 1:
        raise ValueError(f"TAS TEC donation table has no data rows for {spec.source_id}")

    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows[1:], start=1):
        cells = row.find_all("td")
        if len(cells) != len(EXPECTED_HEADERS):
            raise ValueError(
                f"TAS TEC donation row {spec.source_id}:{row_number} has "
                f"{len(cells)} cells, expected {len(EXPECTED_HEADERS)}"
            )
        date_cell, amount_cell, recipient_cell, recipient_type_cell, donor_cell, abn_cell, donor_decl_cell, recipient_decl_cell = cells
        donation_date = _date_string(
            date_cell.get_text(" ", strip=True),
            str(date_cell.get("data-hidden-sort") or ""),
        )
        amount_aud, reportable_loan = _money_string(amount_cell.get_text(" ", strip=True))
        recipient_name = _clean_text(recipient_cell.get_text(" ", strip=True))
        recipient_type = _clean_text(recipient_type_cell.get_text(" ", strip=True))
        donor_name = _clean_text(donor_cell.get_text(" ", strip=True))
        if not recipient_name:
            raise ValueError(f"TAS TEC donation row {spec.source_id}:{row_number} has no recipient")
        if not donor_name:
            raise ValueError(f"TAS TEC donation row {spec.source_id}:{row_number} has no donor")
        donor_identifier = _abn_or_acn(
            abn_cell.get_text(" ", strip=True),
            str(abn_cell.get("data-hidden-sort") or ""),
        )
        donor_declaration = _declaration(donor_decl_cell, source_url)
        recipient_declaration = _declaration(recipient_decl_cell, source_url)
        source_row_number = f"{spec.source_id}:r{row_number}"
        fallback_payload = "|".join(
            [
                spec.source_id,
                donation_date,
                amount_aud,
                donor_name,
                recipient_name,
                recipient_type,
            ]
        )
        disclosure_record_id = _disclosure_record_id(
            spec.source_id,
            str(row_number),
            donor_declaration,
            recipient_declaration,
            fallback_payload,
        )
        flow_kind = "tas_reportable_loan" if reportable_loan else "tas_reportable_donation"
        receipt_type = "Reportable loan" if reportable_loan else "Reportable political donation"
        source_urls = [
            declaration["url"]
            for declaration in (donor_declaration, recipient_declaration)
            if declaration.get("url")
        ]
        original = {
            "date_of_donation": _clean_text(date_cell.get_text(" ", strip=True)),
            "dollar_value_of_donation": _clean_text(amount_cell.get_text(" ", strip=True)),
            "name_of_recipient": recipient_name,
            "type_of_recipient": recipient_type,
            "name_of_donor": donor_name,
            "abn_or_acn_of_donor": donor_identifier["raw"],
            "donor_declaration_lodged": donor_declaration,
            "recipient_declaration_lodged": recipient_declaration,
            "source_as_at": caption,
        }
        records.append(
            {
                "schema_version": SCHEMA_VERSION,
                "source_dataset": SOURCE_DATASET,
                "source_id": spec.source_id,
                "source_table": SOURCE_TABLE,
                "source_row_number": source_row_number,
                "normalizer_name": PARSER_NAME,
                "normalizer_version": PARSER_VERSION,
                "observation_key": f"{spec.source_id}:{disclosure_record_id}",
                "jurisdiction_name": "Tasmania",
                "jurisdiction_level": "state",
                "jurisdiction_code": "TAS",
                "financial_year": spec.financial_year,
                "event_name": spec.event_name,
                "return_type": spec.report_label,
                "reporting_context": spec.reporting_context,
                "flow_kind": flow_kind,
                "receipt_type": receipt_type,
                "disclosure_category": flow_kind,
                "transaction_kind": "loan" if reportable_loan else "donation",
                "source_raw_name": donor_name,
                "recipient_raw_name": recipient_name,
                "recipient_type": recipient_type,
                "amount_aud": amount_aud,
                "currency": "AUD",
                "date": donation_date,
                "date_reported": "",
                "donor_abn_or_acn": donor_identifier,
                "donor_declaration_status": donor_declaration["status"],
                "recipient_declaration_status": recipient_declaration["status"],
                "supporting_document_urls": source_urls,
                "source_as_at": caption,
                "public_amount_counting_role": "single_observation",
                "disclosure_system": "tas_tec_electoral_disclosure_funding",
                "disclosure_threshold": (
                    "Tasmanian reportable political donation disclosure under "
                    "the Electoral Disclosure and Funding Act 2023; the scheme "
                    "commenced on 1 July 2025."
                ),
                "evidence_status": "official_record_parsed",
                "claim_boundary": REPORTABLE_DONATION_CAVEAT,
                "caveat": REPORTABLE_DONATION_CAVEAT,
                "source_metadata_path": str(metadata_path),
                "source_metadata_sha256": metadata_sha256,
                "source_body_path": str(body_path),
                "source_body_sha256": body_sha256,
                "original": original,
            }
        )
    return records


def normalize_tas_tec_donations(
    *,
    metadata_paths: Mapping[str, Path | str] | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    resolved_metadata_paths: dict[str, Path] = {}
    for spec in TAS_TEC_DONATION_TABLES:
        if metadata_paths and spec.source_id in metadata_paths:
            resolved_metadata_paths[spec.source_id] = Path(metadata_paths[spec.source_id])
            continue
        try:
            resolved_metadata_paths[spec.source_id] = _latest_metadata(
                spec.source_id,
                raw_dir=raw_dir,
            )
        except FileNotFoundError:
            resolved_metadata_paths[spec.source_id] = fetch_source(
                get_source(spec.source_id),
                raw_dir=raw_dir,
            )

    records: list[dict[str, Any]] = []
    source_counts: Counter[str] = Counter()
    flow_counts: Counter[str] = Counter()
    report_counts: Counter[str] = Counter()
    source_hashes: dict[str, dict[str, str]] = {}
    amount_total = Decimal("0")

    for spec in TAS_TEC_DONATION_TABLES:
        metadata_path = resolved_metadata_paths[spec.source_id]
        metadata_sha256 = _sha256_path(metadata_path)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source = metadata.get("source") or {}
        if source.get("source_id") != spec.source_id:
            raise ValueError(
                f"Expected {spec.source_id} metadata, got {source.get('source_id')!r}"
            )
        body_path = Path(str(metadata["body_path"]))
        body_sha256 = _sha256_path(body_path)
        if metadata.get("sha256") and metadata["sha256"] != body_sha256:
            raise ValueError(
                f"TAS TEC body hash mismatch for {body_path}: "
                f"metadata={metadata['sha256']} actual={body_sha256}"
            )
        table_records = _records_from_table_body(
            spec=spec,
            metadata_path=metadata_path,
            body_path=body_path,
            metadata_sha256=metadata_sha256,
            body_sha256=body_sha256,
            body=body_path.read_text(encoding="utf-8", errors="replace"),
            source_url=str(metadata.get("final_url") or source.get("url") or ""),
        )
        source_counts[spec.source_id] += len(table_records)
        report_counts[spec.report_label] += len(table_records)
        source_hashes[spec.source_id] = {
            "metadata_path": str(metadata_path),
            "metadata_sha256": metadata_sha256,
            "body_path": str(body_path),
            "body_sha256": body_sha256,
        }
        for record in table_records:
            amount_total += Decimal(str(record["amount_aud"]))
            flow_counts[str(record["flow_kind"])] += 1
        records.extend(table_records)

    if not records:
        raise ValueError("No TAS TEC donation rows extracted")

    timestamp = _timestamp()
    target_dir = processed_dir / "tas_tec_donation_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_dataset": SOURCE_DATASET,
        "source_ids": list(SOURCE_IDS),
        "source_counts": dict(sorted(source_counts.items())),
        "source_hashes": source_hashes,
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "report_counts": dict(sorted(report_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "claim_boundary": REPORTABLE_DONATION_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
