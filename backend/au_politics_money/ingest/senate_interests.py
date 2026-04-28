from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from au_politics_money.config import PROCESSED_DIR
from au_politics_money.ingest.discovered_sources import source_from_discovered_link
from au_politics_money.ingest.discovery import discover_links_from_body, latest_body_path
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.interest_extraction import (
    extract_event_date,
    extract_provider,
    extract_reported_value,
    parse_iso_datetime_date,
)
from au_politics_money.ingest.sources import get_source
from au_politics_money.models import DiscoveredLink, SourceRecord


SENATE_INTEREST_CATEGORIES = {
    "realEstate": "Real estate",
    "shareHoldings": "Shareholdings",
    "trusts": "Trusts",
    "registeredDirectorshipsOfCompanies": "Registered directorships of companies",
    "partnerships": "Partnerships",
    "liabilities": "Liabilities",
    "investments": "Investments",
    "savingsOrInvestmentAccounts": "Savings or investment accounts",
    "otherAssets": "Other assets",
    "otherIncome": "Other income",
    "gifts": "Gifts",
    "sponsoredTravelOrHospitality": "Sponsored travel or hospitality",
    "officeHolderDonating": "Organisations to which office-holder donations are made",
    "otherInterest": "Other interests",
}

COUNTERPARTY_FIELDS = (
    "creditor",
    "nameOfBankInstitution",
    "nameOfOrganisation",
    "nameOfCompany",
    "nameOfTrust",
    "nameOfPartnership",
    "nameOfIncome",
    "nameOfInvestment",
    "provider",
    "providedBy",
    "sponsor",
    "sponsoredBy",
    "host",
    "hostedBy",
)
BENEFIT_PROVIDER_TEXT_FIELDS = (
    "detailOfGifts",
    "detailOfTravelHospitality",
    "details",
    "natureOfInterest",
)

ENV_API_BASE_RE = re.compile(r"SENATORS_API_BASE_URL:\s*['\"](?P<url>[^'\"]+)['\"]")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_file(directory: Path, pattern: str) -> Path:
    candidates = sorted(directory.glob(pattern), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No files matching {pattern!r} in {directory}")
    return candidates[0]


def _metadata_body_path(metadata_path: Path) -> Path:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return Path(metadata["body_path"])


def parse_senate_env_api_base(js_text: str) -> str:
    match = ENV_API_BASE_RE.search(js_text)
    if match is None:
        raise ValueError("Could not find SENATORS_API_BASE_URL in Senate interests env.js")
    return match.group("url").rstrip("/")


def _senate_env_link() -> DiscoveredLink:
    source = get_source("aph_senators_interests")
    body_path = latest_body_path(source.source_id)
    if body_path is None:
        fetch_source(source)
        body_path = latest_body_path(source.source_id)
    if body_path is None:
        raise FileNotFoundError(f"No raw body found for source {source.source_id}")

    links = discover_links_from_body(source, body_path)
    env_links = [link for link in links if "senators-interests-register/build/env.js" in link.url]
    if not env_links:
        raise FileNotFoundError("Could not discover Senate interests env.js from official page")
    return env_links[0]


def _fetch_senate_env() -> Path:
    source = get_source("aph_senators_interests")
    return fetch_source(source_from_discovered_link(source, _senate_env_link()))


def _source_for_query_statements(api_base_url: str) -> SourceRecord:
    query = urlencode(
        {
            "currentPage": 1,
            "pageSize": 100,
            "sortBy": "senator",
            "sortDirection": "ascending",
        }
    )
    return SourceRecord(
        source_id="aph_senators_interests_api_query_statements",
        name="Senate interests API: query statements",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="interests_register_api",
        url=f"{api_base_url}/queryStatements?{query}",
        expected_format="json",
        update_frequency="ongoing",
        priority="core",
        notes="Public JSON endpoint used by the official APH Senate Register of Senators' Interests page.",
    )


def _source_for_statement_detail(api_base_url: str, cdap_id: str, senator_name: str) -> SourceRecord:
    return SourceRecord(
        source_id=f"aph_senators_interests_api_statement__{cdap_id}",
        name=f"Senate interests API: statement detail for {senator_name}",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="interests_register_api_detail",
        url=f"{api_base_url}/getSenatorStatement?cdapid={cdap_id}",
        expected_format="json",
        update_frequency="ongoing",
        priority="core",
        notes="Public JSON detail endpoint used by the official APH Senate Register of Senators' Interests page.",
    )


def fetch_senate_interest_statements(
    *,
    limit: int | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    env_metadata_path = _fetch_senate_env()
    api_base_url = parse_senate_env_api_base(
        _metadata_body_path(env_metadata_path).read_text(encoding="utf-8", errors="replace")
    )

    query_metadata_path = fetch_source(_source_for_query_statements(api_base_url))
    query_payload = json.loads(_metadata_body_path(query_metadata_path).read_text(encoding="utf-8"))
    statements = query_payload.get("statementOfRegisterableInterests", [])
    if limit is not None:
        statements = statements[:limit]

    detail_metadata_paths: list[str] = []
    for statement in statements:
        detail_source = _source_for_statement_detail(
            api_base_url=api_base_url,
            cdap_id=str(statement["cdapId"]),
            senator_name=str(statement["name"]),
        )
        detail_metadata_paths.append(str(fetch_source(detail_source)))

    timestamp = _timestamp()
    target_dir = processed_dir / "senate_interest_api_fetches"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "api_base_url": api_base_url,
        "env_metadata_path": str(env_metadata_path),
        "query_metadata_path": str(query_metadata_path),
        "statement_count_available": query_payload.get("totalResults") or len(
            query_payload.get("statementOfRegisterableInterests", [])
        ),
        "statement_count_fetched": len(detail_metadata_paths),
        "limit": limit,
        "detail_metadata_paths": detail_metadata_paths,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_senate_fetch_summary(processed_dir: Path = PROCESSED_DIR) -> Path:
    return _latest_file(processed_dir / "senate_interest_api_fetches", "*.summary.json")


def _humanize_field_name(field_name: str) -> str:
    words = re.sub(r"(?<!^)([A-Z])", r" \1", field_name).replace("_", " ")
    return words[:1].upper() + words[1:]


def _description_from_item(item: dict[str, Any]) -> str:
    parts = []
    for key, value in item.items():
        if key == "id" or value in ("", None):
            continue
        parts.append(f"{_humanize_field_name(key)}: {value}")
    return "; ".join(parts)


def _counterparty_from_item(item: dict[str, Any]) -> str:
    for key in COUNTERPARTY_FIELDS:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    provider = extract_provider("", fields={key: item.get(key) for key in BENEFIT_PROVIDER_TEXT_FIELDS})
    return str(provider["value"])


def _extracted_item_fields(item: dict[str, Any], description: str) -> dict[str, Any]:
    provider = extract_provider(
        description,
        fields={key: item.get(key) for key in BENEFIT_PROVIDER_TEXT_FIELDS},
    )
    reported_value = extract_reported_value(description)
    event_date = extract_event_date(description)
    return {
        "counterparty_raw_name": provider["value"],
        "counterparty_extraction": provider,
        "estimated_value": reported_value["value"],
        "estimated_value_currency": reported_value["currency"],
        "estimated_value_extraction": reported_value,
        "event_date": event_date["value"],
        "event_date_extraction": event_date,
        "reported_date": parse_iso_datetime_date(str(item.get("createdOn") or "")),
    }


def _flatten_statement_detail(metadata_path: Path) -> list[dict[str, Any]]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload = json.loads(Path(metadata["body_path"]).read_text(encoding="utf-8"))
    statement = payload.get("senatorInterestStatement") or {}
    cdap_id = metadata["source"]["source_id"].split("__")[-1]

    records: list[dict[str, Any]] = []
    for category_key, category_label in SENATE_INTEREST_CATEGORIES.items():
        category_payload = payload.get(category_key) or {}
        for record_type in ("interests", "alterations"):
            items = category_payload.get(record_type) or []
            for index, item in enumerate(items, start=1):
                item_id = item.get("id") or f"{record_type}_{index}"
                description = _description_from_item(item)
                extracted = _extracted_item_fields(item, description)
                records.append(
                    {
                        "external_key": (
                            f"aph_senate_interests:{cdap_id}:{category_key}:"
                            f"{record_type}:{item_id}"
                        ),
                        "source_id": metadata["source"]["source_id"],
                        "source_name": metadata["source"]["name"],
                        "source_metadata_path": str(metadata_path),
                        "url": metadata["source"]["url"],
                        "cdap_id": cdap_id,
                        "senator_name": statement.get("senatorName", ""),
                        "senator_title": statement.get("senatorTitle", ""),
                        "senator_post_nominal": statement.get("senatorPostNominal", ""),
                        "senator_party": statement.get("senatorParty", ""),
                        "state": statement.get("electorateState", ""),
                        "lodgement_date": statement.get("lodgementDate", ""),
                        "last_date_updated": statement.get("lastDateUpdated", ""),
                        "interest_category": category_key,
                        "interest_category_label": category_label,
                        "record_type": record_type.rstrip("s"),
                        "interest_id": item_id,
                        "counterparty_raw_name": extracted["counterparty_raw_name"]
                        or _counterparty_from_item(item),
                        "description": description,
                        "counterparty_extraction": extracted["counterparty_extraction"],
                        "estimated_value": extracted["estimated_value"],
                        "estimated_value_currency": extracted["estimated_value_currency"],
                        "estimated_value_extraction": extracted["estimated_value_extraction"],
                        "event_date": extracted["event_date"],
                        "event_date_extraction": extracted["event_date_extraction"],
                        "reported_date": extracted["reported_date"],
                        "original": item,
                    }
                )
    return records


def extract_senate_interest_records(
    fetch_summary_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if fetch_summary_path is None:
        fetch_summary_path = latest_senate_fetch_summary(processed_dir=processed_dir)

    fetch_summary = json.loads(fetch_summary_path.read_text(encoding="utf-8"))
    detail_paths = [Path(path) for path in fetch_summary["detail_metadata_paths"]]

    timestamp = _timestamp()
    target_dir = processed_dir / "senate_interest_records"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    record_count = 0
    statement_count = 0
    category_counts = {category: 0 for category in SENATE_INTEREST_CATEGORIES}
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for metadata_path in detail_paths:
            records = _flatten_statement_detail(metadata_path)
            statement_count += 1
            for record in records:
                category_counts[record["interest_category"]] += 1
                record_count += 1
                handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_fetch_summary_path": str(fetch_summary_path),
        "jsonl_path": str(jsonl_path),
        "statement_count": statement_count,
        "record_count": record_count,
        "category_counts": category_counts,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
