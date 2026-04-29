from __future__ import annotations

import base64
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.request import HTTPCookieProcessor, Request, build_opener

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.sources import get_source

SOURCE_DATASET = "waec_political_contributions"
DASHBOARD_SOURCE_ID = "waec_ods_public_dashboard"
CONTRIBUTIONS_SOURCE_ID = "waec_ods_political_contributions"
PARSER_NAME = "waec_ods_political_contribution_grid_normalizer"
PARSER_VERSION = "1"
SOURCE_TABLE = "waec_ods_published_disclosures_grid"
DASHBOARD_URL = "https://disclosures.elections.wa.gov.au/public-dashboard/"
TOKEN_URL = "https://disclosures.elections.wa.gov.au/_layout/tokenhtml"
GRID_ENDPOINT = (
    "https://disclosures.elections.wa.gov.au"
    "/_services/entity-grid-data.json/d436612a-0860-4cad-a0b0-54fad5d1dfe5"
)
CONTRIBUTIONS_VIEW_ID = "c1183ed0-5b64-ef11-a671-00224817f825"
CONTRIBUTIONS_ENTITY_NAME = "waec_disclosure"
DEFAULT_PAGE_SIZE = 1000
CLAIM_BOUNDARY = (
    "Official Western Australian Electoral Commission Online Disclosure System "
    "published political contribution row. The row records a disclosed political "
    "contribution from a donor to a political entity at the evidence level "
    "published by WAEC. It is not a claim of wrongdoing, causation, quid pro quo, "
    "or improper influence."
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


def _request_headers(*, referer: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-AU,en;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def _fetch_bytes(opener, url: str, *, headers: dict[str, str], timeout: int) -> tuple[bytes, int, str, dict[str, str]]:
    request = Request(url, headers=headers)
    with opener.open(request, timeout=timeout) as response:
        body = response.read()
        status = response.status
        final_url = response.url
        response_headers = dict(response.headers.items())
    return body, status, final_url, response_headers


def _fetch_json(
    opener,
    url: str,
    *,
    payload: dict[str, Any],
    token: str,
    timeout: int,
) -> tuple[bytes, int, str, dict[str, str]]:
    headers = {
        **_request_headers(referer=DASHBOARD_URL),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/json; charset=utf-8",
        "X-Requested-With": "XMLHttpRequest",
        "__RequestVerificationToken": token,
    }
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with opener.open(request, timeout=timeout) as response:
        body = response.read()
        status = response.status
        final_url = response.url
        response_headers = dict(response.headers.items())
    return body, status, final_url, response_headers


def _selected_contribution_layout(dashboard_body: str) -> dict[str, Any]:
    soup = BeautifulSoup(dashboard_body, "html.parser")
    for grid in soup.select("div.entity-grid.entitylist"):
        encoded = grid.get("data-view-layouts")
        if not encoded:
            continue
        layouts = json.loads(base64.b64decode(str(encoded)).decode("utf-8"))
        if not layouts:
            continue
        layout = layouts[0]
        config = layout.get("Configuration") or {}
        if (
            config.get("EntityName") == CONTRIBUTIONS_ENTITY_NAME
            and str(config.get("ViewId") or "").lower() == CONTRIBUTIONS_VIEW_ID
        ):
            return layout
    raise ValueError("WAEC dashboard did not expose the expected political contributions grid")


def _token_from_html(token_body: str) -> str:
    soup = BeautifulSoup(token_body, "html.parser")
    token_input = soup.find("input", attrs={"name": "__RequestVerificationToken"})
    token = token_input.get("value") if token_input else None
    if not token:
        raise ValueError("WAEC token response did not contain an anti-forgery token")
    return str(token)


def _grid_payload(layout: dict[str, Any], *, page: int, page_size: int) -> dict[str, Any]:
    return {
        "base64SecureConfiguration": layout["Base64SecureConfiguration"],
        "sortExpression": layout.get("SortExpression") or "",
        "search": None,
        "page": page,
        "pageSize": page_size,
        "pagingCookie": "",
        "filter": "",
        "metaFilter": None,
        "nlSearchFilter": None,
        "timezoneOffset": -600,
        "customParameters": [],
        "entityName": None,
        "entityId": None,
    }


def fetch_waec_political_contribution_pages(
    *,
    raw_dir: Path = RAW_DIR,
    max_pages: int | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    timeout: int = 90,
) -> Path:
    if page_size <= 0:
        raise ValueError("page_size must be positive")
    source = get_source(CONTRIBUTIONS_SOURCE_ID)
    run_ts = _timestamp()
    target_dir = raw_dir / CONTRIBUTIONS_SOURCE_ID / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    dashboard_body, dashboard_status, dashboard_final_url, dashboard_headers = _fetch_bytes(
        opener,
        DASHBOARD_URL,
        headers=_request_headers(),
        timeout=timeout,
    )
    if not (200 <= dashboard_status < 400):
        raise RuntimeError(f"WAEC dashboard fetch failed: {dashboard_status}")
    dashboard_path = target_dir / "dashboard.html"
    dashboard_path.write_bytes(dashboard_body)
    layout = _selected_contribution_layout(dashboard_body.decode("utf-8", errors="replace"))

    token_body, token_status, token_final_url, token_headers = _fetch_bytes(
        opener,
        TOKEN_URL,
        headers=_request_headers(referer=DASHBOARD_URL),
        timeout=timeout,
    )
    if not (200 <= token_status < 400):
        raise RuntimeError(f"WAEC token fetch failed: {token_status}")
    token_path = target_dir / "token.html"
    token_path.write_bytes(token_body)
    token = _token_from_html(token_body.decode("utf-8", errors="replace"))

    pages: list[dict[str, Any]] = []
    seen_page_first_ids: set[str] = set()
    page = 1
    while True:
        if max_pages is not None and len(pages) >= max_pages:
            break
        payload = _grid_payload(layout, page=page, page_size=page_size)
        body, status, final_url, headers = _fetch_json(
            opener,
            GRID_ENDPOINT,
            payload=payload,
            token=token,
            timeout=timeout,
        )
        if not (200 <= status < 400):
            raise RuntimeError(f"WAEC contribution grid fetch failed on page {page}: {status}")
        data = json.loads(body.decode("utf-8", errors="replace"))
        records = data.get("Records") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise ValueError(f"WAEC contribution page {page} did not return Records")
        if not records:
            break
        first_id = str(records[0].get("Id") or "")
        if first_id and first_id in seen_page_first_ids:
            if pages and pages[-1].get("more_records"):
                raise RuntimeError(
                    "WAEC contribution pagination repeated the first record while "
                    "the previous page indicated that more records were available"
                )
            break
        if first_id:
            seen_page_first_ids.add(first_id)
        body_path = target_dir / f"contributions_page_{page:04d}.json"
        body_path.write_bytes(body)
        pages.append(
            {
                "page": page,
                "page_size": page_size,
                "url": GRID_ENDPOINT,
                "final_url": final_url,
                "http_status": status,
                "content_type": headers.get("Content-Type") or headers.get("content-type"),
                "content_length": len(body),
                "sha256": _sha256_bytes(body),
                "body_path": str(body_path),
                "record_count": len(records),
                "item_count_reported": int(data.get("ItemCount") or 0),
                "page_count_reported": int(data.get("PageCount") or 0),
                "more_records": bool(data.get("MoreRecords")),
            }
        )
        if not data.get("MoreRecords"):
            break
        page += 1

    if not pages:
        raise ValueError("No WAEC political contribution pages fetched")

    body_manifest = {
        "source_id": CONTRIBUTIONS_SOURCE_ID,
        "generated_at": run_ts,
        "acquisition_strategy": "power_pages_entity_grid_json",
        "dashboard": {
            "url": DASHBOARD_URL,
            "final_url": dashboard_final_url,
            "http_status": dashboard_status,
            "content_type": dashboard_headers.get("Content-Type")
            or dashboard_headers.get("content-type"),
            "content_length": len(dashboard_body),
            "sha256": _sha256_bytes(dashboard_body),
            "body_path": str(dashboard_path),
        },
        "token": {
            "url": TOKEN_URL,
            "final_url": token_final_url,
            "http_status": token_status,
            "content_type": token_headers.get("Content-Type") or token_headers.get("content-type"),
            "content_length": len(token_body),
            "sha256": _sha256_bytes(token_body),
            "body_path": str(token_path),
            "token_sha256": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        },
        "grid": {
            "endpoint": GRID_ENDPOINT,
            "entity_name": CONTRIBUTIONS_ENTITY_NAME,
            "view_id": CONTRIBUTIONS_VIEW_ID,
            "sort_expression": layout.get("SortExpression"),
            "columns": [
                {
                    "name": column.get("Name"),
                    "logical_name": column.get("LogicalName"),
                    "label": column.get("Label"),
                }
                for column in layout.get("Columns", [])
            ],
        },
        "page_size": page_size,
        "expected_complete": max_pages is None,
        "complete_page_coverage": max_pages is None and not pages[-1].get("more_records"),
        "pages": pages,
    }
    body_manifest_path = target_dir / "body.json"
    body_manifest_path.write_text(
        json.dumps(body_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata = {
        "source": asdict_source(source),
        "fetched_at": run_ts,
        "ok": True,
        "http_status": 200,
        "final_url": GRID_ENDPOINT,
        "content_type": "application/json",
        "content_length": body_manifest_path.stat().st_size,
        "sha256": _sha256_path(body_manifest_path),
        "body_path": str(body_manifest_path),
        "request_headers": _request_headers(),
        **body_manifest,
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def asdict_source(source: Any) -> dict[str, Any]:
    return {
        "source_id": source.source_id,
        "name": source.name,
        "jurisdiction": source.jurisdiction,
        "level": source.level,
        "source_type": source.source_type,
        "url": source.url,
        "expected_format": source.expected_format,
        "update_frequency": source.update_frequency,
        "priority": source.priority,
        "notes": source.notes,
    }


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted((raw_dir / source_id).glob("*/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No metadata found for source {source_id}")
    return candidates[0]


def _attr(record: dict[str, Any], name: str) -> dict[str, Any] | None:
    for attr in record.get("Attributes") or []:
        if attr.get("Name") == name:
            return attr
    return None


def _display(attr: dict[str, Any] | None) -> str:
    if not attr:
        return ""
    for key in ("DisplayValue", "FormattedValue"):
        value = attr.get(key)
        if value:
            return str(value).strip()
    value = attr.get("Value")
    if isinstance(value, dict) and value.get("Name"):
        return str(value["Name"]).strip()
    return str(value or "").strip()


def _lookup_id(attr: dict[str, Any] | None) -> str:
    value = attr.get("Value") if attr else None
    if isinstance(value, dict) and value.get("Id"):
        return str(value["Id"])
    return ""


def _money_string(attr: dict[str, Any] | None) -> str:
    value = attr.get("Value") if attr else None
    if isinstance(value, dict) and "Value" in value:
        try:
            return str(Decimal(str(value["Value"])))
        except InvalidOperation as exc:
            raise ValueError(f"Could not parse WAEC amount: {value!r}") from exc
    cleaned = _display(attr).replace("$", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("Missing WAEC amount")
    try:
        return str(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse WAEC amount: {_display(attr)!r}") from exc


def _date_string(attr: dict[str, Any] | None) -> str:
    if not attr:
        return ""
    value = attr.get("Value")
    if isinstance(value, str):
        match = re.fullmatch(r"/Date\((\d+)\)/", value)
        if match:
            return datetime.fromtimestamp(
                int(match.group(1)) / 1000,
                tz=timezone.utc,
            ).date().isoformat()
    displayed = _display(attr)
    if not displayed:
        return ""
    slash_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", displayed)
    if slash_match:
        first = int(slash_match.group(1))
        second = int(slash_match.group(2))
        if first <= 12 and second <= 12:
            raise ValueError(f"Ambiguous WAEC display date: {displayed!r}")
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(displayed, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Could not parse WAEC date: {displayed!r}")


def _records_from_page(
    *,
    page_data: dict[str, Any],
    page_number: int,
    source_metadata_path: Path,
    source_body_path: Path,
    source_metadata_sha256: str,
    source_body_sha256: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row_index, row in enumerate(page_data.get("Records") or [], start=1):
        external_id = str(row.get("Id") or "")
        if not external_id:
            raise ValueError(f"WAEC contribution row {page_number}:{row_index} has no Id")
        donor = _display(_attr(row, "waec_donorid"))
        recipient = _display(_attr(row, "waec_politicalentityaccountid"))
        if not donor or not recipient:
            raise ValueError(f"WAEC contribution row {external_id} is missing donor/recipient")
        contribution_type = _display(_attr(row, "waec_politicalcontributiontype"))
        amount_aud = _money_string(_attr(row, "waec_amount"))
        date_received = _date_string(_attr(row, "waec_datedisclosurereceived"))
        financial_year = _display(_attr(row, "waec_financialyearid"))
        donor_postcode = _display(
            _attr(row, "a_f9c48d73871b443ba59c75ceb843e999.waec_publicpostcode")
        )
        status = _display(_attr(row, "statuscode"))
        version = _display(_attr(row, "waec_disclosureversiontype"))
        currency = _display(_attr(row, "transactioncurrencyid")) or "AUD"
        version_is_original = not version or version.casefold() == "original"
        public_amount_counting_role = (
            "single_observation"
            if version_is_original
            else "versioned_observation_pending_dedupe"
        )
        original = {
            "id": external_id,
            "disclosure_received_date": date_received,
            "financial_year": financial_year,
            "donor": donor,
            "donor_id": _lookup_id(_attr(row, "waec_donorid")),
            "donor_public_postcode": donor_postcode,
            "political_entity": recipient,
            "political_entity_id": _lookup_id(_attr(row, "waec_politicalentityaccountid")),
            "political_contribution_type": contribution_type,
            "amount": _display(_attr(row, "waec_amount")),
            "status": status,
            "version": version,
            "currency": currency,
        }
        records.append(
            {
                "schema_version": "waec_political_contribution_money_flow_v1",
                "source_dataset": SOURCE_DATASET,
                "source_id": CONTRIBUTIONS_SOURCE_ID,
                "source_table": SOURCE_TABLE,
                "source_row_number": external_id,
                "normalizer_name": PARSER_NAME,
                "normalizer_version": PARSER_VERSION,
                "jurisdiction_name": "Western Australia",
                "jurisdiction_level": "state",
                "jurisdiction_code": "WA",
                "financial_year": financial_year,
                "return_type": "WAEC published political contribution",
                "flow_kind": "wa_political_contribution",
                "receipt_type": contribution_type,
                "disclosure_category": "wa_political_contribution",
                "transaction_kind": "political_contribution",
                "source_raw_name": donor,
                "recipient_raw_name": recipient,
                "amount_aud": amount_aud,
                "source_row_reported_amount_aud": amount_aud,
                "currency": "AUD" if "australian dollar" in currency.casefold() else currency,
                "date": "",
                "date_reported": date_received,
                "date_caveat": (
                    "WAEC publishes a disclosure-received date for this row. "
                    "The contribution transaction date is not exposed in the grid "
                    "fields parsed by this adapter."
                ),
                "description": (
                    f"WAEC published political contribution ({contribution_type}) "
                    f"from {donor} to {recipient}."
                ),
                "donor_public_postcode": donor_postcode,
                "waec_donor_id": original["donor_id"],
                "waec_political_entity_id": original["political_entity_id"],
                "public_amount_counting_role": public_amount_counting_role,
                "version_counting_caveat": (
                    "Original-version WAEC rows are counted as source-row observations. "
                    "Amendment or other versioned rows are preserved but excluded from "
                    "reported amount totals until amendment lineage is validated."
                ),
                "disclosure_system": "waec_online_disclosure_system",
                "evidence_status": "official_record_parsed",
                "claim_boundary": CLAIM_BOUNDARY,
                "caveat": (
                    "WAEC Online Disclosure System row. Contribution types include "
                    "gifts and other political contribution categories; do not treat "
                    "all rows as personal receipt by a candidate or representative."
                ),
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "original": original,
            }
        )
    return records


def normalize_waec_political_contributions(
    *,
    metadata_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        metadata_path = _latest_metadata(CONTRIBUTIONS_SOURCE_ID, raw_dir=raw_dir)

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != CONTRIBUTIONS_SOURCE_ID:
        raise ValueError(
            f"Expected {CONTRIBUTIONS_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"WAEC contribution body manifest hash mismatch: "
            f"metadata={metadata['sha256']} actual={source_body_sha256}"
        )
    pages = metadata.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("WAEC contribution metadata has no pages")

    records: list[dict[str, Any]] = []
    for page in pages:
        page_path = Path(str(page["body_path"]))
        expected_page_sha256 = str(page.get("sha256") or "")
        actual_page_sha256 = _sha256_path(page_path)
        if expected_page_sha256 and actual_page_sha256 != expected_page_sha256:
            raise ValueError(
                f"WAEC contribution page hash mismatch for {page_path}: "
                f"metadata={expected_page_sha256} actual={actual_page_sha256}"
            )
        page_data = json.loads(page_path.read_text(encoding="utf-8"))
        records.extend(
            _records_from_page(
                page_data=page_data,
                page_number=int(page["page"]),
                source_metadata_path=metadata_path,
                source_body_path=source_body_path,
                source_metadata_sha256=source_metadata_sha256,
                source_body_sha256=source_body_sha256,
            )
        )

    unique: dict[str, dict[str, Any]] = {}
    duplicate_count = 0
    for record in records:
        key = str(record["source_row_number"])
        if key in unique:
            duplicate_count += 1
            continue
        unique[key] = record
    records = list(unique.values())
    if not records:
        raise ValueError("No WAEC political contribution records extracted")

    run_ts = _timestamp()
    output_dir = processed_dir / "waec_political_contribution_money_flows"
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{run_ts}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    flow_counts = Counter(record["receipt_type"] for record in records)
    amount_total = sum(
        Decimal(record["amount_aud"])
        for record in records
        if str(record.get("amount_aud") or "").strip()
        and record.get("public_amount_counting_role") != "versioned_observation_pending_dedupe"
    )
    reported_item_counts = [
        int(page.get("item_count_reported") or 0)
        for page in metadata.get("pages") or []
        if int(page.get("item_count_reported") or 0) > 0
    ]
    reported_page_counts = [
        int(page.get("page_count_reported") or 0)
        for page in metadata.get("pages") or []
        if int(page.get("page_count_reported") or 0) > 0
    ]
    item_count_reported = max(reported_item_counts) if reported_item_counts else 0
    page_count_reported = max(reported_page_counts) if reported_page_counts else 0
    source_page_record_count_total = sum(
        int(page.get("record_count") or 0) for page in metadata.get("pages") or []
    )
    if bool(metadata.get("complete_page_coverage")) and source_page_record_count_total:
        if len(records) != source_page_record_count_total:
            raise ValueError(
                "WAEC contribution row count mismatch: "
                f"source={source_page_record_count_total} parsed={len(records)}"
            )
        if item_count_reported and item_count_reported > len(records):
            raise ValueError(
                "WAEC contribution reported item count exceeds parsed rows: "
                f"source={item_count_reported} parsed={len(records)}"
            )
    summary = {
        "schema_version": "waec_political_contribution_money_flow_v1",
        "source_dataset": SOURCE_DATASET,
        "source_id": CONTRIBUTIONS_SOURCE_ID,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "generated_at": run_ts,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_metadata_path": str(metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "source_counts": {CONTRIBUTIONS_SOURCE_ID: len(records)},
        "duplicate_page_observation_count": duplicate_count,
        "complete_page_coverage": bool(metadata.get("complete_page_coverage")),
        "source_item_count_reported": item_count_reported,
        "source_item_count_appears_capped": bool(
            item_count_reported and item_count_reported < len(records)
        ),
        "source_page_count_reported": page_count_reported,
        "source_page_record_count_total": source_page_record_count_total,
        "total_count": len(records),
        "receipt_type_counts": dict(sorted(flow_counts.items())),
        "versioned_observation_pending_dedupe_count": sum(
            1
            for record in records
            if record.get("public_amount_counting_role")
            == "versioned_observation_pending_dedupe"
        ),
        "reported_amount_total": str(amount_total),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    summary_path = output_dir / f"{run_ts}.summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path
