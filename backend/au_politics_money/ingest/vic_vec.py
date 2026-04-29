from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.official_identifiers import normalize_name
from au_politics_money.ingest.sources import get_source
from au_politics_money.models import SourceRecord

SOURCE_DATASET = "vic_vec_funding_register"
FUNDING_REGISTER_SOURCE_ID = "vic_vec_funding_register"
DOCUMENT_FETCHER_NAME = "vic_vec_funding_register_document_fetcher"
PARSER_NAME = "vic_vec_funding_register_docx_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "vic_vec_funding_register_docx"
PUBLIC_SOURCE_NAME = "Victorian Electoral Commission"
VIC_VEC_PUBLIC_FUNDING_FLOW_KINDS = (
    "vic_administrative_funding_entitlement",
    "vic_policy_development_funding_payment",
    "vic_public_funding_payment",
)
VIC_VEC_CAVEAT = (
    "Official VEC funding-register records. These rows describe public funding, "
    "administrative expenditure funding, policy development funding, entitlements, "
    "payments, repayments, or recoveries for Victorian political participants. They "
    "are not private donations, gifts, personal income, or evidence of improper "
    "conduct. The VEC funding pages state that the information may be impacted by "
    "Hopper & Anor v State of Victoria [2026] HCA 11 and may not be accurate while "
    "the VEC reviews affected material."
)

WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
WORD_TAG = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


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


def _latest_document_summary(processed_dir: Path = PROCESSED_DIR) -> Path:
    candidates = sorted(
        (processed_dir / "vic_vec_funding_register_documents").glob("*.summary.json"),
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError("No VEC funding-register document summary found")
    return candidates[0]


def _slug(value: str, default: str = "document") -> str:
    normalized = normalize_name(value).replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]+", "_", normalized).strip("_")
    return normalized[:80] or default


def _source_id_key(source_id: str) -> str:
    digest = hashlib.sha1(source_id.encode("utf-8")).hexdigest()[:10]
    return f"{_slug(source_id)[:48]}_{digest}"


def _load_metadata(metadata_path: Path) -> dict[str, Any]:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if not metadata.get("body_path"):
        raise ValueError(f"Metadata has no body_path: {metadata_path}")
    return metadata


def _body_path_from_metadata(metadata_path: Path) -> Path:
    metadata = _load_metadata(metadata_path)
    body_path = Path(str(metadata["body_path"]))
    if not body_path.exists():
        raise FileNotFoundError(f"Metadata body_path does not exist: {body_path}")
    return body_path


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _funding_register_links(body: str, *, base_url: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(body, "html.parser")
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        title = _clean_text(anchor.get_text(" ", strip=True))
        url = urljoin(base_url, href)
        if not url.lower().endswith(".docx"):
            continue
        if "funding register" not in title.lower():
            continue
        if url in seen:
            continue
        seen.add(url)
        links.append({"title": title, "url": url})
    if not links:
        raise ValueError("No VEC funding-register DOCX links found")
    return links


def _document_source(link: dict[str, str]) -> SourceRecord:
    title = link["title"]
    digest = hashlib.sha1(link["url"].encode("utf-8")).hexdigest()[:10]
    return SourceRecord(
        source_id=f"{FUNDING_REGISTER_SOURCE_ID}__{_slug(title)}__{digest}",
        name=f"VEC Funding Register: {title}",
        jurisdiction="Victoria",
        level="state",
        source_type="state_public_funding_register_docx",
        url=link["url"],
        expected_format="docx",
        update_frequency="quarterly_or_as_updated",
        priority="high",
        notes=(
            "Official VEC funding-register DOCX discovered from the funding-register "
            "page. Public funding/admin/policy funding context only; not private donations."
        ),
    )


def fetch_vic_vec_funding_register_documents(
    *,
    page_metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if page_metadata_path is None:
        try:
            page_metadata_path = _latest_metadata(FUNDING_REGISTER_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            page_metadata_path = fetch_source(
                get_source(FUNDING_REGISTER_SOURCE_ID),
                raw_dir=raw_dir,
            )

    page_metadata_path = Path(page_metadata_path)
    page_metadata = _load_metadata(page_metadata_path)
    source = page_metadata.get("source") or {}
    if source.get("source_id") != FUNDING_REGISTER_SOURCE_ID:
        raise ValueError(
            f"Expected {FUNDING_REGISTER_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    page_body_path = _body_path_from_metadata(page_metadata_path)
    page_body_sha256 = _sha256_path(page_body_path)
    if page_metadata.get("sha256") and page_metadata["sha256"] != page_body_sha256:
        raise ValueError(
            f"VEC funding-register page body hash mismatch: "
            f"metadata={page_metadata['sha256']} actual={page_body_sha256}"
        )
    body = page_body_path.read_text(encoding="utf-8", errors="replace")
    links = _funding_register_links(
        body,
        base_url=str(page_metadata.get("final_url") or source.get("url") or ""),
    )

    documents: list[dict[str, str]] = []
    for link in links:
        doc_source = _document_source(link)
        metadata_path = fetch_source(doc_source, raw_dir=raw_dir)
        doc_metadata = _load_metadata(Path(metadata_path))
        doc_body_path = _body_path_from_metadata(Path(metadata_path))
        documents.append(
            {
                "title": link["title"],
                "url": link["url"],
                "source_id": doc_source.source_id,
                "metadata_path": str(metadata_path),
                "metadata_sha256": _sha256_path(Path(metadata_path)),
                "body_path": str(doc_body_path),
                "body_sha256": _sha256_path(doc_body_path),
                "source_sha256": str(doc_metadata.get("sha256") or ""),
            }
        )

    timestamp = _timestamp()
    target_dir = processed_dir / "vic_vec_funding_register_documents"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "document_count": len(documents),
        "documents": documents,
        "page_metadata_path": str(page_metadata_path),
        "page_metadata_sha256": _sha256_path(page_metadata_path),
        "page_body_path": str(page_body_path),
        "page_body_sha256": page_body_sha256,
        "source_id": FUNDING_REGISTER_SOURCE_ID,
        "source_dataset": SOURCE_DATASET,
        "fetcher_name": DOCUMENT_FETCHER_NAME,
        "claim_boundary": VIC_VEC_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def _docx_text(node: ET.Element) -> str:
    return _clean_text("".join(text for text in node.itertext()))


def _docx_blocks(path: Path) -> list[tuple[str, Any]]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    body = root.find("w:body", WORD_NS)
    if body is None:
        raise ValueError(f"DOCX body not found: {path}")

    blocks: list[tuple[str, Any]] = []
    for child in body:
        if child.tag == WORD_TAG + "p":
            text = _docx_text(child)
            if text:
                blocks.append(("p", text))
        elif child.tag == WORD_TAG + "tbl":
            rows: list[list[str]] = []
            for table_row in child.findall("./w:tr", WORD_NS):
                cells = [
                    _docx_text(cell)
                    for cell in table_row.findall("./w:tc", WORD_NS)
                ]
                if any(cells):
                    rows.append(cells)
            if rows:
                blocks.append(("tbl", rows))
    return blocks


def _table_context(blocks: list[tuple[str, Any]]) -> list[tuple[list[str], list[list[str]]]]:
    contexts: list[tuple[list[str], list[list[str]]]] = []
    paragraphs: list[str] = []
    for kind, value in blocks:
        if kind == "p":
            paragraphs.append(str(value))
            paragraphs = paragraphs[-8:]
        elif kind == "tbl":
            contexts.append((list(paragraphs), value))
    return contexts


def _parse_amount(value: str) -> Decimal | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    if cleaned.casefold() in {"n/a", "na", "not submitted", "to be confirmed"}:
        return None
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()").replace("$", "").replace(",", "").replace(" ", "")
    if cleaned in {"", "-"}:
        return None
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse VEC amount: {value!r}") from exc
    return -amount if negative else amount


def _parse_date(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned or cleaned.casefold() in {"n/a", "na"}:
        return ""
    for fmt in ("%d %B %Y", "%d %b %Y", "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse VEC date: {value!r}")


def _last_updated(blocks: list[tuple[str, Any]]) -> str:
    full_text = "\n".join(str(value) for kind, value in blocks if kind == "p")
    match = re.search(r"Last updated:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", full_text)
    return _parse_date(match.group(1)) if match else ""


def _election_day(paragraphs: list[str]) -> str:
    text = " ".join(paragraphs)
    match = re.search(r"Election day was\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", text)
    return _parse_date(match.group(1)) if match else ""


def _public_payment_period_label(paragraphs: list[str], fallback: str) -> str:
    text = " ".join(paragraphs)
    match = re.search(
        r"payments for the\s+(.+?)(?:\s+Election day was\b|$)",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return _clean_text(match.group(1))
    for paragraph in reversed(paragraphs):
        cleaned = _clean_text(paragraph)
        if not cleaned or "election day was" in cleaned.casefold():
            continue
        if "public funding" in cleaned.casefold() or "by-election" in cleaned.casefold():
            return cleaned
    return fallback


def _calendar_year(paragraphs: list[str]) -> str:
    text = " ".join(paragraphs)
    matches = re.findall(r"([0-9]{4})\s+calendar year", text, flags=re.IGNORECASE)
    return matches[-1] if matches else ""


def _header_index(rows: list[list[str]], required: tuple[str, ...]) -> int:
    required_normalized = tuple(normalize_name(value) for value in required)
    for index, row in enumerate(rows):
        normalized = tuple(normalize_name(cell) for cell in row[: len(required)])
        if normalized == required_normalized:
            return index
    raise ValueError(f"Expected VEC table header not found: {required!r}")


def _row_dict(headers: list[str], row: list[str]) -> dict[str, str]:
    return {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}


def _is_total_or_blank(recipient: str) -> bool:
    normalized = normalize_name(recipient)
    return not normalized or normalized in {"total", "totals"}


def _base_record(
    *,
    document: dict[str, str],
    doc_last_updated: str,
    row_number: int,
    table_index: int,
    row_index: int,
    flow_kind: str,
    receipt_type: str,
    recipient_type: str,
    recipient_name: str,
    amount: Decimal,
    date_value: str,
    period_label: str,
    description: str,
    original: dict[str, Any],
    amount_role: str,
    date_caveat: str,
) -> dict[str, Any]:
    source_metadata_path = Path(document["metadata_path"])
    source_body_path = Path(document["body_path"])
    source_row_number = ":".join(
        (
            _source_id_key(document["source_id"]),
            f"t{table_index}",
            f"r{row_index}",
            _slug(amount_role, "amount"),
        )
    )
    public_funding_context = {
        "tier": "source_backed_public_funding_context",
        "not_personal_receipt": True,
        "notes": [
            "VEC funding-register amount; not a private donation, gift, or personal receipt."
        ],
    }
    return {
        "schema_version": "vic_vec_funding_register_money_flow_v1",
        "source_dataset": SOURCE_DATASET,
        "source_id": document["source_id"],
        "source_table": SOURCE_TABLE,
        "source_row_number": source_row_number,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "jurisdiction_name": "Victoria",
        "jurisdiction_level": "state",
        "jurisdiction_code": "VIC",
        "financial_year": period_label,
        "return_type": "VEC funding register",
        "flow_kind": flow_kind,
        "receipt_type": receipt_type,
        "disclosure_category": flow_kind,
        "transaction_kind": "public_funding",
        "source_raw_name": PUBLIC_SOURCE_NAME,
        "recipient_raw_name": recipient_name,
        "amount_aud": str(amount),
        "currency": "AUD",
        "date": date_value,
        "date_reported": "",
        "description": description,
        "recipient_type_raw": recipient_type,
        "amount_role": amount_role,
        "doc_last_updated": doc_last_updated,
        "date_caveat": date_caveat,
        "document_title": document["title"],
        "document_url": document["url"],
        "public_amount_counting_role": "single_observation",
        "disclosure_system": "vic_vec_funding_register",
        "disclosure_threshold": "Not applicable: official public funding register.",
        "evidence_status": "official_record_parsed",
        "campaign_support_attribution": public_funding_context,
        "public_funding_context": public_funding_context,
        "claim_boundary": VIC_VEC_CAVEAT,
        "caveat": VIC_VEC_CAVEAT,
        "source_metadata_path": str(source_metadata_path),
        "source_metadata_sha256": document["metadata_sha256"],
        "source_body_path": str(source_body_path),
        "source_body_sha256": document["body_sha256"],
        "original": {
            **original,
            "table_index": table_index,
            "row_index": row_index,
            "amount_role": amount_role,
        },
    }


def _normalize_admin_document(
    *,
    document: dict[str, str],
    blocks: list[tuple[str, Any]],
    doc_last_updated: str,
    row_counter: int,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    required = ("Recipient name", "Recipient type", "Maximum entitlement")
    for table_index, (paragraphs, rows) in enumerate(_table_context(blocks), start=1):
        try:
            header_index = _header_index(rows, required)
        except ValueError:
            continue
        headers = rows[header_index]
        year = _calendar_year(paragraphs)
        if not year:
            raise ValueError(f"Could not infer VEC admin funding calendar year: {document['title']}")
        period_label = f"{year} calendar year"
        for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            row_data = _row_dict(headers, row)
            recipient = row_data.get("Recipient name", "")
            if _is_total_or_blank(recipient):
                continue
            amount_label = "Adjusted final entitlement"
            amount = _parse_amount(row_data.get(amount_label, ""))
            date_value = f"{year}-12-31"
            date_caveat = "Calendar-year context end date, not necessarily payment date."
            if amount is None:
                amount_label = "Maximum entitlement September year to date"
                amount = _parse_amount(row_data.get(amount_label, ""))
                date_value = f"{year}-09-30"
                date_caveat = "September year-to-date context date, not payment date."
            if amount is None:
                continue
            row_counter += 1
            records.append(
                _base_record(
                    document=document,
                    doc_last_updated=doc_last_updated,
                    row_number=row_counter,
                    table_index=table_index,
                    row_index=row_index,
                    flow_kind="vic_administrative_funding_entitlement",
                    receipt_type="Administrative expenditure funding entitlement",
                    recipient_type=row_data.get("Recipient type", ""),
                    recipient_name=recipient,
                    amount=amount,
                    date_value=date_value,
                    period_label=period_label,
                    description=(
                        f"VEC administrative expenditure funding entitlement for "
                        f"{recipient} ({period_label}); not private donation or personal income."
                    ),
                    original=row_data,
                    amount_role=normalize_name(amount_label).replace(" ", "_"),
                    date_caveat=date_caveat,
                )
            )
    return records, row_counter


def _normalize_public_payment_document(
    *,
    document: dict[str, str],
    blocks: list[tuple[str, Any]],
    doc_last_updated: str,
    row_counter: int,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    required = ("Recipient type", "Recipient name", "Maximum entitlement")
    for table_index, (paragraphs, rows) in enumerate(_table_context(blocks), start=1):
        try:
            header_index = _header_index(rows, required)
        except ValueError:
            continue
        headers = rows[header_index]
        election_day = _election_day(paragraphs)
        period_label = _public_payment_period_label(paragraphs, document["title"])
        amount_label = "Amount paid" if "Amount paid" in headers else "Net payment"
        for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            row_data = _row_dict(headers, row)
            recipient = row_data.get("Recipient name", "")
            if _is_total_or_blank(recipient):
                continue
            amount = _parse_amount(row_data.get(amount_label, ""))
            if amount is None:
                continue
            row_counter += 1
            records.append(
                _base_record(
                    document=document,
                    doc_last_updated=doc_last_updated,
                    row_number=row_counter,
                    table_index=table_index,
                    row_index=row_index,
                    flow_kind="vic_public_funding_payment",
                    receipt_type=f"Public funding {amount_label.lower()}",
                    recipient_type=row_data.get("Recipient type", ""),
                    recipient_name=recipient,
                    amount=amount,
                    date_value=election_day,
                    period_label=_clean_text(period_label),
                    description=(
                        f"VEC public funding {amount_label.lower()} for {recipient}: "
                        f"{document['title']}; not private donation or personal income."
                    ),
                    original=row_data,
                    amount_role=normalize_name(amount_label).replace(" ", "_"),
                    date_caveat="Election-day context date, not necessarily payment date."
                    if election_day
                    else "",
                )
            )
    return records, row_counter


def _normalize_advance_document(
    *,
    document: dict[str, str],
    blocks: list[tuple[str, Any]],
    doc_last_updated: str,
    row_counter: int,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    required = ("Recipient type", "Recipient name", "Maximum entitlement")
    for table_index, (paragraphs, rows) in enumerate(_table_context(blocks), start=1):
        header_index = _header_index(rows, required)
        headers = rows[header_index]
        period_label = "2026 State general election advance public funding"
        installment_columns = [
            (index, header)
            for index, header in enumerate(headers)
            if header.lower().startswith("instalment")
        ]
        for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            row_data = _row_dict(headers, row)
            recipient = row_data.get("Recipient name", "")
            if _is_total_or_blank(recipient):
                continue
            for column_index, header in installment_columns:
                amount = _parse_amount(row[column_index] if column_index < len(row) else "")
                if amount is None or amount == 0:
                    continue
                year_match = re.search(r"\b(20[0-9]{2})\b", header)
                year = year_match.group(1) if year_match else ""
                row_counter += 1
                records.append(
                    _base_record(
                        document=document,
                        doc_last_updated=doc_last_updated,
                        row_number=row_counter,
                        table_index=table_index,
                        row_index=row_index,
                        flow_kind="vic_public_funding_payment",
                        receipt_type=f"Advance public funding {header}",
                        recipient_type=row_data.get("Recipient type", ""),
                        recipient_name=recipient,
                        amount=amount,
                        date_value=f"{year}-12-31" if year else "",
                        period_label=period_label,
                        description=(
                            f"VEC advance public funding payment for {recipient}: {header}; "
                            "not private donation or personal income."
                        ),
                        original=row_data,
                        amount_role=normalize_name(header).replace(" ", "_"),
                        date_caveat="Calendar-year context date, not exact payment date."
                        if year
                        else "",
                    )
                )
    return records, row_counter


def _normalize_policy_document(
    *,
    document: dict[str, str],
    blocks: list[tuple[str, Any]],
    doc_last_updated: str,
    row_counter: int,
) -> tuple[list[dict[str, Any]], int]:
    records: list[dict[str, Any]] = []
    for table_index, (_paragraphs, rows) in enumerate(_table_context(blocks), start=1):
        try:
            header_index = _header_index(rows, ("Recipient type", "Recipient name"))
        except ValueError:
            continue
        year_row = rows[header_index - 1] if header_index > 0 else []
        years = [cell for cell in year_row if re.fullmatch(r"20[0-9]{2}", cell)]
        if not years:
            continue
        headers = rows[header_index]
        for row_index, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
            row_data = _row_dict(headers, row)
            recipient = row[1] if len(row) > 1 else ""
            if _is_total_or_blank(recipient):
                continue
            for offset, year in enumerate(years):
                date_index = 2 + offset * 2
                amount_index = date_index + 1
                date_paid = _parse_date(row[date_index]) if date_index < len(row) else ""
                amount = _parse_amount(row[amount_index] if amount_index < len(row) else "")
                if amount is None or amount == 0:
                    continue
                row_counter += 1
                records.append(
                    _base_record(
                        document=document,
                        doc_last_updated=doc_last_updated,
                        row_number=row_counter,
                        table_index=table_index,
                        row_index=row_index,
                        flow_kind="vic_policy_development_funding_payment",
                        receipt_type="Policy development funding payment",
                        recipient_type=row[0] if row else "",
                        recipient_name=recipient,
                        amount=amount,
                        date_value=date_paid,
                        period_label=f"{year} calendar year",
                        description=(
                            f"VEC policy development funding payment for {recipient} "
                            f"({year}); not private donation or personal income."
                        ),
                        original={
                            **row_data,
                            "payment_year": year,
                            "date_paid": row[date_index] if date_index < len(row) else "",
                            "amount_paid": row[amount_index] if amount_index < len(row) else "",
                        },
                        amount_role=f"policy_development_amount_paid_{year}",
                        date_caveat="Date paid from VEC funding-register table.",
                    )
                )
    return records, row_counter


def _records_from_document(
    document: dict[str, str],
    *,
    row_counter: int,
) -> tuple[list[dict[str, Any]], int]:
    body_path = Path(document["body_path"])
    if document.get("source_sha256") and document["source_sha256"] != _sha256_path(body_path):
        raise ValueError(
            f"VEC funding-register document hash mismatch: "
            f"metadata={document['source_sha256']} actual={_sha256_path(body_path)}"
        )
    blocks = _docx_blocks(body_path)
    doc_last_updated = _last_updated(blocks)
    title = document["title"].lower()
    if "administrative expenditure funding" in title:
        return _normalize_admin_document(
            document=document,
            blocks=blocks,
            doc_last_updated=doc_last_updated,
            row_counter=row_counter,
        )
    if "advance payments for 2026" in title:
        return _normalize_advance_document(
            document=document,
            blocks=blocks,
            doc_last_updated=doc_last_updated,
            row_counter=row_counter,
        )
    if "policy development funding" in title:
        return _normalize_policy_document(
            document=document,
            blocks=blocks,
            doc_last_updated=doc_last_updated,
            row_counter=row_counter,
        )
    return _normalize_public_payment_document(
        document=document,
        blocks=blocks,
        doc_last_updated=doc_last_updated,
        row_counter=row_counter,
    )


def normalize_vic_vec_funding_registers(
    *,
    document_summary_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if document_summary_path is None:
        document_summary_path = _latest_document_summary(processed_dir=processed_dir)

    document_summary_path = Path(document_summary_path)
    document_summary = json.loads(document_summary_path.read_text(encoding="utf-8"))
    if document_summary.get("source_dataset") != SOURCE_DATASET:
        raise ValueError(
            f"Expected {SOURCE_DATASET} summary, got {document_summary.get('source_dataset')!r}"
        )
    documents = document_summary.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError(f"VEC funding-register summary has no documents: {document_summary_path}")

    records: list[dict[str, Any]] = []
    row_counter = 0
    document_counts: Counter[str] = Counter()
    flow_counts: Counter[str] = Counter()
    for document in documents:
        doc_records, row_counter = _records_from_document(document, row_counter=row_counter)
        if not doc_records:
            raise ValueError(f"No VEC funding-register rows parsed from {document['title']!r}")
        records.extend(doc_records)
        document_counts[document["source_id"]] += len(doc_records)
        for record in doc_records:
            flow_counts[str(record["flow_kind"])] += 1

    timestamp = _timestamp()
    target_dir = processed_dir / "vic_vec_funding_register_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"
    amount_total = Decimal("0")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            amount_total += Decimal(str(record["amount_aud"]))
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "document_summary_path": str(document_summary_path),
        "document_summary_sha256": _sha256_path(document_summary_path),
        "source_dataset": SOURCE_DATASET,
        "source_id": FUNDING_REGISTER_SOURCE_ID,
        "source_counts": dict(sorted(document_counts.items())),
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "total_count": len(records),
        "reported_amount_total": str(amount_total),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "vic_vec_funding_register_money_flow_v1",
        "claim_boundary": VIC_VEC_CAVEAT,
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
