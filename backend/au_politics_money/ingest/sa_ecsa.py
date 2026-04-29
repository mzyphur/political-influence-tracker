from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.sources import get_source

SOURCE_DATASET = "sa_ecsa_funding_returns"
SOURCE_ID = "sa_ecsa_funding2024_return_records"
PARSER_NAME = "sa_ecsa_funding_return_index_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "sa_ecsa_funding2024_return_records_index"
BASE_URL = "https://www.ecsa.sa.gov.au/html/funding2024/index.php"
ROWS_PER_PAGE = 15
FINANCIAL_YEAR = "2025-2026"
FLOW_KIND_BY_RETURN_TYPE = {
    "Political Party Return": "sa_political_party_return_summary",
    "Candidate Campaign Donations Return": "sa_candidate_campaign_donations_return_summary",
    "Associated Entity Return": "sa_associated_entity_return_summary",
    "Third Party Return": "sa_third_party_return_summary",
    "Special Return for Large Gift Return": "sa_special_large_gift_return_summary",
    "Special Returnfor Large Gift Return": "sa_special_large_gift_return_summary",
    "Special Return for Large Gift": "sa_special_large_gift_return_summary",
    "Donor Return": "sa_donor_return_summary",
    "Capped Expenditure Period Return": "sa_capped_expenditure_return_summary",
    "Third Party Capped Expenditure Period Return": (
        "sa_third_party_capped_expenditure_return_summary"
    ),
    "Prescribed Expenditure Return": "sa_prescribed_expenditure_return_summary",
    "Annual Political Expenditure Return": "sa_annual_political_expenditure_return_summary",
}
CLAIM_BOUNDARY = (
    "Official Electoral Commission SA current funding portal index row. Rows "
    "summarise lodged political participant returns and link to the official "
    "return view/attachment page. The value is a return-level reported amount, "
    "not an individual donor-to-recipient transaction and not a personal receipt "
    "by a representative. Rows are source-backed disclosure context, not "
    "allegations of wrongdoing, causation, quid pro quo, or improper influence."
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _date_string(value: str) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(cleaned, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse ECSA date: {value!r}")


def _money_string(value: str) -> str:
    cleaned = _clean_text(value).replace("$", "").replace(",", "")
    if not cleaned:
        raise ValueError("Missing ECSA return amount")
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    cleaned = cleaned.strip("()")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse ECSA return amount: {value!r}") from exc
    return str(-amount if negative else amount)


def _source_row_number(report_url: str, page: int, row_index: int) -> str:
    match = re.search(r"[?&]ID=(\d+)", report_url)
    if match:
        return f"id:{match.group(1)}"
    digest = hashlib.sha1(report_url.encode("utf-8")).hexdigest()[:12]
    return f"p{page}:r{row_index}:{digest}"


def _portal_record_count(text: str) -> int:
    match = re.search(r"(\d[\d,]*)\s+records returned", text)
    if not match:
        raise ValueError("ECSA funding portal page did not expose a record count")
    return int(match.group(1).replace(",", ""))


def _request_url(page: int, *, filter_for: str = "") -> str:
    params = {
        "sort": "3",
        "order": "desc",
        "filterReport": "",
        "filterFor": filter_for,
        "filterSubmitter": "",
        "filterRecipient": "",
    }
    if page > 1:
        params["page"] = str(page)
    return f"{BASE_URL}?{urlencode(params)}"


def _filter_for_values(body: str) -> list[str]:
    soup = BeautifulSoup(body, "html.parser")
    select = soup.find("select", attrs={"name": "filterFor"})
    if select is None:
        return []
    values: list[str] = []
    for option in select.find_all("option"):
        value = option.get("value")
        if value:
            values.append(str(value))
    return values


def _fetch_html(
    url: str,
    *,
    headers: dict[str, str],
    timeout: int,
) -> tuple[bytes, int, str, dict[str, str]]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
        status = response.status
        final_url = response.url
        response_headers = dict(response.headers.items())
    return body, status, final_url, response_headers


def fetch_sa_ecsa_return_index_pages(
    *,
    raw_dir: Path = RAW_DIR,
    max_pages: int | None = None,
    timeout: int = 60,
) -> Path:
    source = get_source(SOURCE_ID)
    run_ts = _timestamp()
    target_dir = raw_dir / SOURCE_ID / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)
    request_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    }

    pages: list[dict[str, Any]] = []
    page_sequence = 0
    first_url = _request_url(1)
    first_body, first_status, first_final_url, first_headers = _fetch_html(
        first_url,
        headers=request_headers,
        timeout=timeout,
    )
    if not (200 <= first_status < 400):
        raise RuntimeError(f"ECSA funding portal fetch failed for index page: {first_status}")
    first_text = first_body.decode("utf-8", errors="replace")
    reported_total = _portal_record_count(first_text)
    filter_for_values = _filter_for_values(first_text)
    filter_plan = filter_for_values or [""]
    expected_page_count = 0
    filtered_reported_total = 0

    for filter_index, filter_for in enumerate(filter_plan, start=1):
        page = 1
        page_count = 1
        filter_reported_total = 0
        while page <= page_count:
            if max_pages is not None and page_sequence >= max_pages:
                break
            url = _request_url(page, filter_for=filter_for)
            if filter_for == "" and page == 1:
                body = first_body
                status = first_status
                final_url = first_final_url
                headers = first_headers
            else:
                body, status, final_url, headers = _fetch_html(
                    url,
                    headers=request_headers,
                    timeout=timeout,
                )
            if not (200 <= status < 400):
                raise RuntimeError(
                    f"ECSA funding portal fetch failed for filter {filter_for!r} "
                    f"page {page}: {status}"
                )
            text = body.decode("utf-8", errors="replace")
            if page == 1:
                filter_reported_total = _portal_record_count(text)
                if filter_reported_total == 0:
                    page_count = 0
                    break
                page_count = max(1, math.ceil(filter_reported_total / ROWS_PER_PAGE))
                expected_page_count += page_count
                filtered_reported_total += filter_reported_total
            page_sequence += 1
            body_path = target_dir / (
                f"filter_for_{filter_index:03d}_page_{page:03d}.html"
            )
            body_path.write_bytes(body)
            pages.append(
                {
                    "page": page_sequence,
                    "filter_for_index": filter_index,
                    "filter_for": filter_for,
                    "filter_page": page,
                    "filter_record_count_reported": filter_reported_total,
                    "url": url,
                    "final_url": final_url,
                    "http_status": status,
                    "content_type": headers.get("Content-Type")
                    or headers.get("content-type"),
                    "content_length": len(body),
                    "sha256": _sha256_bytes(body),
                    "body_path": str(body_path),
                }
            )
            page += 1
        if max_pages is not None and page_sequence >= max_pages:
            break

    body_manifest = {
        "source_id": SOURCE_ID,
        "generated_at": run_ts,
        "portal_record_count_reported": reported_total,
        "filter_for_value_count": len(filter_for_values),
        "filtered_record_count_reported": filtered_reported_total,
        "expected_page_count": expected_page_count,
        "fetched_page_count": len(pages),
        "complete_page_coverage": (
            len(pages) == expected_page_count
            and (not filter_for_values or filtered_reported_total == reported_total)
        ),
        "acquisition_strategy": (
            "filter_for_partitioned_pages"
            if filter_for_values
            else "unfiltered_paginated_pages"
        ),
        "pages": pages,
    }
    body_manifest_path = target_dir / "body.json"
    body_manifest_path.write_text(
        json.dumps(body_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    body_manifest_sha256 = _sha256_path(body_manifest_path)
    metadata = {
        "source": asdict(source),
        "fetched_at": run_ts,
        "ok": True,
        "http_status": 200,
        "final_url": BASE_URL,
        "content_type": "application/json",
        "content_length": body_manifest_path.stat().st_size,
        "sha256": body_manifest_sha256,
        "body_path": str(body_manifest_path),
        "request_headers": request_headers,
        **body_manifest,
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _records_from_page(
    *,
    body: str,
    page: int,
    page_url: str,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(body, "html.parser")
    table = soup.find("table")
    if table is None:
        raise ValueError(f"ECSA funding portal page {page} has no records table")
    rows = table.find_all("tr")
    if not rows:
        raise ValueError(f"ECSA funding portal page {page} has no table rows")
    headers = [
        _clean_text(cell.get_text(" ", strip=True)).casefold()
        for cell in rows[0].find_all(["th", "td"])
    ]
    expected_headers = [
        "return type",
        "date lodged",
        "submitter",
        "for",
        "recipient",
        "from",
        "to",
        "value",
        "reports",
    ]
    if headers[:9] != expected_headers:
        raise ValueError(f"Unexpected ECSA funding portal headers: {headers!r}")

    records: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows[1:], start=2):
        cells = [_clean_text(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
        if not cells:
            continue
        if len(cells) < 9:
            raise ValueError(
                f"ECSA funding portal row {page}:{row_index} has {len(cells)} cells"
            )
        return_type, lodged, submitter, for_name, recipient, period_from, period_to, value = (
            cells[:8]
        )
        link = row.find("a", href=True)
        if link is None:
            raise ValueError(f"ECSA funding portal row {page}:{row_index} has no report link")
        report_url = urljoin(page_url, str(link["href"]))
        flow_kind = FLOW_KIND_BY_RETURN_TYPE.get(return_type)
        if flow_kind is None:
            raise ValueError(f"Unexpected ECSA return type: {return_type!r}")
        amount_aud = _money_string(value)
        date_lodged = _date_string(lodged)
        period_start = _date_string(period_from)
        period_end = _date_string(period_to)
        source_row_number = _source_row_number(report_url, page, row_index)
        recipient_name = recipient or for_name
        original = {
            "return_type": return_type,
            "date_lodged": lodged,
            "submitter": submitter,
            "for": for_name,
            "recipient": recipient,
            "from": period_from,
            "to": period_to,
            "value": value,
            "report_url": report_url,
            "page": page,
            "row_index": row_index,
        }
        records.append(
            {
                "schema_version": "sa_ecsa_return_summary_money_flow_v1",
                "source_dataset": SOURCE_DATASET,
                "source_id": SOURCE_ID,
                "source_table": SOURCE_TABLE,
                "source_row_number": source_row_number,
                "normalizer_name": PARSER_NAME,
                "normalizer_version": PARSER_VERSION,
                "jurisdiction_name": "South Australia",
                "jurisdiction_level": "state",
                "jurisdiction_code": "SA",
                "financial_year": FINANCIAL_YEAR,
                "return_type": return_type,
                "flow_kind": flow_kind,
                "receipt_type": return_type,
                "disclosure_category": flow_kind,
                "transaction_kind": "return_summary",
                "source_raw_name": submitter,
                "recipient_raw_name": recipient_name,
                "amount_aud": amount_aud,
                "currency": "AUD",
                "date": "",
                "date_reported": date_lodged,
                "reporting_period_start": period_start,
                "reporting_period_end": period_end,
                "report_url": report_url,
                "source_actor_role": "submitter_or_agent",
                "recipient_actor_role": "return_subject_or_recipient",
                "description": (
                    f"ECSA {return_type} lodged by {submitter} for "
                    f"{for_name or recipient_name}; return-level value {value} "
                    f"for {period_from} to {period_to}."
                ),
                "public_amount_counting_role": "jurisdictional_cross_disclosure_observation",
                "cross_source_dedupe_status": "return_summary_not_transaction_deduplicated",
                "amount_counting_caveat": (
                    "Return-level summary value. Do not include in consolidated "
                    "reported money totals until detailed return parsing and "
                    "cross-source deduplication are available."
                ),
                "disclosure_system": "sa_ecsa_funding_disclosure_portal",
                "evidence_status": "official_record_parsed",
                "claim_boundary": CLAIM_BOUNDARY,
                "caveat": CLAIM_BOUNDARY,
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "original": original,
            }
        )
    return records


def normalize_sa_ecsa_return_index(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        candidates = sorted((raw_dir / SOURCE_ID).glob("*/metadata.json"), reverse=True)
        metadata_path = candidates[0] if candidates else fetch_sa_ecsa_return_index_pages()

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != SOURCE_ID:
        raise ValueError(f"Expected {SOURCE_ID} metadata, got {source.get('source_id')!r}")
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"ECSA funding portal body manifest hash mismatch: "
            f"metadata={metadata['sha256']} actual={source_body_sha256}"
        )
    pages = metadata.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("ECSA funding portal metadata has no pages")

    records: list[dict[str, Any]] = []
    for page in pages:
        page_path = Path(str(page["body_path"]))
        expected_page_sha256 = str(page.get("sha256") or "")
        actual_page_sha256 = _sha256_path(page_path)
        if expected_page_sha256 and actual_page_sha256 != expected_page_sha256:
            raise ValueError(
                f"ECSA funding portal page hash mismatch for {page_path}: "
                f"metadata={expected_page_sha256} actual={actual_page_sha256}"
            )
        records.extend(
            _records_from_page(
                body=page_path.read_text(encoding="utf-8", errors="replace"),
                page=int(page["page"]),
                page_url=str(page["url"]),
                source_metadata_path=metadata_path,
                source_body_path=source_body_path,
                source_metadata_sha256=source_metadata_sha256,
                source_body_sha256=source_body_sha256,
            )
        )

    unique_records: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    duplicate_observation_count = 0
    for record in records:
        original = record["original"]
        unique_key = (
            str(record["return_type"]),
            str(record["source_row_number"]),
            str(record["source_raw_name"]),
            str(record["recipient_raw_name"]),
            str(record["reporting_period_start"]),
            str(record["reporting_period_end"]),
            str(original.get("report_url") or ""),
        )
        if unique_key in unique_records:
            duplicate_observation_count += 1
            continue
        unique_records[unique_key] = record
    records = list(unique_records.values())

    reported_total = int(metadata.get("portal_record_count_reported") or 0)
    complete_page_coverage = bool(metadata.get("complete_page_coverage"))
    if complete_page_coverage and reported_total and len(records) != reported_total:
        raise ValueError(
            "ECSA funding portal row count mismatch: "
            f"reported={reported_total} parsed={len(records)}"
        )
    if not records:
        raise ValueError("No ECSA funding portal records extracted")

    run_ts = _timestamp()
    output_dir = processed_dir / "sa_ecsa_return_summary_money_flows"
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{run_ts}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    flow_counts = Counter(record["flow_kind"] for record in records)
    amount_total = sum(Decimal(record["amount_aud"]) for record in records)
    summary = {
        "schema_version": "sa_ecsa_return_summary_money_flow_v1",
        "source_dataset": SOURCE_DATASET,
        "source_id": SOURCE_ID,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "generated_at": run_ts,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_metadata_path": str(metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "source_counts": {SOURCE_ID: len(records)},
        "portal_record_count_reported": reported_total,
        "filtered_record_count_reported": int(
            metadata.get("filtered_record_count_reported") or 0
        ),
        "duplicate_page_observation_count": duplicate_observation_count,
        "acquisition_strategy": metadata.get("acquisition_strategy"),
        "complete_page_coverage": complete_page_coverage,
        "total_count": len(records),
        "flow_kind_counts": dict(sorted(flow_counts.items())),
        "reported_amount_total": str(amount_total),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    summary_path = output_dir / f"{run_ts}.summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
