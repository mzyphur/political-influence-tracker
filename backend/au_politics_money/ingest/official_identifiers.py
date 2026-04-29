from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import time
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.sources import get_source


OFFICIAL_IDENTIFIER_SCHEMA_VERSION = "official_identifier_record_v1"
OFFICIAL_IDENTIFIER_PARSER_NAME = "official_identifier_enrichment_v1"
LOBBYIST_API_BASE = "https://api.lobbyists.ag.gov.au/"
ABN_LOOKUP_WEB_SERVICE_BASE = "https://abr.business.gov.au/ABRXMLSearch/AbrXmlSearch.asmx"
ABN_LOOKUP_WEB_METHODS: dict[str, str] = {
    "abn": "SearchByABNv202001",
    "acn": "SearchByASICv201408",
}
ABN_LOOKUP_TRADING_NAME_CAVEAT = (
    "The ABR stopped collecting or updating trading names in May 2012; any trading "
    "names in ABN Lookup responses are historical reference only and have no legal status."
)

DATA_GOV_PACKAGES: tuple[dict[str, Any], ...] = (
    {
        "source_id": "asic_companies_dataset",
        "package_id": "asic-companies",
        "canonical_package_id": "7b8656f9-606d-4337-af29-66b89b2eeefb",
        "landing_page": "https://data.gov.au/data/dataset/asic-companies",
        "resource_hints": ("Company Dataset - Current",),
    },
    {
        "source_id": "acnc_register",
        "package_id": "acnc-register",
        "canonical_package_id": "b050b242-4487-4306-abf5-07ca073e5594",
        "landing_page": "https://data.gov.au/data/dataset/acnc-register",
        "resource_hints": ("ACNC Register of Australian charities CSV",),
    },
    {
        "source_id": "abn_lookup",
        "package_id": "abn-bulk-extract",
        "canonical_package_id": "5bd7fcab-e315-42cb-8daf-50b7efc2027e",
        "landing_page": "https://data.gov.au/data/dataset/abn-bulk-extract",
        "resource_hints": ("ABN Bulk Extract Resource List", "ABN Bulk Extract Part"),
    },
)
DATA_GOV_PACKAGE_BY_SOURCE_ID = {
    str(package["source_id"]): package for package in DATA_GOV_PACKAGES
}
OFFICIAL_IDENTIFIER_BULK_SOURCE_IDS = tuple(DATA_GOV_PACKAGE_BY_SOURCE_ID)
OFFICIAL_IDENTIFIER_SUPPORTED_EXTENSIONS = {
    "asic_companies_dataset": {".csv", ".zip"},
    "acnc_register": {".csv", ".zip"},
    "abn_lookup": {".xml", ".zip"},
}

ANZSIC_SECTIONS: tuple[dict[str, str], ...] = (
    {"code": "A", "label": "Agriculture, Forestry and Fishing"},
    {"code": "B", "label": "Mining"},
    {"code": "C", "label": "Manufacturing"},
    {"code": "D", "label": "Electricity, Gas, Water and Waste Services"},
    {"code": "E", "label": "Construction"},
    {"code": "F", "label": "Wholesale Trade"},
    {"code": "G", "label": "Retail Trade"},
    {"code": "H", "label": "Accommodation and Food Services"},
    {"code": "I", "label": "Transport, Postal and Warehousing"},
    {"code": "J", "label": "Information Media and Telecommunications"},
    {"code": "K", "label": "Financial and Insurance Services"},
    {"code": "L", "label": "Rental, Hiring and Real Estate Services"},
    {"code": "M", "label": "Professional, Scientific and Technical Services"},
    {"code": "N", "label": "Administrative and Support Services"},
    {"code": "O", "label": "Public Administration and Safety"},
    {"code": "P", "label": "Education and Training"},
    {"code": "Q", "label": "Health Care and Social Assistance"},
    {"code": "R", "label": "Arts and Recreation Services"},
    {"code": "S", "label": "Other Services"},
)


@dataclass(frozen=True)
class Identifier:
    identifier_type: str
    identifier_value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "identifier_type": self.identifier_type,
            "identifier_value": self.identifier_value,
        }


class MissingAbnLookupGuid(RuntimeError):
    pass


class AbnLookupWebServiceError(RuntimeError):
    pass


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def normalize_name(value: str) -> str:
    lowered = (value or "").lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _digits(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def is_valid_abn(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 11:
        return False
    weights = (10, 1, 3, 5, 7, 9, 11, 13, 15, 17, 19)
    values = [int(digit) for digit in digits]
    values[0] -= 1
    return sum(weight * digit for weight, digit in zip(weights, values, strict=True)) % 89 == 0


def format_abn(value: str) -> str:
    digits = _digits(value)
    if len(digits) != 11:
        return digits
    return f"{digits[:2]} {digits[2:5]} {digits[5:8]} {digits[8:]}"


def is_valid_acn(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 9:
        return False
    weights = (8, 7, 6, 5, 4, 3, 2, 1)
    total = sum(int(digit) * weight for digit, weight in zip(digits[:8], weights, strict=True))
    check_digit = (10 - (total % 10)) % 10
    return check_digit == int(digits[-1])


def format_acn(value: str) -> str:
    digits = _digits(value)
    if len(digits) != 9:
        return digits
    return f"{digits[:3]} {digits[3:6]} {digits[6:]}"


def _identifier(identifier_type: str, value: str) -> Identifier | None:
    if identifier_type == "abn":
        return Identifier("abn", format_abn(value)) if is_valid_abn(value) else None
    if identifier_type == "acn":
        return Identifier("acn", format_acn(value)) if is_valid_acn(value) else None
    cleaned = " ".join((value or "").split())
    return Identifier(identifier_type, cleaned) if cleaned else None


def _stable_key(source_id: str, source_record_type: str, external_id: str, display_name: str) -> str:
    stable_record_id = external_id or normalize_name(display_name)
    seed = "|".join([source_id, source_record_type, stable_record_id])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"{source_id}:{source_record_type}:{digest}"


def _record(
    *,
    source_id: str,
    source_record_type: str,
    display_name: str,
    source_metadata_path: str,
    external_id: str = "",
    entity_type: str = "unknown",
    identifiers: Iterable[Identifier | None] = (),
    aliases: Iterable[str] = (),
    public_sector: str = "unknown",
    official_classification: str = "",
    status: str = "",
    source_updated_at: str = "",
    evidence_note: str = "",
    raw_record: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cleaned_name = " ".join((display_name or "").split())
    identifier_dicts = [
        item.to_dict() for item in identifiers if item is not None and item.identifier_value
    ]
    alias_values = sorted(
        {
            " ".join(alias.split())
            for alias in aliases
            if alias and normalize_name(alias) != normalize_name(cleaned_name)
        }
    )
    return {
        "schema_version": OFFICIAL_IDENTIFIER_SCHEMA_VERSION,
        "parser_name": OFFICIAL_IDENTIFIER_PARSER_NAME,
        "source_id": source_id,
        "source_record_type": source_record_type,
        "external_id": external_id,
        "stable_key": _stable_key(source_id, source_record_type, external_id, cleaned_name),
        "display_name": cleaned_name,
        "normalized_name": normalize_name(cleaned_name),
        "entity_type": entity_type,
        "identifiers": identifier_dicts,
        "aliases": alias_values,
        "public_sector": public_sector,
        "official_classification": official_classification,
        "confidence": "exact_name_context",
        "status": status,
        "source_updated_at": source_updated_at,
        "evidence_note": evidence_note,
        "source_metadata_path": source_metadata_path,
        "raw_record": raw_record or {},
        "metadata": metadata or {},
    }


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_input_file_metadata(source_id: str, input_path: Path, raw_dir: Path = RAW_DIR) -> Path:
    source = get_source(source_id)
    run_ts = _timestamp()
    target_dir = raw_dir / source_id / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)
    body_path = target_dir / f"body{input_path.suffix or '.bin'}"
    shutil.copy2(input_path, body_path)
    metadata = {
        "source": source.to_dict(),
        "fetched_at": run_ts,
        "ok": True,
        "http_status": None,
        "final_url": source.url,
        "content_type": None,
        "content_length": body_path.stat().st_size,
        "sha256": _sha256_path(body_path),
        "body_path": str(body_path.resolve()),
        "headers": {},
        "metadata_kind": "local_official_extract_input",
        "original_input_path": str(input_path.resolve()),
    }
    return _write_json(target_dir / "metadata.json", metadata)


def _abn_lookup_guid() -> str:
    value = (os.environ.get("ABN_LOOKUP_GUID") or "").strip()
    if not value or value.lower() == "your_abn_lookup_guid_here":
        raise MissingAbnLookupGuid(
            "ABN_LOOKUP_GUID is required for ABN Lookup web-service enrichment. "
            "Store it in backend/.env and run commands through dotenv."
        )
    return value


def _abn_lookup_endpoint(method: str) -> str:
    return f"{ABN_LOOKUP_WEB_SERVICE_BASE}/{method}"


def _abn_lookup_request_params(
    *,
    lookup_value: str,
    include_historical_details: bool,
    authentication_guid: str,
) -> dict[str, str]:
    return {
        "searchString": lookup_value,
        "includeHistoricalDetails": "Y" if include_historical_details else "N",
        "authenticationGuid": authentication_guid,
    }


def _redact_abn_lookup_params(params: dict[str, str]) -> dict[str, str]:
    return {
        key: ("redacted" if key.lower() == "authenticationguid" else value)
        for key, value in params.items()
    }


def _open_bytes_with_retries(
    request: Request,
    *,
    timeout: int = 60,
    tries: int = 4,
) -> tuple[bytes, int | None, dict[str, str]]:
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            with urlopen(request, timeout=timeout) as response:
                headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.lower() in {"content-type", "content-length", "date"}
                }
                return response.read(), getattr(response, "status", None), headers
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == tries - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(delay)
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"Request failed after retries: {last_error!r}")


def _abn_lookup_identifier_slug(lookup_type: str, lookup_value: str) -> str:
    digits = _digits(lookup_value)
    return f"{lookup_type}_{digits or normalize_name(lookup_value).replace(' ', '_')}"


def _redact_secret_bytes(body: bytes, secret: str, marker: bytes) -> bytes:
    redacted = body
    for variant in {secret, quote(secret, safe=""), quote_plus(secret)}:
        if variant:
            redacted = redacted.replace(variant.encode("utf-8"), marker)
    return redacted


def _ckan_package_url(package_id: str) -> str:
    return f"https://data.gov.au/data/api/3/action/package_show?id={package_id}"


def _read_json_url(url: str, timeout: int = 60) -> dict[str, Any]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def discover_official_identifier_sources(processed_dir: Path = PROCESSED_DIR) -> Path:
    timestamp = _timestamp()
    packages: list[dict[str, Any]] = []
    for package in DATA_GOV_PACKAGES:
        result: dict[str, Any] = {
            "source_id": package["source_id"],
            "package_id": package["package_id"],
            "canonical_package_id": package["canonical_package_id"],
            "landing_page": package["landing_page"],
            "resource_hints": list(package["resource_hints"]),
            "ckan_url": _ckan_package_url(package["canonical_package_id"]),
            "ok": False,
            "resources": [],
        }
        try:
            payload = _read_json_url(result["ckan_url"])
            result["ok"] = bool(payload.get("success"))
            ckan_result = payload.get("result", {})
            result["title"] = ckan_result.get("title") or ckan_result.get("name")
            result["metadata_modified"] = ckan_result.get("metadata_modified")
            result["resources"] = [
                {
                    "id": resource.get("id"),
                    "name": resource.get("name"),
                    "format": resource.get("format"),
                    "url": resource.get("url"),
                    "size": resource.get("size"),
                    "last_modified": resource.get("last_modified"),
                    "mimetype": resource.get("mimetype"),
                }
                for resource in ckan_result.get("resources", [])
            ]
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            try:
                fallback_url = _ckan_package_url(package["package_id"])
                payload = _read_json_url(fallback_url)
                result["ckan_url"] = fallback_url
                result["ok"] = bool(payload.get("success"))
                ckan_result = payload.get("result", {})
                result["title"] = ckan_result.get("title") or ckan_result.get("name")
                result["metadata_modified"] = ckan_result.get("metadata_modified")
                result["resources"] = [
                    {
                        "id": resource.get("id"),
                        "name": resource.get("name"),
                        "format": resource.get("format"),
                        "url": resource.get("url"),
                        "size": resource.get("size"),
                        "last_modified": resource.get("last_modified"),
                        "mimetype": resource.get("mimetype"),
                    }
                    for resource in ckan_result.get("resources", [])
                ]
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as fallback_exc:
                result["error"] = repr(fallback_exc)
                result["canonical_error"] = repr(exc)
        packages.append(result)

    payload = {
        "generated_at": timestamp,
        "parser_name": OFFICIAL_IDENTIFIER_PARSER_NAME,
        "packages": packages,
        "lobbyist_register": {
            "source_id": "australian_lobbyists_register",
            "landing_page": "https://www.ag.gov.au/integrity/australian-government-register-lobbyists",
            "public_app": "https://lobbyists.ag.gov.au/register",
            "api_base": LOBBYIST_API_BASE,
            "search_endpoints": [
                "search/organisations",
                "search/lobbyists",
                "search/clients",
                "search/all",
            ],
        },
        "anzsic": {
            "source_id": "abs_anzsic",
            "landing_page": (
                "https://www.abs.gov.au/statistics/classifications/"
                "australian-and-new-zealand-standard-industrial-classification-anzsic"
            ),
            "seeded_sections": ANZSIC_SECTIONS,
        },
    }
    output_path = _write_json(
        processed_dir / "official_identifier_sources" / f"{timestamp}.json",
        payload,
    )
    failed = [package["source_id"] for package in packages if not package.get("ok")]
    if failed:
        raise RuntimeError(
            f"Official identifier source discovery failed for {failed}; artifact: {output_path}"
        )
    return output_path


def latest_official_identifier_sources_path(processed_dir: Path = PROCESSED_DIR) -> Path:
    source_dir = processed_dir / "official_identifier_sources"
    candidates = sorted(source_dir.glob("*.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError("No official identifier source discovery artifact found.")
    return candidates[0]


def _resource_text(resource: dict[str, Any]) -> str:
    return " ".join(
        str(resource.get(key) or "")
        for key in ("name", "format", "mimetype", "url")
    ).lower()


def _resource_suffix(resource: dict[str, Any]) -> str:
    url = str(resource.get("url") or "").split("?", maxsplit=1)[0].lower()
    for suffix in (".zip", ".csv", ".xml", ".txt"):
        if url.endswith(suffix):
            return suffix
    resource_format = str(resource.get("format") or "").strip().lower()
    if resource_format in {"zip", "csv", "xml"}:
        return f".{resource_format}"
    return ".bin"


def _resource_supported_for_source(source_id: str, resource: dict[str, Any]) -> bool:
    url = str(resource.get("url") or "").strip()
    if not url.lower().startswith(("https://", "http://")):
        return False
    supported = OFFICIAL_IDENTIFIER_SUPPORTED_EXTENSIONS[source_id]
    return _resource_suffix(resource) in supported


def _resource_hint_score(source_id: str, resource: dict[str, Any]) -> int:
    package = DATA_GOV_PACKAGE_BY_SOURCE_ID[source_id]
    text = _resource_text(resource)
    score = 0
    for hint in package["resource_hints"]:
        hint_text = str(hint).lower()
        if hint_text and hint_text in text:
            score += 100
    if "current" in text:
        score += 15
    if _resource_supported_for_source(source_id, resource):
        score += 25
    if source_id == "abn_lookup":
        if "part" in text and "resource list" not in text:
            score += 100
        if "resource list" in text:
            score -= 200
    return score


def select_official_identifier_bulk_resources(
    discovery_payload: dict[str, Any],
    *,
    source_ids: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    requested_source_ids = set(source_ids or OFFICIAL_IDENTIFIER_BULK_SOURCE_IDS)
    unsupported = requested_source_ids - set(OFFICIAL_IDENTIFIER_BULK_SOURCE_IDS)
    if unsupported:
        raise ValueError(f"Unsupported official identifier bulk sources: {sorted(unsupported)}")

    selected: list[dict[str, Any]] = []
    for package in discovery_payload.get("packages", []):
        source_id = package.get("source_id")
        if source_id not in requested_source_ids:
            continue
        candidates = [
            {
                "source_id": source_id,
                "package_id": package.get("package_id"),
                "canonical_package_id": package.get("canonical_package_id"),
                "resource": resource,
                "selection_score": _resource_hint_score(source_id, resource),
                "selection_reason": "",
            }
            for resource in package.get("resources", [])
            if _resource_supported_for_source(source_id, resource)
        ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda item: (
                item["selection_score"],
                str(item["resource"].get("last_modified") or ""),
                str(item["resource"].get("name") or ""),
            ),
            reverse=True,
        )
        if source_id == "abn_lookup":
            abn_parts = [
                item
                for item in candidates
                if "part" in _resource_text(item["resource"])
                and "resource list" not in _resource_text(item["resource"])
            ]
            abn_parts.sort(
                key=lambda item: (
                    str(item["resource"].get("name") or ""),
                    str(item["resource"].get("id") or ""),
                )
            )
            chosen = abn_parts or candidates[:1]
            for item in chosen:
                item["selection_reason"] = "abn_bulk_part_resource"
                selected.append(item)
            continue
        candidates[0]["selection_reason"] = "highest_scoring_supported_resource"
        selected.append(candidates[0])
    return selected


def _download_official_identifier_resource(
    item: dict[str, Any],
    *,
    timestamp: str,
    raw_dir: Path,
    timeout: int,
) -> dict[str, Any]:
    source_id = item["source_id"]
    resource = item["resource"]
    source = get_source(source_id)
    resource_id = str(resource.get("id") or normalize_name(resource.get("name") or "resource"))
    resource_slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", resource_id).strip("_") or "resource"
    target_dir = raw_dir / source_id / timestamp / resource_slug
    target_dir.mkdir(parents=True, exist_ok=True)

    request = Request(
        str(resource["url"]),
        headers={"Accept": "*/*", "User-Agent": USER_AGENT},
    )
    body, http_status, headers = _open_bytes_with_retries(request, timeout=timeout)
    body_path = target_dir / f"body{_resource_suffix(resource)}"
    body_path.write_bytes(body)
    metadata_path = _write_json(
        target_dir / "metadata.json",
        {
            "source": source.to_dict(),
            "fetched_at": timestamp,
            "ok": http_status is None or 200 <= http_status < 400,
            "http_status": http_status,
            "final_url": resource["url"],
            "content_type": headers.get("Content-Type") or headers.get("content-type"),
            "content_length": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "body_path": str(body_path.resolve()),
            "headers": headers,
            "metadata_kind": "data_gov_official_identifier_resource",
            "data_gov_package_id": item.get("package_id"),
            "data_gov_canonical_package_id": item.get("canonical_package_id"),
            "data_gov_resource": resource,
            "selection_score": item.get("selection_score"),
            "selection_reason": item.get("selection_reason"),
        },
    )
    return {
        **item,
        "body_path": body_path,
        "source_metadata_path": metadata_path,
    }


def _iter_records_for_download(
    source_id: str,
    body_path: Path,
    source_metadata_path: Path,
    *,
    remaining_limit: int | None,
) -> Iterator[dict[str, Any]]:
    if source_id == "asic_companies_dataset":
        yield from iter_asic_company_records(
            body_path,
            source_metadata_path,
            limit=remaining_limit,
        )
    elif source_id == "acnc_register":
        yield from iter_acnc_charity_records(
            body_path,
            source_metadata_path,
            limit=remaining_limit,
        )
    elif source_id == "abn_lookup":
        yield from iter_abn_bulk_records(
            body_path,
            source_metadata_path,
            limit=remaining_limit,
        )
    else:
        raise ValueError(f"Unsupported official identifier bulk source: {source_id}")


def fetch_official_identifier_bulk_resources(
    *,
    source_ids: Iterable[str] | None = None,
    discovery_path: Path | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    extract_limit_per_source: int | None = None,
    timeout: int = 60,
) -> Path:
    if extract_limit_per_source is not None and extract_limit_per_source < 1:
        raise ValueError("extract_limit_per_source must be positive when supplied.")
    requested_source_ids_arg = tuple(source_ids) if source_ids is not None else None
    timestamp = _timestamp()
    if discovery_path is None:
        try:
            discovery_path = latest_official_identifier_sources_path(processed_dir)
        except FileNotFoundError:
            discovery_path = discover_official_identifier_sources(processed_dir)

    discovery_payload = json.loads(discovery_path.read_text(encoding="utf-8"))
    selected = select_official_identifier_bulk_resources(
        discovery_payload,
        source_ids=requested_source_ids_arg,
    )
    requested_source_ids = set(requested_source_ids_arg or OFFICIAL_IDENTIFIER_BULK_SOURCE_IDS)
    selected_source_ids = {item["source_id"] for item in selected}
    missing_source_ids = sorted(requested_source_ids - selected_source_ids)
    if missing_source_ids:
        raise RuntimeError(
            f"No supported data.gov resources selected for {missing_source_ids}; "
            f"discovery artifact: {discovery_path}"
        )

    downloads = [
        _download_official_identifier_resource(
            item,
            timestamp=timestamp,
            raw_dir=raw_dir,
            timeout=timeout,
        )
        for item in selected
    ]

    jsonl_paths: list[str] = []
    source_summaries: dict[str, dict[str, Any]] = {}
    for source_id in sorted(selected_source_ids):
        source_downloads = [item for item in downloads if item["source_id"] == source_id]

        def records_for_source() -> Iterator[dict[str, Any]]:
            yielded = 0
            for item in source_downloads:
                remaining = (
                    None
                    if extract_limit_per_source is None
                    else max(extract_limit_per_source - yielded, 0)
                )
                if remaining == 0:
                    break
                for record in _iter_records_for_download(
                    source_id,
                    item["body_path"],
                    item["source_metadata_path"],
                    remaining_limit=remaining,
                ):
                    yielded += 1
                    yield record

        artifact_id = f"{timestamp}_{source_id}_bulk"
        jsonl_path = write_official_identifier_records(
            records_for_source(),
            processed_dir=processed_dir,
            artifact_id=artifact_id,
        )
        jsonl_paths.append(str(jsonl_path))
        source_summary_path = jsonl_path.with_suffix(".summary.json")
        source_summaries[source_id] = json.loads(
            source_summary_path.read_text(encoding="utf-8")
        )

    summary_path = _write_json(
        processed_dir / "official_identifier_bulk_fetches" / f"{timestamp}.summary.json",
        {
            "generated_at": timestamp,
            "source_ids": sorted(selected_source_ids),
            "requested_source_ids": sorted(requested_source_ids),
            "discovery_path": str(discovery_path),
            "extract_limit_per_source": extract_limit_per_source,
            "selected_resources": [
                {
                    "source_id": item["source_id"],
                    "resource_id": item["resource"].get("id"),
                    "resource_name": item["resource"].get("name"),
                    "resource_url": item["resource"].get("url"),
                    "selection_score": item.get("selection_score"),
                    "selection_reason": item.get("selection_reason"),
                }
                for item in selected
            ],
            "downloaded_resources": [
                {
                    "source_id": item["source_id"],
                    "resource_id": item["resource"].get("id"),
                    "body_path": str(item["body_path"]),
                    "source_metadata_path": str(item["source_metadata_path"]),
                }
                for item in downloads
            ],
            "official_identifiers_jsonl_paths": jsonl_paths,
            "source_summaries": source_summaries,
        },
    )
    return summary_path


def _canonical_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")


def _normalise_row(row: dict[str, str]) -> dict[str, str]:
    return {_canonical_header(key): (value or "").strip() for key, value in row.items()}


def _field(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(_canonical_header(name), "")
        if value:
            return value
    return ""


def _dict_reader(text) -> csv.DictReader:
    sample = text.read(8192)
    text.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(text, dialect=dialect)


def _csv_rows_from_path(path: Path) -> Iterator[dict[str, str]]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
            if not names:
                raise ValueError(f"No CSV files found in {path}")
            with archive.open(sorted(names)[0]) as raw_handle:
                text = io.TextIOWrapper(raw_handle, encoding="utf-8-sig", errors="replace")
                for row in _dict_reader(text):
                    yield _normalise_row(row)
        return

    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
        for row in _dict_reader(handle):
            yield _normalise_row(row)


def iter_asic_company_records(
    input_path: Path,
    source_metadata_path: Path,
    *,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    seen = 0
    for row in _csv_rows_from_path(input_path):
        name = _field(row, "company_name", "company name", "current_name", "current name")
        if not name:
            continue
        acn = _field(row, "acn")
        abn = _field(row, "abn")
        yield _record(
            source_id="asic_companies_dataset",
            source_record_type="asic_company",
            display_name=name,
            external_id=_digits(acn) or normalize_name(name),
            entity_type="company",
            identifiers=(_identifier("acn", acn), _identifier("abn", abn)),
            aliases=(_field(row, "current name", "current_name"),),
            status=_field(row, "status"),
            source_updated_at=_field(row, "modified since last report"),
            evidence_note="ASIC Company Dataset exact register extract record.",
            source_metadata_path=str(source_metadata_path),
            raw_record=row,
        )
        seen += 1
        if limit is not None and seen >= limit:
            return


def _split_aliases(value: str) -> list[str]:
    if not value:
        return []
    return [
        " ".join(item.split())
        for item in re.split(r"\s*(?:;|\||\n)\s*", value)
        if " ".join(item.split())
    ]


def iter_acnc_charity_records(
    input_path: Path,
    source_metadata_path: Path,
    *,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    seen = 0
    for row in _csv_rows_from_path(input_path):
        name = _field(row, "charity_legal_name")
        if not name:
            continue
        abn = _field(row, "abn")
        aliases = _split_aliases(_field(row, "other_organisation_names"))
        purposes = [
            key for key, value in row.items() if value.strip().upper() == "Y" and key.startswith("advancing")
        ]
        yield _record(
            source_id="acnc_register",
            source_record_type="acnc_charity",
            display_name=name,
            external_id=_digits(abn) or normalize_name(name),
            entity_type="charity",
            identifiers=(_identifier("abn", abn),),
            aliases=aliases,
            public_sector="charities_nonprofits",
            official_classification="ACNC registered charity",
            status="registered",
            evidence_note="ACNC Charity Register record.",
            source_metadata_path=str(source_metadata_path),
            raw_record=row,
            metadata={
                "charity_size": _field(row, "charity_size"),
                "charity_website": _field(row, "charity_website"),
                "pbi": _field(row, "pbi"),
                "hpc": _field(row, "hpc"),
                "purpose_flags": purposes,
            },
        )
        seen += 1
        if limit is not None and seen >= limit:
            return


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _child_texts(element: ElementTree.Element, local_names: set[str]) -> list[str]:
    target_names = {name.lower() for name in local_names}
    values: list[str] = []
    for child in element.iter():
        if _local_name(child.tag).lower() in target_names and child.text:
            values.append(" ".join(child.text.split()))
    return values


def _first_child_text(element: ElementTree.Element, local_names: set[str]) -> str:
    values = _child_texts(element, local_names)
    return values[0] if values else ""


def _first_attr(element: ElementTree.Element, attr_names: set[str]) -> str:
    target_names = {name.lower() for name in attr_names}
    for child in element.iter():
        for key, value in child.attrib.items():
            if _local_name(key).lower() in target_names and value:
                return " ".join(value.split())
    return ""


def _first_identifier_value(
    element: ElementTree.Element,
    container_names: set[str],
    value_names: set[str] = frozenset({"identifierValue"}),
) -> str:
    target_containers = {name.lower() for name in container_names}
    for child in element.iter():
        if _local_name(child.tag).lower() not in target_containers:
            continue
        direct_text = " ".join((child.text or "").split())
        if _digits(direct_text):
            return direct_text
        nested = _first_child_text(child, set(value_names))
        if nested:
            return nested
    return ""


def _is_current_effective_to(value: str) -> bool:
    cleaned = (value or "").strip()
    return not cleaned or cleaned.startswith("0001-01-01") or cleaned.startswith("9999-12-31")


def _abn_name_observations(element: ElementTree.Element) -> list[dict[str, Any]]:
    container_names = {
        "mainentity",
        "mainname",
        "businessname",
        "maintradingname",
        "othertradingname",
        "legalname",
    }
    name_value_tags = {
        "NonIndividualNameText",
        "BusinessNameText",
        "TradingNameText",
        "OrganisationName",
        "organisationName",
    }
    observations: list[dict[str, Any]] = []
    for child in element.iter():
        container_name = _local_name(child.tag)
        container_name_key = container_name.lower()
        if container_name_key not in container_names:
            continue
        values = _child_texts(child, name_value_tags)
        if not values:
            continue
        effective_to = _first_child_text(child, {"effectiveTo"})
        effective_from = _first_child_text(child, {"effectiveFrom"})
        is_trading_name = "trading" in container_name_key
        for value in values:
            observations.append(
                {
                    "name": value,
                    "name_type": container_name_key,
                    "effective_from": effective_from,
                    "effective_to": effective_to,
                    "is_current": _is_current_effective_to(effective_to),
                    "is_trading_name": is_trading_name,
                    "legal_status_caveat": ABN_LOOKUP_TRADING_NAME_CAVEAT
                    if is_trading_name
                    else "",
                }
            )
    return observations


def _abn_current_display_name_and_aliases(
    element: ElementTree.Element,
) -> tuple[str, list[str], list[dict[str, Any]]]:
    name_observations = _abn_name_observations(element)
    current_non_trading = [
        item for item in name_observations if item["is_current"] and not item["is_trading_name"]
    ]
    display_candidates = [
        item
        for item in current_non_trading
        if item["name_type"] in {"mainentity", "mainname", "legalname"}
    ]
    if not display_candidates:
        display_candidates = current_non_trading
    if not display_candidates:
        display_candidates = [
            item for item in name_observations if not item["is_trading_name"]
        ] or name_observations

    display_name = display_candidates[0]["name"] if display_candidates else ""
    aliases: list[str] = []
    seen = {normalize_name(display_name)} if display_name else set()
    for item in current_non_trading:
        normalized_alias = normalize_name(item["name"])
        if normalized_alias and normalized_alias not in seen:
            aliases.append(item["name"])
            seen.add(normalized_alias)
    return display_name, aliases, name_observations


def _iter_abn_xml_elements(input_path: Path) -> Iterator[ElementTree.Element]:
    if zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            for name in sorted(names):
                with archive.open(name) as raw_handle:
                    yield from _iter_abn_element_stream(raw_handle)
        return
    with input_path.open("rb") as handle:
        yield from _iter_abn_element_stream(handle)


def _iter_abn_element_stream(raw_handle) -> Iterator[ElementTree.Element]:
    record_tags = {
        "abr",
        "abrrecord",
        "businessentity",
        "businessentity200506",
        "businessentity200709",
        "businessentity201205",
        "businessentity201408",
        "businessentity202001",
    }
    for _event, element in ElementTree.iterparse(raw_handle, events=("end",)):
        if _local_name(element.tag).lower() in record_tags:
            yield element
            element.clear()


def iter_abn_bulk_records(
    input_path: Path,
    source_metadata_path: Path,
    *,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    seen = 0
    for element in _iter_abn_xml_elements(input_path):
        abn = _first_identifier_value(element, {"ABN"}) or _first_child_text(element, {"ABN"})
        names = _child_texts(
            element,
            {
                "NonIndividualNameText",
                "BusinessNameText",
                "TradingNameText",
                "OrganisationName",
                "organisationName",
            },
        )
        individual_given = _first_child_text(element, {"GivenName", "givenName"})
        individual_family = _first_child_text(element, {"FamilyName", "Surname", "familyName"})
        if not names and (individual_given or individual_family):
            names = [" ".join(part for part in (individual_given, individual_family) if part)]
        name = names[0] if names else ""
        if not name:
            continue
        acn = _first_identifier_value(element, {"ASICNumber", "ACN", "ARBN", "ARSN"})
        if not acn:
            acn = _first_child_text(element, {"ASICNumber", "ACN", "ARBN", "ARSN"})
        entity_type_text = _first_attr(element, {"EntityTypeText"}) or _first_child_text(
            element,
            {"EntityTypeText", "EntityTypeInd", "entityDescription", "entityTypeDescription"},
        )
        state = _first_child_text(element, {"StateCode", "stateCode"})
        postcode = _first_child_text(element, {"Postcode", "postcode"})
        status = (
            _first_attr(element, {"status"})
            or _first_attr(element, {"ABNStatus"})
            or _first_child_text(element, {"entityStatusCode", "ABNStatus"})
        )
        yield _record(
            source_id="abn_lookup",
            source_record_type="abn_bulk_entity",
            display_name=name,
            external_id=_digits(abn) or normalize_name(name),
            entity_type="company" if "company" in entity_type_text.lower() else "unknown",
            identifiers=(_identifier("abn", abn), _identifier("acn", acn)),
            aliases=names[1:],
            status=status,
            evidence_note="ABN Lookup Bulk Extract public register record.",
            source_metadata_path=str(source_metadata_path),
            raw_record=ElementTree.tostring(element, encoding="unicode"),
            metadata={
                "entity_type_text": entity_type_text,
                "state": state,
                "postcode": postcode,
                "trading_name_caveat": ABN_LOOKUP_TRADING_NAME_CAVEAT,
            },
        )
        seen += 1
        if limit is not None and seen >= limit:
            return


def _abn_lookup_response_context(input_path: Path) -> dict[str, Any]:
    try:
        root = ElementTree.parse(input_path).getroot()
    except ElementTree.ParseError:
        return {"parse_error": "response XML could not be parsed"}
    exceptions = [
        {
            "code": _first_child_text(child, {"exceptionCode"}),
            "description": _first_child_text(child, {"exceptionDescription"}),
        }
        for child in root.iter()
        if _local_name(child.tag).lower() == "exception"
    ]
    return {
        "usage_statement": _first_child_text(root, {"usageStatement"}),
        "date_register_last_updated": _first_child_text(root, {"dateRegisterLastUpdated"}),
        "date_time_retrieved": _first_child_text(root, {"dateTimeRetrieved"}),
        "exceptions": exceptions,
    }


def iter_abn_lookup_web_records(
    input_path: Path,
    source_metadata_path: Path,
    *,
    lookup_method: str,
    include_historical_details: bool,
    limit: int | None = None,
) -> Iterator[dict[str, Any]]:
    seen = 0
    response_context = _abn_lookup_response_context(input_path)
    for element in _iter_abn_xml_elements(input_path):
        abn = _first_identifier_value(element, {"ABN"}) or _first_child_text(element, {"ABN"})
        name, aliases, name_observations = _abn_current_display_name_and_aliases(element)
        individual_given = _first_child_text(element, {"GivenName", "givenName"})
        individual_family = _first_child_text(element, {"FamilyName", "Surname", "familyName"})
        if not name and (individual_given or individual_family):
            name = " ".join(part for part in (individual_given, individual_family) if part)
        if not name:
            continue
        acn = _first_identifier_value(element, {"ASICNumber", "ACN", "ARBN", "ARSN"})
        if not acn:
            acn = _first_child_text(element, {"ASICNumber", "ACN", "ARBN", "ARSN"})
        entity_type_text = _first_attr(element, {"EntityTypeText"}) or _first_child_text(
            element,
            {"EntityTypeText", "EntityTypeInd", "entityDescription", "entityTypeDescription"},
        )
        state = _first_child_text(element, {"StateCode", "stateCode"})
        postcode = _first_child_text(element, {"Postcode", "postcode"})
        status = (
            _first_attr(element, {"status"})
            or _first_attr(element, {"ABNStatus"})
            or _first_child_text(element, {"entityStatusCode", "ABNStatus"})
        )
        yield _record(
            source_id="abn_lookup",
            source_record_type="abn_web_service_entity",
            display_name=name,
            external_id=_digits(abn) or normalize_name(name),
            entity_type="company" if "company" in entity_type_text.lower() else "unknown",
            identifiers=(_identifier("abn", abn), _identifier("acn", acn)),
            aliases=aliases,
            status=status,
            evidence_note=(
                "ABN Lookup web-service record using the current public document-style method. "
                + ABN_LOOKUP_TRADING_NAME_CAVEAT
            ),
            source_metadata_path=str(source_metadata_path),
            raw_record=ElementTree.tostring(element, encoding="unicode"),
            metadata={
                "lookup_method": lookup_method,
                "include_historical_details": include_historical_details,
                "entity_type_text": entity_type_text,
                "state": state,
                "postcode": postcode,
                "trading_name_caveat": ABN_LOOKUP_TRADING_NAME_CAVEAT,
                "name_observations": name_observations,
                **response_context,
            },
        )
        seen += 1
        if limit is not None and seen >= limit:
            return


def fetch_abn_lookup_web_record(
    lookup_type: str,
    lookup_value: str,
    *,
    include_historical_details: bool = True,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    timeout: int = 60,
) -> Path:
    normalized_lookup_type = lookup_type.lower().strip()
    if normalized_lookup_type not in ABN_LOOKUP_WEB_METHODS:
        raise ValueError(f"Unsupported ABN Lookup web-service lookup type: {lookup_type}")
    search_value = _digits(lookup_value)
    if normalized_lookup_type == "abn" and not is_valid_abn(search_value):
        raise ValueError(f"Invalid ABN for ABN Lookup web-service search: {lookup_value!r}")
    if normalized_lookup_type == "acn" and not is_valid_acn(search_value):
        raise ValueError(f"Invalid ACN for ABN Lookup web-service search: {lookup_value!r}")

    timestamp = _timestamp()
    artifact_slug = _abn_lookup_identifier_slug(normalized_lookup_type, search_value)
    artifact_id = f"{timestamp}_{artifact_slug}"
    source = get_source("abn_lookup")
    method = ABN_LOOKUP_WEB_METHODS[normalized_lookup_type]
    endpoint = _abn_lookup_endpoint(method)
    guid = _abn_lookup_guid()
    request_params = _abn_lookup_request_params(
        lookup_value=search_value,
        include_historical_details=include_historical_details,
        authentication_guid=guid,
    )
    encoded_params = urlencode(request_params).encode("utf-8")
    request = Request(
        endpoint,
        data=encoded_params,
        headers={
            "Accept": "text/xml",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    body, http_status, headers = _open_bytes_with_retries(request, timeout=timeout)
    safe_body = _redact_secret_bytes(body, guid, b"REDACTED_ABN_LOOKUP_GUID")

    target_dir = raw_dir / "abn_lookup" / artifact_id
    target_dir.mkdir(parents=True, exist_ok=True)
    body_path = target_dir / f"{artifact_slug}.xml"
    body_path.write_bytes(safe_body)

    response_context = _abn_lookup_response_context(body_path)
    metadata_path = _write_json(
        target_dir / "metadata.json",
        {
            "source": source.to_dict(),
            "fetched_at": timestamp,
            "ok": http_status is None or 200 <= http_status < 400,
            "http_status": http_status,
            "final_url": endpoint,
            "content_type": headers.get("Content-Type") or headers.get("content-type"),
            "content_length": len(safe_body),
            "sha256": hashlib.sha256(safe_body).hexdigest(),
            "body_path": str(body_path.resolve()),
            "headers": headers,
            "metadata_kind": "abn_lookup_web_service_response",
            "lookup_type": normalized_lookup_type,
            "lookup_method": method,
            "lookup_method_documentation_url": (
                f"https://abr.business.gov.au/abrxmlsearch/Forms/{method}.aspx"
            ),
            "include_historical_details": include_historical_details,
            "request_params": _redact_abn_lookup_params(request_params),
            "response_context": response_context,
            "secret_handling": (
                "ABN_LOOKUP_GUID is read from the environment and omitted/redacted from "
                "stored metadata and raw responses."
            ),
            "terms_note": (
                "Use targeted, cached ABN/ACN enrichment. Do not run high-volume web-service "
                "sweeps without documenting ABN Lookup terms, permitted use, and rate limits."
            ),
        },
    )

    records = list(
        iter_abn_lookup_web_records(
            body_path,
            metadata_path,
            lookup_method=method,
            include_historical_details=include_historical_details,
        )
    )
    exceptions = response_context.get("exceptions") or []
    failure_reason = ""
    if exceptions:
        failure_reason = "ABN Lookup web-service response contained exceptions."
    elif not records:
        failure_reason = "ABN Lookup web-service response contained no business entity records."

    if failure_reason:
        summary_path = _write_json(
            processed_dir / "abn_lookup_web" / f"{artifact_id}.summary.json",
            {
                "generated_at": timestamp,
                "lookup_type": normalized_lookup_type,
                "lookup_method": method,
                "lookup_value": search_value,
                "include_historical_details": include_historical_details,
                "source_metadata_path": str(metadata_path),
                "body_path": str(body_path),
                "official_identifiers_jsonl": "",
                "records_written": 0,
                "ok": False,
                "failure_reason": failure_reason,
                "response_context": response_context,
            },
        )
        raise AbnLookupWebServiceError(f"{failure_reason} Summary artifact: {summary_path}")

    jsonl_path = write_official_identifier_records(
        records,
        processed_dir=processed_dir,
        artifact_id=artifact_id,
    )
    summary_path = _write_json(
        processed_dir / "abn_lookup_web" / f"{artifact_id}.summary.json",
        {
            "generated_at": timestamp,
            "lookup_type": normalized_lookup_type,
            "lookup_method": method,
            "lookup_value": search_value,
            "include_historical_details": include_historical_details,
            "source_metadata_path": str(metadata_path),
            "body_path": str(body_path),
            "official_identifiers_jsonl": str(jsonl_path),
            "records_written": len(records),
            "ok": True,
            "response_context": response_context,
        },
    )
    return summary_path


def _open_json_with_retries(request: Request, timeout: int = 60, tries: int = 4) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 500, 502, 503, 504} or attempt == tries - 1:
                raise
            retry_after = exc.headers.get("Retry-After") if exc.headers else None
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
            time.sleep(delay)
        except (URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == tries - 1:
                raise
            time.sleep(2**attempt)
    raise RuntimeError(f"Request failed after retries: {last_error!r}")


def _post_lobbyist_json(endpoint: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    request = Request(
        LOBBYIST_API_BASE + endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    return _open_json_with_retries(request, timeout=timeout)


def _get_lobbyist_json(endpoint: str, timeout: int = 60) -> dict[str, Any]:
    request = Request(LOBBYIST_API_BASE + endpoint, headers={"User-Agent": USER_AGENT})
    return _open_json_with_retries(request, timeout=timeout)


def fetch_lobbyist_register_snapshot(
    *,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    limit: int | None = None,
    sleep_seconds: float = 0.2,
) -> Path:
    timestamp = _timestamp()
    source = get_source("australian_lobbyists_register")
    target_dir = raw_dir / source.source_id / timestamp
    target_dir.mkdir(parents=True, exist_ok=True)

    search_payload: dict[str, Any] = {
        "entity": "organisation",
        "query": "",
        "pageNumber": 1,
        "pagingCookie": None,
        "count": 1000,
        "sortCriteria": {"fieldName": "name", "sortOrder": 0},
        "isDeregistered": False,
    }
    pages: list[dict[str, Any]] = []
    org_rows: list[dict[str, Any]] = []
    while True:
        page = _post_lobbyist_json("search/organisations", search_payload)
        pages.append(page)
        org_rows.extend(page.get("resultSet", []))
        if limit is not None and len(org_rows) >= limit:
            org_rows = org_rows[:limit]
            break
        if not page.get("hasMoreRecords"):
            break
        search_payload["pageNumber"] = int(page.get("pageNumber") or search_payload["pageNumber"]) + 1
        search_payload["pagingCookie"] = page.get("pagingCookie")
        if sleep_seconds:
            time.sleep(sleep_seconds)

    organisations_path = target_dir / "organisations.json"
    organisations_path.write_text(
        json.dumps({"pages": pages, "resultSet": org_rows}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    profiles_path = target_dir / "profiles.jsonl"
    with profiles_path.open("w", encoding="utf-8") as handle:
        for organisation in org_rows:
            profile = _get_lobbyist_json(f"search/organisations/{organisation['id']}/profile")
            summary = profile.get("summary") or {}
            if not summary.get("id") or not summary.get("displayName"):
                raise RuntimeError(
                    "Lobbyist profile missing required summary id/displayName "
                    f"for organisation {organisation.get('id')}"
                )
            handle.write(json.dumps(profile, sort_keys=True) + "\n")
            if sleep_seconds:
                time.sleep(sleep_seconds)

    sha = hashlib.sha256()
    sha.update(organisations_path.read_bytes())
    sha.update(profiles_path.read_bytes())
    metadata_path = _write_json(
        target_dir / "metadata.json",
        {
            "source": source.to_dict(),
            "fetched_at": timestamp,
            "ok": True,
            "http_status": 200,
            "final_url": LOBBYIST_API_BASE,
            "content_type": "application/json",
            "content_length": organisations_path.stat().st_size + profiles_path.stat().st_size,
            "sha256": sha.hexdigest(),
            "body_path": str(profiles_path.resolve()),
            "headers": {},
            "metadata_kind": "lobbyist_register_api_snapshot",
            "organisation_count": len(org_rows),
        },
    )
    jsonl_path = write_lobbyist_identifier_records(profiles_path, metadata_path, processed_dir)
    summary_path = _write_json(
        processed_dir / "official_lobbyist_snapshots" / f"{timestamp}.summary.json",
        {
            "generated_at": timestamp,
            "organisations_path": str(organisations_path),
            "profiles_path": str(profiles_path),
            "source_metadata_path": str(metadata_path),
            "official_identifiers_jsonl": str(jsonl_path),
            "organisation_count": len(org_rows),
        },
    )
    return summary_path


def _client_key(organisation_id: str, client: dict[str, Any]) -> str:
    identifier = _digits(client.get("abn") or "")
    name = normalize_name(client.get("displayName") or "")
    return f"{organisation_id}:client:{identifier or name}"


def write_lobbyist_identifier_records(
    profiles_path: Path,
    source_metadata_path: Path,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    timestamp = _timestamp()
    target_dir = processed_dir / "official_identifiers"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}.jsonl"

    records_written = 0
    relationships_written = 0
    with profiles_path.open("r", encoding="utf-8") as profiles, target_path.open(
        "w", encoding="utf-8"
    ) as output:
        for line in profiles:
            profile = json.loads(line)
            summary = profile.get("summary") or {}
            organisation_id = summary.get("id") or ""
            output.write(
                json.dumps(
                    _record(
                        source_id="australian_lobbyists_register",
                        source_record_type="lobbyist_organisation",
                        display_name=summary.get("displayName") or "",
                        external_id=organisation_id,
                        entity_type="lobbyist_organisation",
                        identifiers=(
                            _identifier("lobbyist_register_organisation_id", organisation_id),
                            _identifier("abn", summary.get("abn") or ""),
                        ),
                        aliases=(summary.get("tradingName") or "",),
                        public_sector="consulting",
                        official_classification=(
                            "Registered third-party lobbying organisation"
                        ),
                        status="deregistered" if summary.get("isDeregistered") else "registered",
                        source_updated_at=summary.get("modifiedOn") or "",
                        evidence_note="Australian Government Register of Lobbyists organisation.",
                        source_metadata_path=str(source_metadata_path),
                        raw_record=summary,
                    ),
                    sort_keys=True,
                )
                + "\n"
            )
            records_written += 1

            for client in profile.get("clients") or []:
                client_name = client.get("displayName") or ""
                if not client_name:
                    continue
                output.write(
                    json.dumps(
                        _record(
                            source_id="australian_lobbyists_register",
                            source_record_type="lobbyist_client",
                            display_name=client_name,
                            external_id=_client_key(organisation_id, client),
                            entity_type="unknown",
                            identifiers=(_identifier("abn", client.get("abn") or ""),),
                            status=(
                                "deregistered"
                                if client.get("isDeregistered")
                                else "represented_client"
                            ),
                            source_updated_at=client.get("modifiedOn") or "",
                            evidence_note=(
                                "Client listed for a registered third-party lobbying organisation."
                            ),
                            source_metadata_path=str(source_metadata_path),
                            raw_record=client,
                            metadata={
                                "lobbyist_organisation_id": organisation_id,
                                "lobbyist_organisation_name": summary.get("displayName") or "",
                            },
                        ),
                        sort_keys=True,
                    )
                    + "\n"
                )
                records_written += 1
                relationships_written += 1

            for lobbyist in profile.get("lobbyists") or []:
                name = lobbyist.get("displayName") or ""
                if not name:
                    continue
                output.write(
                    json.dumps(
                        _record(
                            source_id="australian_lobbyists_register",
                            source_record_type="lobbyist_person",
                            display_name=name,
                            external_id=f"{organisation_id}:lobbyist:{normalize_name(name)}",
                            entity_type="individual",
                            status=(
                                "former_representative"
                                if lobbyist.get("isFormerRepresentative")
                                else "registered_lobbyist"
                            ),
                            source_updated_at=lobbyist.get("modifiedOn") or "",
                            evidence_note=(
                                "Individual lobbyist listed for a registered organisation."
                            ),
                            source_metadata_path=str(source_metadata_path),
                            raw_record=lobbyist,
                            metadata={
                                "lobbyist_organisation_id": organisation_id,
                                "lobbyist_organisation_name": summary.get("displayName") or "",
                                "is_former_representative": bool(
                                    lobbyist.get("isFormerRepresentative")
                                ),
                            },
                        ),
                        sort_keys=True,
                    )
                    + "\n"
                )
                records_written += 1
                relationships_written += 1

    summary_path = _write_json(
        target_dir / f"{timestamp}.summary.json",
        {
            "generated_at": timestamp,
            "jsonl_path": str(target_path),
            "records_written": records_written,
            "relationships_written": relationships_written,
            "source_metadata_path": str(source_metadata_path),
        },
    )
    return target_path if summary_path.exists() else target_path


def extract_official_identifiers_from_file(
    source_id: str,
    input_path: Path,
    *,
    processed_dir: Path = PROCESSED_DIR,
    raw_dir: Path = RAW_DIR,
    limit: int | None = None,
) -> Path:
    source_metadata_path = write_input_file_metadata(source_id, input_path, raw_dir=raw_dir)
    if source_id == "asic_companies_dataset":
        records = iter_asic_company_records(input_path, source_metadata_path, limit=limit)
    elif source_id == "acnc_register":
        records = iter_acnc_charity_records(input_path, source_metadata_path, limit=limit)
    elif source_id == "abn_lookup":
        records = iter_abn_bulk_records(input_path, source_metadata_path, limit=limit)
    else:
        raise ValueError(f"Unsupported official identifier source: {source_id}")
    return write_official_identifier_records(records, processed_dir=processed_dir)


def write_official_identifier_records(
    records: Iterable[dict[str, Any]],
    *,
    processed_dir: Path = PROCESSED_DIR,
    artifact_id: str | None = None,
) -> Path:
    generated_at = _timestamp()
    timestamp = artifact_id or generated_at
    target_dir = processed_dir / "official_identifiers"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}.jsonl"
    count = 0
    source_counts: dict[str, int] = {}
    with target_path.open("w", encoding="utf-8") as handle:
        for record in records:
            if not record.get("normalized_name"):
                continue
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
            source_counts[record["source_id"]] = source_counts.get(record["source_id"], 0) + 1
    _write_json(
        target_dir / f"{timestamp}.summary.json",
        {
            "generated_at": generated_at,
            "jsonl_path": str(target_path),
            "record_count": count,
            "source_counts": source_counts,
        },
    )
    return target_path


def latest_official_identifiers_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path:
    source_dir = processed_dir / "official_identifiers"
    candidates = sorted(source_dir.glob("*.jsonl"), reverse=True)
    if not candidates:
        raise FileNotFoundError("No official identifier JSONL artifact found.")
    return candidates[0]


def latest_official_identifier_jsonl_paths(processed_dir: Path = PROCESSED_DIR) -> list[Path]:
    source_dir = processed_dir / "official_identifiers"
    candidates = sorted(source_dir.glob("*.jsonl"), reverse=True)
    latest_snapshot_by_source: dict[str, Path] = {}
    incremental_paths: list[Path] = []
    incremental_record_types = {"abn_web_service_entity"}
    for path in candidates:
        try:
            with path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
        except OSError:
            continue
        if not first_line:
            continue
        try:
            first_record = json.loads(first_line)
        except json.JSONDecodeError:
            continue
        source_id = first_record.get("source_id")
        source_record_type = first_record.get("source_record_type")
        if source_record_type in incremental_record_types:
            incremental_paths.append(path)
            continue
        if source_id and source_id not in latest_snapshot_by_source:
            latest_snapshot_by_source[source_id] = path
    if not latest_snapshot_by_source and not incremental_paths:
        raise FileNotFoundError("No official identifier JSONL artifact found.")
    return [
        latest_snapshot_by_source[source_id]
        for source_id in sorted(latest_snapshot_by_source)
    ] + sorted(incremental_paths)
