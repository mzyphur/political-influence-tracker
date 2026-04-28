from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.discovery import latest_body_path
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.sources import get_source
from au_politics_money.models import SourceRecord


PARSER_NAME = "aph_decision_record_index_v1"
PARSER_VERSION = "1"
DECISION_RECORD_SOURCE_IDS = ("aph_house_votes_and_proceedings", "aph_senate_journals")
MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}
MONTH_ABBREVIATIONS = {month[:3].lower(): month for month in MONTHS}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _normalize_url(value: str) -> str:
    return re.sub(r"\s+", "%20", value.strip())


def _month_from_text(value: str) -> str:
    cleaned = _clean_text(value).lower()
    for month in MONTHS:
        if cleaned.startswith(month):
            return month.title()
    return ""


def _nearest_heading_text(anchor, names: tuple[str, ...], pattern: str | None = None) -> str:
    for heading in anchor.find_all_previous(names):
        text = _clean_text(heading.get_text(" ", strip=True))
        if not text:
            continue
        if pattern is None or re.search(pattern, text, flags=re.IGNORECASE):
            return text
    return ""


def _parliament_label(anchor) -> str:
    text = _nearest_heading_text(anchor, ("h1", "h2"), r"\bparliament\b")
    return text


def _year_label(anchor) -> str:
    heading = _nearest_heading_text(anchor, ("h2", "h3", "h4"), r"\b(19|20)\d{2}\b")
    match = re.search(r"\b(19|20)\d{2}\b", heading)
    return match.group(0) if match else ""


def _month_label(anchor) -> str:
    parent_row = anchor.find_parent("tr")
    if parent_row is not None:
        cells = parent_row.find_all(["th", "td"])
        if cells:
            month = _month_from_text(cells[0].get_text(" ", strip=True))
            if month:
                return month
    parent = anchor.find_parent(["p", "li", "div"])
    if parent is not None:
        month = _month_from_text(parent.get_text(" ", strip=True))
        if month:
            return month
    return ""


def _iso_date(year: str, month: str, day: str) -> str:
    if not (year and month and day.isdigit()):
        return ""
    month_number = MONTHS.get(month.lower())
    if not month_number:
        return ""
    try:
        parsed = datetime.strptime(f"{int(year):04d}-{month_number}-{int(day):02d}", "%Y-%m-%d")
    except ValueError:
        return ""
    return parsed.date().isoformat()


def _date_parts_from_aria_label(anchor) -> tuple[str, str, str, str, str]:
    label = _clean_text(str(anchor.get("aria-label") or ""))
    if not label:
        return "", "", "", "", ""
    for fmt in ("%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(label, fmt).date()
            return (
                parsed.isoformat(),
                f"{parsed.year:04d}",
                parsed.strftime("%B"),
                str(parsed.day),
                "aria-label",
            )
        except ValueError:
            continue
    match = re.match(r"^(\d{1,2})[- ]([A-Za-z]{3,9})[- ]((?:19|20)\d{2})$", label)
    if not match:
        return "", "", "", "", ""
    day, month_raw, year = match.groups()
    month = MONTHS.get(month_raw.lower()) or MONTH_ABBREVIATIONS.get(month_raw[:3].lower(), "")
    date = _iso_date(year, month, day)
    return date, year if date else "", month if date else "", str(int(day)) if date else "", "aria-label"


def _record_kind(source_id: str, url: str, title: str) -> str:
    parsed = urlparse(url)
    lowered = f"{url} {title}".lower()
    if "parlinfo.aph.gov.au" in parsed.netloc.lower():
        if "download" in parsed.path.lower() or "filetype=application" in lowered:
            return "parlinfo_pdf"
        return "parlinfo_html"
    if parsed.path.lower().endswith(".pdf") or "pdf" in title.lower():
        return "pdf"
    if source_id == "aph_house_votes_and_proceedings":
        return "house_votes_and_proceedings_link"
    return "senate_journal_link"


def _parlinfo_record_key(url: str) -> str:
    decoded = unquote(url)
    match = re.search(r"chamber/(votes|journals)/([^/\";\s]+)/", decoded, flags=re.IGNORECASE)
    if match:
        return f"{match.group(1).lower()}:{match.group(2)}"
    return ""


def _canonical_link_key(source_id: str, url: str) -> str:
    parlinfo_key = _parlinfo_record_key(url)
    if parlinfo_key:
        return f"{source_id}:parlinfo:{parlinfo_key}"
    external_key = hashlib.sha256(f"{source_id}|{url}".encode("utf-8")).hexdigest()[:24]
    return f"{source_id}:url:{external_key}"


def _representation_priority(record_kind: str) -> int:
    if record_kind == "parlinfo_html":
        return 0
    if record_kind == "parlinfo_pdf":
        return 1
    return 2


def _keep_decision_record_link(source_id: str, url: str, title: str) -> bool:
    parsed = urlparse(url)
    lowered_url = url.lower()
    if source_id == "aph_house_votes_and_proceedings":
        if "parlinfo.aph.gov.au" in parsed.netloc.lower():
            return "chamber/votes" in lowered_url
        return False
    if source_id == "aph_senate_journals":
        if "parlinfo.aph.gov.au" in parsed.netloc.lower():
            return "chamber/journals" in lowered_url
        return False
    raise ValueError(f"Unsupported APH decision-record source: {source_id}")


def parse_aph_decision_record_index(
    *,
    source: SourceRecord,
    html: str,
    source_metadata_path: Path | None = None,
) -> list[dict[str, Any]]:
    if source.source_id not in DECISION_RECORD_SOURCE_IDS:
        raise ValueError(f"Unsupported APH decision-record source: {source.source_id}")

    chamber = "house" if source.source_id == "aph_house_votes_and_proceedings" else "senate"
    record_type = (
        "votes_and_proceedings"
        if source.source_id == "aph_house_votes_and_proceedings"
        else "journals_of_the_senate"
    )
    soup = BeautifulSoup(html, "html.parser")
    records_by_key: dict[str, dict[str, Any]] = {}
    for anchor in soup.find_all("a", href=True):
        raw_title = _clean_text(anchor.get_text(" ", strip=True))
        url = _normalize_url(urljoin(source.url, str(anchor["href"]).strip()))
        if not raw_title or not _keep_decision_record_link(source.source_id, url, raw_title):
            continue

        date, year, month, day_label, date_source = _date_parts_from_aria_label(anchor)
        if not date:
            year = _year_label(anchor)
            month = _month_label(anchor)
            day_label = raw_title if raw_title.isdigit() else ""
            date = _iso_date(year, month, day_label)
            date_source = "heading_month_and_link_text" if date else ""
        if not date:
            raise ValueError(f"Decision record link missing parseable date: {url}")

        kind = _record_kind(source.source_id, url, raw_title)
        canonical_key = _canonical_link_key(source.source_id, url)
        external_key = (
            f"{source.source_id}:{hashlib.sha256(canonical_key.encode('utf-8')).hexdigest()[:24]}"
        )
        parent_text = _clean_text(
            (anchor.find_parent(["tr", "p", "li"]) or anchor).get_text(" ", strip=True)
        )
        representation = {
            "url": url,
            "record_kind": kind,
            "link_text": raw_title,
            "host": urlparse(url).netloc,
            "parent_text": parent_text,
        }
        existing = records_by_key.get(canonical_key)
        if existing is not None:
            representations = existing["metadata"].setdefault("representations", [])
            if not any(item.get("url") == url for item in representations):
                representations.append(representation)
            if _representation_priority(kind) < _representation_priority(existing["record_kind"]):
                existing["record_kind"] = kind
                existing["link_text"] = raw_title
                existing["url"] = url
                existing["metadata"]["host"] = representation["host"]
                existing["metadata"]["parent_text"] = parent_text
            if len({item.get("url") for item in representations}) > 1:
                existing["record_kind"] = "parlinfo_multi"
            continue

        records_by_key[canonical_key] = {
            "schema_version": "aph_decision_record_index_v1",
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "source_id": source.source_id,
            "source_name": source.name,
            "source_metadata_path": str(source_metadata_path) if source_metadata_path else "",
            "external_key": external_key,
            "chamber": chamber,
            "record_type": record_type,
            "record_kind": kind,
            "parliament_label": _parliament_label(anchor),
            "year": year,
            "month": month,
            "day_label": day_label,
            "record_date": date,
            "title": f"{source.name} {date}",
            "link_text": raw_title,
            "url": url,
            "evidence_status": "official_record_index",
            "metadata": {
                "host": urlparse(url).netloc,
                "parent_text": parent_text,
                "canonical_link_key": canonical_key,
                "date_source": date_source,
                "representations": [representation],
            },
        }
    return list(records_by_key.values())


def latest_source_metadata_path(source_id: str) -> Path | None:
    body_path = latest_body_path(source_id)
    if body_path is None:
        return None
    metadata_path = body_path.parent / "metadata.json"
    return metadata_path if metadata_path.exists() else None


def latest_aph_decision_record_index_jsonl_paths(
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> list[Path]:
    paths: list[Path] = []
    for source_id in DECISION_RECORD_SOURCE_IDS:
        source_dir = processed_dir / "aph_decision_record_indexes" / source_id
        if not source_dir.exists():
            continue
        candidates = sorted(source_dir.glob("*.jsonl"), reverse=True)
        if candidates:
            paths.append(candidates[0])
    return paths


def read_aph_decision_record_index_records(
    jsonl_paths: list[Path] | None = None,
) -> list[dict[str, Any]]:
    paths = jsonl_paths or latest_aph_decision_record_index_jsonl_paths()
    records: list[dict[str, Any]] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
    return records


def _representation_rows(record: dict[str, Any]) -> list[dict[str, str]]:
    representations = (record.get("metadata") or {}).get("representations") or []
    if not representations:
        representations = [
            {
                "url": record["url"],
                "record_kind": record["record_kind"],
                "link_text": record.get("link_text") or "",
                "host": urlparse(record["url"]).netloc,
                "parent_text": (record.get("metadata") or {}).get("parent_text", ""),
            }
        ]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for representation in representations:
        url = _normalize_url(str(representation.get("url") or ""))
        if not url or url in seen:
            continue
        seen.add(url)
        rows.append(
            {
                "url": url,
                "record_kind": str(representation.get("record_kind") or record["record_kind"]),
                "link_text": str(representation.get("link_text") or record.get("link_text") or ""),
                "host": str(representation.get("host") or urlparse(url).netloc),
                "parent_text": str(representation.get("parent_text") or ""),
            }
        )
    return rows


def decision_record_document_source(
    record: dict[str, Any],
    representation: dict[str, str],
) -> SourceRecord:
    record_date = (record.get("record_date") or "undated").replace("-", "")
    representation_kind = representation["record_kind"]
    format_label = "pdf" if "pdf" in representation_kind else "html"
    stable_hash = hashlib.sha256(
        f"{record['external_key']}|{representation['url']}".encode("utf-8")
    ).hexdigest()[:12]
    return SourceRecord(
        source_id=(
            f"{record['source_id']}__decision_record__"
            f"{record_date}__{format_label}__{stable_hash}"
        ),
        name=f"{record['source_name']} {record['record_date']} {format_label.upper()}",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="official_parliamentary_decision_record_document",
        url=representation["url"],
        expected_format=format_label,
        update_frequency="sitting_days_plus_corrections",
        priority="high",
        notes=(
            f"Linked {representation_kind} representation for "
            f"{record['external_key']} ({record['chamber']} {record['record_date']})."
        ),
    )


def latest_aph_decision_record_documents_summary(
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    source_dir = processed_dir / "aph_decision_record_documents"
    if not source_dir.exists():
        return None
    candidates = sorted(source_dir.glob("*.summary.json"), reverse=True)
    return candidates[0] if candidates else None


def _decision_document_link_metadata(
    *,
    record: dict[str, Any],
    representation: dict[str, str],
    index_artifact_path: Path,
) -> dict[str, Any]:
    return {
        "official_decision_record": {
            "external_key": record["external_key"],
            "source_id": record["source_id"],
            "source_name": record["source_name"],
            "chamber": record["chamber"],
            "record_type": record["record_type"],
            "record_date": record["record_date"],
            "title": record["title"],
            "index_url": record["url"],
            "index_artifact_path": str(index_artifact_path),
            "index_source_metadata_path": record.get("source_metadata_path", ""),
        },
        "official_decision_record_representation": representation,
    }


def _validate_decision_document_metadata(
    *,
    metadata_path: Path,
    representation_kind: str,
) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata.get("body_path") or "")
    if not body_path.exists():
        raise FileNotFoundError(f"Fetched APH decision-record body is missing: {body_path}")
    body_start = body_path.read_bytes()[:8192]
    content_type = str(metadata.get("content_type") or "").lower()
    is_pdf = "pdf" in representation_kind
    if is_pdf:
        if not body_start.startswith(b"%PDF-"):
            raise RuntimeError(
                f"Expected APH decision-record PDF but body does not start with %PDF: {body_path}"
            )
        if content_type and "pdf" not in content_type:
            raise RuntimeError(
                "Expected APH decision-record PDF but response content type was "
                f"{metadata.get('content_type')}: {body_path}"
            )
    else:
        lowered_start = body_start.lower()
        if b"<html" not in lowered_start and b"<!doctype html" not in lowered_start:
            raise RuntimeError(f"Expected APH decision-record HTML body: {body_path}")
        blocked_markers = (b"access denied", b"request blocked", b"forbidden")
        if any(marker in lowered_start for marker in blocked_markers):
            raise RuntimeError(f"APH decision-record HTML body appears to be an access page: {body_path}")
        if content_type and "html" not in content_type:
            raise RuntimeError(
                "Expected APH decision-record HTML but response content type was "
                f"{metadata.get('content_type')}: {body_path}"
            )
    return {
        "body_path": str(body_path),
        "content_type": metadata.get("content_type"),
        "content_length": metadata.get("content_length"),
        "sha256": metadata.get("sha256"),
        "validation": "pdf_signature" if is_pdf else "html_signature",
    }


def _document_summary_row(
    *,
    status: str,
    source_id: str,
    record: dict[str, Any],
    representation: dict[str, str],
    index_artifact_path: Path,
    metadata_path: Path | None = None,
    validation: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    row = {
        "status": status,
        "source_id": source_id,
        "decision_record_external_key": record["external_key"],
        "record_date": record["record_date"],
        "representation_kind": representation["record_kind"],
        "representation_url": representation["url"],
        **_decision_document_link_metadata(
            record=record,
            representation=representation,
            index_artifact_path=index_artifact_path,
        ),
    }
    if metadata_path is not None:
        row["metadata_path"] = str(metadata_path)
    if validation is not None:
        row["validation"] = validation
    if error is not None:
        row["error"] = error
    return row


def _without_fragment(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(fragment=""))


def _derived_house_pdf_representations_from_html(
    metadata_path: Path,
) -> list[dict[str, str]]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata.get("body_path") or "")
    if not body_path.exists():
        return []
    base_url = str(metadata.get("final_url") or (metadata.get("source") or {}).get("url") or "")
    soup = BeautifulSoup(body_path.read_text(encoding="utf-8", errors="replace"), "html.parser")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = _without_fragment(_normalize_url(urljoin(base_url, str(anchor["href"]).strip())))
        lowered = href.lower()
        if "parlinfo.aph.gov.au" not in urlparse(href).netloc.lower():
            continue
        if "download/chamber/votes/" not in lowered:
            continue
        if "pdf" not in lowered:
            continue
        if href in seen:
            continue
        seen.add(href)
        parent = anchor.find_parent(["p", "li", "div"])
        rows.append(
            {
                "url": href,
                "record_kind": "parlinfo_pdf",
                "link_text": _clean_text(anchor.get_text(" ", strip=True)) or "Download PDF",
                "host": urlparse(href).netloc,
                "parent_text": _clean_text(
                    (parent or anchor).get_text(" ", strip=True)
                ),
                "derived_from_html_metadata_path": str(metadata_path),
                "derivation_method": "house_parlinfo_html_download_pdf_anchor",
            }
        )
    return rows


def fetch_aph_decision_record_documents(
    *,
    jsonl_paths: list[Path] | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    include_html: bool = True,
    include_pdf: bool = True,
    only_missing: bool = False,
    limit: int | None = None,
    timeout: int = 90,
    fetcher: Callable[..., Path] = fetch_source,
) -> Path:
    paths = jsonl_paths or latest_aph_decision_record_index_jsonl_paths(processed_dir=processed_dir)
    records = read_aph_decision_record_index_records(paths)
    if not records:
        raise RuntimeError("No APH decision-record index rows available for document fetch.")

    timestamp = _timestamp()
    documents: list[dict[str, Any]] = []
    fetched_count = 0
    skipped_existing_count = 0
    derived_representation_count = 0
    skipped_filter_count = 0
    failed_count = 0
    selected_count = 0

    def fetch_document_representation(
        *,
        record: dict[str, Any],
        representation: dict[str, str],
        index_artifact_path: Path,
        status_on_existing: str = "skipped_existing",
    ) -> tuple[dict[str, Any], bool]:
        nonlocal fetched_count, skipped_existing_count, failed_count
        source = decision_record_document_source(record, representation)
        latest_existing_body = latest_body_path(source.source_id, raw_dir=raw_dir)
        if only_missing and latest_existing_body is not None:
            metadata_path = latest_existing_body.parent / "metadata.json"
            try:
                validation = _validate_decision_document_metadata(
                    metadata_path=metadata_path,
                    representation_kind=representation["record_kind"],
                )
            except Exception:
                latest_existing_body = None
            else:
                skipped_existing_count += 1
                return (
                    _document_summary_row(
                        status=status_on_existing,
                        source_id=source.source_id,
                        record=record,
                        representation=representation,
                        index_artifact_path=index_artifact_path,
                        metadata_path=metadata_path,
                        validation=validation,
                    ),
                    True,
                )

        try:
            metadata_path = fetcher(source, raw_dir=raw_dir, timeout=timeout)
            validation = _validate_decision_document_metadata(
                metadata_path=metadata_path,
                representation_kind=representation["record_kind"],
            )
        except Exception as exc:  # noqa: BLE001 - summary must preserve partial failures.
            failed_count += 1
            return (
                _document_summary_row(
                    status="failed",
                    source_id=source.source_id,
                    record=record,
                    representation=representation,
                    index_artifact_path=index_artifact_path,
                    error=repr(exc),
                ),
                False,
            )

        fetched_count += 1
        return (
            _document_summary_row(
                status="fetched",
                source_id=source.source_id,
                record=record,
                representation=representation,
                index_artifact_path=index_artifact_path,
                metadata_path=metadata_path,
                validation=validation,
            ),
            True,
        )

    for record in records:
        index_artifact_path = next(
            (
                path
                for path in paths
                if path.parent.name == record["source_id"]
            ),
            paths[0],
        )
        for representation in _representation_rows(record):
            representation_kind = representation["record_kind"]
            is_pdf = "pdf" in representation_kind
            is_html = "html" in representation_kind
            if (is_pdf and not include_pdf) or (is_html and not include_html):
                skipped_filter_count += 1
                continue
            if limit is not None and selected_count >= limit:
                break
            selected_count += 1

            document_row, ok = fetch_document_representation(
                record=record,
                representation=representation,
                index_artifact_path=index_artifact_path,
            )
            documents.append(document_row)
            if (
                ok
                and include_pdf
                and record.get("chamber") == "house"
                and "html" in representation_kind
                and document_row.get("metadata_path")
            ):
                for derived_representation in _derived_house_pdf_representations_from_html(
                    Path(str(document_row["metadata_path"]))
                ):
                    if limit is not None and selected_count >= limit:
                        break
                    selected_count += 1
                    derived_representation_count += 1
                    derived_row, _ = fetch_document_representation(
                        record=record,
                        representation=derived_representation,
                        index_artifact_path=index_artifact_path,
                    )
                    documents.append(derived_row)
        if limit is not None and selected_count >= limit:
            break

    target_dir = processed_dir / "aph_decision_record_documents"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": timestamp,
        "index_jsonl_paths": [str(path) for path in paths],
        "include_html": include_html,
        "include_pdf": include_pdf,
        "only_missing": only_missing,
        "limit": limit,
        "selected_count": selected_count,
        "fetched_count": fetched_count,
        "skipped_existing_count": skipped_existing_count,
        "derived_representation_count": derived_representation_count,
        "skipped_filter_count": skipped_filter_count,
        "failed_count": failed_count,
        "documents": documents,
    }
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if selected_count == 0:
        raise RuntimeError(f"No APH decision-record document representations matched fetch filters: {summary_path}")
    if failed_count:
        raise RuntimeError(f"{failed_count} APH decision-record document fetches failed: {summary_path}")
    return summary_path


def extract_aph_decision_record_index(
    source_id: str,
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    source = get_source(source_id)
    body_path = latest_body_path(source_id)
    if body_path is None:
        fetch_source(source)
        body_path = latest_body_path(source_id)
    if body_path is None:
        raise FileNotFoundError(f"No raw body found for source {source_id}")
    metadata_path = body_path.parent / "metadata.json"
    records = parse_aph_decision_record_index(
        source=source,
        html=body_path.read_text(encoding="utf-8", errors="replace"),
        source_metadata_path=metadata_path,
    )
    if not records:
        raise RuntimeError(f"No APH decision records parsed for {source_id}")
    missing_dates = [record["url"] for record in records if not record.get("record_date")]
    if missing_dates:
        raise RuntimeError(
            f"Parsed APH decision records without record_date for {source_id}: {missing_dates[:5]}"
        )
    timestamp = _timestamp()
    target_dir = processed_dir / "aph_decision_record_indexes" / source_id
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    summary = {
        "generated_at": timestamp,
        "source_id": source_id,
        "source_metadata_path": str(metadata_path),
        "jsonl_path": str(jsonl_path),
        "record_count": len(records),
        "record_kind_counts": {
            kind: sum(1 for record in records if record["record_kind"] == kind)
            for kind in sorted({record["record_kind"] for record in records})
        },
    }
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
