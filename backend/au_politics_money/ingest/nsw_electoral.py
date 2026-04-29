from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.official_identifiers import normalize_name
from au_politics_money.ingest.sources import get_source

SOURCE_DATASET = "nsw_electoral_disclosures"
PRE_ELECTION_SOURCE_ID = "nsw_2023_state_election_pre_election_donations"
HEATMAP_SOURCE_ID = "nsw_2023_state_election_donation_heatmap"
PARSER_NAME = "nsw_pre_election_donor_location_heatmap_normalizer"
PARSER_VERSION = "1"
REPORTING_PERIOD_START = "2022-10-01"
REPORTING_PERIOD_END = "2023-03-25"
SOURCE_TABLE = "nsw_2023_state_election_donation_heatmap_district_table"
HEATMAP_CAVEAT = (
    "Official NSW Electoral Commission 2023 State Election heatmap aggregate. "
    "Rows are donor-location totals by electoral district or interstate location "
    "for pre-election-period reportable donations. The heatmap does not identify "
    "the recipient, donor entity, candidate, party, or MP for each aggregate row; "
    "these rows are source-backed aggregate context only and must not be displayed "
    "as donations received by a representative. The source page notes the map does "
    "not show recipient locations and may exclude donor locations that cannot be "
    "mapped, including silent electors and some donors outside New South Wales. "
    "NSW Electoral Commission material is used under Creative Commons Attribution "
    "4.0 unless otherwise noted; attribution is © State of New South Wales through "
    "the NSW Electoral Commission."
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


def resolve_nsw_heatmap_url_from_pre_election_page(metadata_path: Path) -> dict[str, str]:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != PRE_ELECTION_SOURCE_ID:
        raise ValueError(
            f"Expected {PRE_ELECTION_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    body_path = Path(str(metadata["body_path"]))
    body = body_path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(body, "html.parser")
    candidates: list[dict[str, str]] = []
    base_url = str(metadata.get("final_url") or source.get("url") or "")
    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "")
        label = " ".join(link.get_text(" ", strip=True).split())
        combined = f"{href} {label}".casefold()
        if "heat-map.html" in combined or "disclosures heatmap" in combined:
            candidates.append(
                {
                    "heatmap_url": urljoin(base_url, href),
                    "link_text": label,
                    "source_page_metadata_path": str(metadata_path),
                    "source_page_body_path": str(body_path),
                }
            )
    if not candidates:
        raise ValueError("Could not resolve NSW 2023 State election heatmap link")
    if len(candidates) > 1:
        unique_urls = {candidate["heatmap_url"].casefold() for candidate in candidates}
        if len(unique_urls) > 1:
            raise ValueError(
                "Multiple NSW heatmap links found on pre-election page: "
                f"{sorted(candidate['heatmap_url'] for candidate in candidates)}"
            )
    return candidates[0]


def _money_string(value: Any) -> str:
    cleaned = str(value if value is not None else "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("Missing NSW heatmap amount")
    try:
        return str(Decimal(cleaned))
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse NSW heatmap amount: {value!r}") from exc


def _int_count(value: Any) -> int:
    cleaned = str(value if value is not None else "").replace(",", "").strip()
    if not cleaned:
        raise ValueError("Missing NSW heatmap donation count")
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Could not parse NSW heatmap donation count: {value!r}") from exc
    if parsed != parsed.to_integral_value():
        raise ValueError(f"NSW heatmap donation count is not integral: {value!r}")
    return int(parsed)


def _find_district_table(body: str) -> tuple[list[str], list[Any], list[Any]]:
    soup = BeautifulSoup(body, "html.parser")
    for script in soup.find_all("script", {"type": "application/json"}):
        try:
            payload = json.loads(script.get_text())
        except json.JSONDecodeError:
            continue
        x_payload = payload.get("x") if isinstance(payload, dict) else None
        if not isinstance(x_payload, dict):
            continue
        table_data = x_payload.get("data")
        container = str(x_payload.get("container") or "")
        if (
            isinstance(table_data, list)
            and len(table_data) == 3
            and "District" in container
            and "Amount" in container
            and "Count" in container
        ):
            districts, amounts, counts = table_data
            if not (
                isinstance(districts, list)
                and isinstance(amounts, list)
                and isinstance(counts, list)
            ):
                continue
            if len(districts) != len(amounts) or len(districts) != len(counts):
                raise ValueError(
                    "NSW heatmap district table columns have inconsistent lengths: "
                    f"districts={len(districts)} amounts={len(amounts)} counts={len(counts)}"
                )
            if not districts:
                raise ValueError("NSW heatmap district table has no rows")
            return [str(value) for value in districts], amounts, counts
    raise ValueError("Could not find NSW heatmap district amount/count table")


def _record(
    *,
    source_metadata_path: Path,
    source_body_path: Path,
    row_number: int,
    district: str,
    amount: Any,
    count: Any,
    source_metadata_sha256: str,
    source_body_sha256: str,
    source_page_link_context: dict[str, str] | None,
) -> dict[str, Any]:
    district_name = " ".join(district.split())
    if not district_name:
        raise ValueError(f"Missing NSW heatmap district at row {row_number}")
    amount_aud = _money_string(amount)
    donation_count = _int_count(count)
    normalized = normalize_name(district_name)
    geography_type = (
        "interstate_donor_location"
        if district_name.casefold() == "interstate"
        else "state_electoral_district_donor_location"
    )
    average_donation = (
        str((Decimal(amount_aud) / Decimal(donation_count)).quantize(Decimal("0.01")))
        if donation_count
        else ""
    )
    return {
        "schema_version": "state_local_aggregate_context_v1",
        "source_dataset": SOURCE_DATASET,
        "source_id": HEATMAP_SOURCE_ID,
        "source_table": SOURCE_TABLE,
        "source_row_number": str(row_number),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "observation_key": f"{HEATMAP_SOURCE_ID}:{normalized}",
        "jurisdiction_name": "New South Wales",
        "jurisdiction_level": "state",
        "jurisdiction_code": "NSW",
        "context_family": "money_aggregate_context",
        "context_type": "pre_election_reportable_donation_donor_location",
        "geography_type": geography_type,
        "geography_name": district_name,
        "amount_aud": amount_aud,
        "amount_status": "reported",
        "donation_count": donation_count,
        "average_donation_aud": average_donation,
        "reporting_period_start": REPORTING_PERIOD_START,
        "reporting_period_end": REPORTING_PERIOD_END,
        "evidence_status": "official_record_parsed",
        "attribution_scope": "aggregate_context_not_recipient_attribution",
        "claim_boundary": (
            "Aggregate donor-location context only; not a donor-recipient money flow "
            "and not representative-level receipt."
        ),
        "caveat": HEATMAP_CAVEAT,
        "source_metadata_path": str(source_metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "metadata": {
            "source_surface": "static_official_heatmap_htmlwidget",
            "state_election": "2023 NSW State Election",
            "reporting_period": f"{REPORTING_PERIOD_START}/{REPORTING_PERIOD_END}",
            "recipient_identified": False,
            "donor_identified": False,
            "representative_attribution": "none",
            "public_display_group": "aggregate_context",
            "source_page_link_context": source_page_link_context or {},
            "copyright": {
                "notice": "© State of New South Wales through NSW Electoral Commission",
                "license": "Creative Commons Attribution 4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "copyright_url": "https://elections.nsw.gov.au/copyright",
                "no_endorsement": True,
            },
        },
    }


def normalize_nsw_pre_election_donor_location_heatmap(
    *,
    metadata_path: Path | None = None,
    source_page_link_context: dict[str, str] | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if metadata_path is None:
        try:
            metadata_path = _latest_metadata(HEATMAP_SOURCE_ID, raw_dir=raw_dir)
        except FileNotFoundError:
            metadata_path = fetch_source(get_source(HEATMAP_SOURCE_ID), raw_dir=raw_dir)

    metadata_path = Path(metadata_path)
    source_metadata_sha256 = _sha256_path(metadata_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata.get("source") or {}
    if source.get("source_id") != HEATMAP_SOURCE_ID:
        raise ValueError(
            f"Expected {HEATMAP_SOURCE_ID} metadata, got {source.get('source_id')!r}"
        )
    source_body_path = Path(str(metadata["body_path"]))
    source_body_sha256 = _sha256_path(source_body_path)
    if metadata.get("sha256") and metadata["sha256"] != source_body_sha256:
        raise ValueError(
            f"NSW heatmap body hash mismatch: metadata={metadata['sha256']} "
            f"actual={source_body_sha256}"
        )
    body = source_body_path.read_text(encoding="utf-8", errors="replace")
    districts, amounts, counts = _find_district_table(body)

    timestamp = _timestamp()
    target_dir = processed_dir / "nsw_pre_election_donor_location_aggregates"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    total_amount = Decimal("0")
    total_count = 0
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row_number, (district, amount, count) in enumerate(
            zip(districts, amounts, counts, strict=True),
            start=1,
        ):
            record = _record(
                source_metadata_path=Path(metadata_path),
                source_body_path=source_body_path,
                row_number=row_number,
                district=district,
                amount=amount,
                count=count,
                source_metadata_sha256=source_metadata_sha256,
                source_body_sha256=source_body_sha256,
                source_page_link_context=source_page_link_context,
            )
            total_amount += Decimal(str(record["amount_aud"]))
            total_count += int(record["donation_count"])
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    if not districts:
        raise RuntimeError("No NSW donor-location aggregate rows normalized")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": _sha256_path(jsonl_path),
        "source_metadata_path": str(metadata_path),
        "source_metadata_sha256": source_metadata_sha256,
        "source_body_path": str(source_body_path),
        "source_body_sha256": source_body_sha256,
        "source_id": HEATMAP_SOURCE_ID,
        "source_dataset": SOURCE_DATASET,
        "source_page_link_context": source_page_link_context or {},
        "total_count": len(districts),
        "donation_count_total": total_count,
        "reported_amount_total": str(total_amount),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "schema_version": "state_local_aggregate_context_v1",
        "claim_boundary": HEATMAP_CAVEAT,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
