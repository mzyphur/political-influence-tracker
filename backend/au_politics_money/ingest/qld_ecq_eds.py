from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.aec_annual import parse_money
from au_politics_money.ingest.fetch import (
    _safe_response_headers,
    _suffix_for_content,
    fetch_source,
)
from au_politics_money.ingest.official_identifiers import normalize_name
from au_politics_money.ingest.sources import get_source


@dataclass(frozen=True)
class QldEcqExportSpec:
    export_name: str
    page_source_id: str
    export_source_id: str


@dataclass(frozen=True)
class QldEcqLookupSpec:
    source_id: str
    source_record_type: str
    id_field: str
    name_field: str
    identifier_type: str
    entity_type: str
    level: str


@dataclass(frozen=True)
class QldEcqContextSpec:
    source_id: str
    source_record_type: str
    id_field: str
    name_field: str
    identifier_type: str
    context_type: str
    level: str


QLD_ECQ_EDS_EXPORTS: tuple[QldEcqExportSpec, ...] = (
    QldEcqExportSpec(
        export_name="map",
        page_source_id="qld_ecq_eds_public_map",
        export_source_id="qld_ecq_eds_map_export_csv",
    ),
    QldEcqExportSpec(
        export_name="expenditures",
        page_source_id="qld_ecq_eds_expenditures",
        export_source_id="qld_ecq_eds_expenditure_export_csv",
    ),
)

QLD_ECQ_EDS_PARTICIPANT_LOOKUPS: tuple[QldEcqLookupSpec, ...] = (
    QldEcqLookupSpec(
        source_id="qld_ecq_eds_api_political_electors",
        source_record_type="qld_ecq_political_elector",
        id_field="electorId",
        name_field="fullName",
        identifier_type="qld_ecq_elector_id",
        entity_type="candidate_or_elector",
        level="state_council",
    ),
    QldEcqLookupSpec(
        source_id="qld_ecq_eds_api_political_parties",
        source_record_type="qld_ecq_political_party",
        id_field="politicalPartyId",
        name_field="partyName",
        identifier_type="qld_ecq_political_party_id",
        entity_type="political_party",
        level="state_council",
    ),
    QldEcqLookupSpec(
        source_id="qld_ecq_eds_api_associated_entities",
        source_record_type="qld_ecq_associated_entity",
        id_field="organisationId",
        name_field="name",
        identifier_type="qld_ecq_organisation_id",
        entity_type="associated_entity",
        level="state_council",
    ),
    QldEcqLookupSpec(
        source_id="qld_ecq_eds_api_local_groups",
        source_record_type="qld_ecq_local_group",
        id_field="localGroupId",
        name_field="name",
        identifier_type="qld_ecq_local_group_id",
        entity_type="local_group",
        level="council",
    ),
)

QLD_ECQ_EDS_CONTEXT_LOOKUPS: tuple[QldEcqContextSpec, ...] = (
    QldEcqContextSpec(
        source_id="qld_ecq_eds_api_political_events",
        source_record_type="qld_ecq_political_event",
        id_field="eventId",
        name_field="name",
        identifier_type="qld_ecq_event_id",
        context_type="political_event",
        level="state_council",
    ),
    QldEcqContextSpec(
        source_id="qld_ecq_eds_api_local_electorates",
        source_record_type="qld_ecq_local_electorate",
        id_field="localElectorateId",
        name_field="localElectorateName",
        identifier_type="qld_ecq_local_electorate_id",
        context_type="local_electorate",
        level="council",
    ),
)

PARSER_NAME = "qld_ecq_eds_money_flow_normalizer"
PARSER_VERSION = "1"
PARTICIPANT_PARSER_NAME = "qld_ecq_eds_participant_normalizer"
PARTICIPANT_PARSER_VERSION = "1"
CONTEXT_PARSER_NAME = "qld_ecq_eds_context_normalizer"
CONTEXT_PARSER_VERSION = "1"
SOURCE_DATASET = "qld_ecq_eds"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path | None:
    candidates = sorted((raw_dir / source_id).glob("*/metadata.json"), reverse=True)
    return candidates[0] if candidates else None


def form_fields_from_html(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    form = soup.find("form", id="root") or soup.find("form")
    scope = form or soup
    fields: list[tuple[str, str]] = []

    for element in scope.select("input[name], select[name], textarea[name]"):
        if element.has_attr("disabled"):
            continue
        name = str(element.get("name") or "")
        if not name:
            continue

        tag_name = element.name.lower()
        if tag_name == "input":
            input_type = str(element.get("type") or "text").lower()
            if input_type in {"button", "submit", "reset", "file", "image"}:
                continue
            if input_type in {"checkbox", "radio"} and not element.has_attr("checked"):
                continue
            fields.append((name, str(element.get("value") or "")))
            continue

        if tag_name == "select":
            selected_options = element.find_all("option", selected=True)
            if not selected_options:
                first_option = element.find("option")
                selected_options = [first_option] if first_option else []
            for option in selected_options:
                fields.append((name, str(option.get("value") or "")))
            continue

        fields.append((name, element.get_text("", strip=True)))

    return fields


def _request_headers() -> dict[str, str]:
    return {
        "User-Agent": USER_AGENT,
        "Accept": "text/csv,text/plain,*/*",
        "Accept-Language": "en-AU,en;q=0.9",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def _fetch_export(
    spec: QldEcqExportSpec,
    raw_dir: Path,
    *,
    page_metadata_path: Path | None = None,
) -> dict[str, object]:
    page_source = get_source(spec.page_source_id)
    if page_metadata_path is None:
        page_metadata_path = _latest_metadata(page_source.source_id, raw_dir=raw_dir)
        if page_metadata_path is None:
            page_metadata_path = fetch_source(page_source, raw_dir=raw_dir)

    page_metadata = json.loads(page_metadata_path.read_text(encoding="utf-8"))
    page_body_path = Path(page_metadata["body_path"])
    fields = form_fields_from_html(page_body_path.read_text(encoding="utf-8", errors="replace"))
    if not fields:
        raise RuntimeError(f"No form fields found in {page_body_path} for {spec.export_name}")

    export_source = get_source(spec.export_source_id)
    run_ts = _timestamp()
    target_dir = raw_dir / export_source.source_id / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)

    body = urlencode(fields).encode("utf-8")
    request_headers = _request_headers()
    request = Request(export_source.url, data=body, headers=request_headers)
    try:
        with urlopen(request, timeout=60) as response:
            response_body = response.read()
            status = response.status
            headers = _safe_response_headers(dict(response.headers.items()))
            final_url = response.url
    except HTTPError as exc:
        response_body = exc.read()
        status = exc.code
        headers = _safe_response_headers(dict(exc.headers.items()) if exc.headers else {})
        final_url = export_source.url

    content_type = headers.get("Content-Type") or headers.get("content-type")
    suffix = _suffix_for_content(final_url, content_type)
    body_path = target_dir / f"body{suffix}"
    body_path.write_bytes(response_body)
    sha256 = hashlib.sha256(response_body).hexdigest()

    metadata = {
        "source": asdict(export_source),
        "fetched_at": run_ts,
        "ok": 200 <= status < 400,
        "http_status": status,
        "final_url": final_url,
        "content_type": content_type,
        "content_length": len(response_body),
        "sha256": sha256,
        "body_path": str(body_path),
        "headers": headers,
        "request_headers": request_headers,
        "form_source_id": page_source.source_id,
        "form_source_metadata_path": str(page_metadata_path),
        "form_source_body_path": str(page_body_path),
        "form_field_count": len(fields),
        "form_field_names": [name for name, _ in fields],
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not metadata["ok"]:
        raise RuntimeError(
            f"Fetch failed for {export_source.source_id}: HTTP {status}; metadata: {metadata_path}"
        )

    return {
        "export_name": spec.export_name,
        "source_id": export_source.source_id,
        "metadata_path": str(metadata_path),
        "body_path": str(body_path),
        "http_status": status,
        "content_type": content_type,
        "content_length": len(response_body),
        "form_field_count": len(fields),
    }


def fetch_qld_ecq_eds_exports(
    export_names: list[str] | None = None,
    page_metadata_paths: Mapping[str, Path] | None = None,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    requested = set(export_names or [spec.export_name for spec in QLD_ECQ_EDS_EXPORTS])
    specs = [spec for spec in QLD_ECQ_EDS_EXPORTS if spec.export_name in requested]
    unknown = requested - {spec.export_name for spec in QLD_ECQ_EDS_EXPORTS}
    if unknown:
        raise ValueError(f"Unknown QLD ECQ EDS export(s): {', '.join(sorted(unknown))}")
    if not specs:
        raise ValueError("No QLD ECQ EDS exports selected")

    if page_metadata_paths is not None:
        missing = [spec.page_source_id for spec in specs if spec.page_source_id not in page_metadata_paths]
        if missing:
            raise ValueError(
                "Missing QLD ECQ page metadata path(s): " + ", ".join(sorted(missing))
            )

    outputs = [
        _fetch_export(
            spec,
            raw_dir=raw_dir,
            page_metadata_path=(
                Path(page_metadata_paths[spec.page_source_id])
                if page_metadata_paths is not None
                else None
            ),
        )
        for spec in specs
    ]
    timestamp = _timestamp()
    target_dir = processed_dir / "qld_ecq_eds_exports"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "export_names": [spec.export_name for spec in specs],
        "export_count": len(outputs),
        "outputs": outputs,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def _latest_export_metadata(source_id: str, raw_dir: Path) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    if metadata_path is None:
        raise FileNotFoundError(
            f"No metadata found for {source_id}; run `fetch-qld-ecq-eds-exports` first."
        )
    return metadata_path


def _iter_csv_rows(path: Path):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            yield row_number, {key: (value or "").strip() for key, value in row.items()}


def _infer_qld_jurisdiction(row: dict[str, str]) -> tuple[str, str, str, str]:
    election = (row.get("Election") or "").lower()
    if "local government" in election:
        return (
            "Queensland local governments",
            "local",
            "QLD-LOCAL",
            "election_name_contains_local_government",
        )
    if row.get("Local Electorate"):
        return (
            "Queensland local governments",
            "local",
            "QLD-LOCAL",
            "local_electorate_present",
        )
    return "Queensland", "state", "QLD", "no_local_government_marker"


def _base_record(
    *,
    source_metadata_path: Path,
    source_body_path: Path,
    source_table: str,
    row_number: int,
    row: dict[str, str],
    flow_kind: str,
    source_raw_name: str,
    recipient_raw_name: str,
    receipt_type: str,
    date_value: str,
    amount_value: str,
    return_type: str,
    extra_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    amount_aud = parse_money(amount_value)
    if amount_value and not amount_aud:
        raise ValueError(
            f"Could not parse QLD ECQ amount {amount_value!r} in {source_table}:{row_number}"
        )
    jurisdiction_name, jurisdiction_level, jurisdiction_code, jurisdiction_reason = (
        _infer_qld_jurisdiction(row)
    )
    return {
        "source_dataset": SOURCE_DATASET,
        "source_table": source_table,
        "source_row_number": str(row_number),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "flow_kind": flow_kind,
        "financial_year": "",
        "return_type": return_type,
        "source_raw_name": source_raw_name,
        "recipient_raw_name": recipient_raw_name,
        "receipt_type": receipt_type,
        "date": date_value,
        "amount_aud": amount_aud,
        "jurisdiction_name": jurisdiction_name,
        "jurisdiction_level": jurisdiction_level,
        "jurisdiction_code": jurisdiction_code,
        "jurisdiction_level_inference": {
            "method": "qld_ecq_eds_export_fields_v1",
            "reason": jurisdiction_reason,
        },
        "disclosure_system": "qld_ecq_eds",
        "public_amount_counting_role": "single_observation",
        "source_metadata_path": str(source_metadata_path),
        "source_body_path": str(source_body_path),
        "original": row,
        **(extra_metadata or {}),
    }


def _normalize_gift_row(
    *,
    source_metadata_path: Path,
    source_body_path: Path,
    row_number: int,
    row: dict[str, str],
) -> dict[str, object]:
    political_donation = (row.get("Political donation") or "").strip().lower() == "yes"
    return _base_record(
        source_metadata_path=source_metadata_path,
        source_body_path=source_body_path,
        source_table="qld_ecq_eds_map_export_csv",
        row_number=row_number,
        row=row,
        flow_kind="qld_gift",
        source_raw_name=row.get("Donor") or "Unknown donor",
        recipient_raw_name=row.get("Recipient") or "Unknown recipient",
        receipt_type="Political Donation" if political_donation else "Gift",
        date_value=row.get("Date Gift Made") or "",
        amount_value=row.get("Gift value") or "",
        return_type="ECQ EDS Gift Map Export",
        extra_metadata={
            "transaction_kind": "political_donation" if political_donation else "gift",
            "event_name": row.get("Election") or "",
            "political_donation": political_donation,
            "electoral_committee": row.get("Electoral committee") or "",
            "electoral_committee_name": row.get("Name of electoral committee") or "",
        },
    )


def _normalize_expenditure_row(
    *,
    source_metadata_path: Path,
    source_body_path: Path,
    row_number: int,
    row: dict[str, str],
) -> dict[str, object]:
    return _base_record(
        source_metadata_path=source_metadata_path,
        source_body_path=source_body_path,
        source_table="qld_ecq_eds_expenditure_export_csv",
        row_number=row_number,
        row=row,
        flow_kind="qld_electoral_expenditure",
        source_raw_name=row.get("Incurred By") or "Unknown spender",
        recipient_raw_name="Unknown expenditure recipient",
        receipt_type="Electoral Expenditure",
        date_value=row.get("Date Incurred") or "",
        amount_value=row.get("Value") or "",
        return_type="ECQ EDS Electoral Expenditure Export",
        extra_metadata={
            "transaction_kind": "electoral_expenditure",
            "event_name": row.get("Election") or "",
            "candidate_type": row.get("Candidate Type") or "",
            "local_electorate": row.get("Local Electorate") or "",
            "description_of_goods_or_services": row.get("Description of Goods or Services") or "",
            "purpose_of_expenditure": row.get("Purpose of the Expenditure") or "",
            "campaign_support_attribution": {
                "tier": "observed_state_local_campaign_expenditure",
                "not_personal_receipt": True,
                "notes": [
                    "ECQ records electoral expenditure incurred; this is campaign-support context, not money received by a person."
                ],
            },
        },
    )


def normalize_qld_ecq_eds_money_flows(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    export_metadata_paths: Mapping[str, Path] | None = None,
) -> Path:
    export_specs = {
        "qld_ecq_eds_map_export_csv": _normalize_gift_row,
        "qld_ecq_eds_expenditure_export_csv": _normalize_expenditure_row,
    }
    timestamp = _timestamp()
    target_dir = processed_dir / "qld_ecq_eds_money_flows"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    total_count = 0
    missing_amount_count = 0
    table_counts: dict[str, int] = {}
    source_metadata_paths: dict[str, str] = {}
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for source_id, normalizer in export_specs.items():
            if export_metadata_paths is not None:
                if source_id not in export_metadata_paths:
                    raise ValueError(f"Missing QLD ECQ export metadata path for {source_id}")
                metadata_path = Path(export_metadata_paths[source_id])
            else:
                metadata_path = _latest_export_metadata(source_id, raw_dir=raw_dir)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body_path = Path(metadata["body_path"])
            source_metadata_paths[source_id] = str(metadata_path)
            table_count = 0
            for row_number, row in _iter_csv_rows(body_path):
                record = normalizer(
                    source_metadata_path=metadata_path,
                    source_body_path=body_path,
                    row_number=row_number,
                    row=row,
                )
                if not record["amount_aud"]:
                    missing_amount_count += 1
                table_count += 1
                total_count += 1
                handle.write(json.dumps(record, sort_keys=True) + "\n")
            table_counts[source_id] = table_count

    if total_count == 0:
        raise RuntimeError("No QLD ECQ EDS rows normalized from latest CSV exports")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "source_metadata_paths": source_metadata_paths,
        "total_count": total_count,
        "missing_amount_count": missing_amount_count,
        "table_counts": table_counts,
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def _latest_lookup_metadata(source_id: str, raw_dir: Path) -> Path:
    metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
    if metadata_path is None:
        source = get_source(source_id)
        metadata_path = fetch_source(source, raw_dir=raw_dir)
    return metadata_path


def _participant_aliases(display_name: str) -> list[str]:
    aliases: list[str] = []
    if "(" in display_name and ")" in display_name:
        before_parenthesis = display_name.split("(", maxsplit=1)[0].strip()
        if before_parenthesis and before_parenthesis != display_name:
            aliases.append(before_parenthesis)
    return aliases


def _participant_record(
    *,
    spec: QldEcqLookupSpec,
    source_metadata_path: Path,
    source_body_path: Path,
    raw_record: dict[str, object],
) -> dict[str, object] | None:
    external_id = str(raw_record.get(spec.id_field) or "").strip()
    display_name = str(raw_record.get(spec.name_field) or "").strip()
    normalized = normalize_name(display_name)
    if not external_id or not normalized:
        return None

    identifier = {
        "identifier_type": spec.identifier_type,
        "identifier_value": external_id,
    }
    return {
        "parser_name": PARTICIPANT_PARSER_NAME,
        "parser_version": PARTICIPANT_PARSER_VERSION,
        "schema_version": "qld_ecq_eds_participant_v1",
        "source_dataset": SOURCE_DATASET,
        "source_id": spec.source_id,
        "source_record_type": spec.source_record_type,
        "source_metadata_path": str(source_metadata_path),
        "source_body_path": str(source_body_path),
        "stable_key": f"{spec.source_id}:{spec.source_record_type}:{external_id}",
        "external_id": external_id,
        "display_name": display_name,
        "normalized_name": normalized,
        "entity_type": spec.entity_type,
        "public_sector": "unknown",
        "confidence": "exact_identifier",
        "status": "active",
        "evidence_note": (
            "Queensland ECQ Electronic Disclosure System lookup API participant record."
        ),
        "identifiers": [identifier],
        "aliases": _participant_aliases(display_name),
        "raw_record": raw_record,
        "metadata": {
            "jurisdiction_name": "Queensland",
            "level": spec.level,
            "identifier_type": spec.identifier_type,
            "source_lookup": "qld_ecq_eds_public_api",
        },
    }


def normalize_qld_ecq_eds_participants(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    lookup_metadata_paths: Mapping[str, Path] | None = None,
) -> Path:
    timestamp = _timestamp()
    target_dir = processed_dir / "qld_ecq_eds_participants"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    total_count = 0
    skipped_count = 0
    source_counts: dict[str, int] = {}
    source_metadata_paths: dict[str, str] = {}
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for spec in QLD_ECQ_EDS_PARTICIPANT_LOOKUPS:
            if lookup_metadata_paths is not None:
                if spec.source_id not in lookup_metadata_paths:
                    raise ValueError(
                        f"Missing QLD ECQ participant lookup metadata path for {spec.source_id}"
                    )
                metadata_path = Path(lookup_metadata_paths[spec.source_id])
            else:
                metadata_path = _latest_lookup_metadata(spec.source_id, raw_dir=raw_dir)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body_path = Path(metadata["body_path"])
            rows = json.loads(body_path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise RuntimeError(f"Expected JSON list in {body_path}")
            source_metadata_paths[spec.source_id] = str(metadata_path)
            source_count = 0
            for row in rows:
                if not isinstance(row, dict):
                    skipped_count += 1
                    continue
                record = _participant_record(
                    spec=spec,
                    source_metadata_path=metadata_path,
                    source_body_path=body_path,
                    raw_record=row,
                )
                if record is None:
                    skipped_count += 1
                    continue
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                source_count += 1
                total_count += 1
            source_counts[spec.source_id] = source_count

    if total_count == 0:
        raise RuntimeError("No QLD ECQ EDS participant records normalized from lookup APIs")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "source_metadata_paths": source_metadata_paths,
        "total_count": total_count,
        "skipped_count": skipped_count,
        "source_counts": source_counts,
        "normalizer_name": PARTICIPANT_PARSER_NAME,
        "normalizer_version": PARTICIPANT_PARSER_VERSION,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def _context_record(
    *,
    spec: QldEcqContextSpec,
    source_metadata_path: Path,
    source_body_path: Path,
    raw_record: dict[str, object],
) -> dict[str, object] | None:
    external_id = str(raw_record.get(spec.id_field) or "").strip()
    display_name = str(raw_record.get(spec.name_field) or "").strip()
    if not external_id or not display_name:
        return None
    normalized = normalize_name(display_name)
    if not normalized:
        return None

    level = spec.level
    if spec.context_type == "political_event":
        is_state = raw_record.get("isState")
        if is_state is True:
            level = "state"
        elif is_state is False:
            level = "council"

    return {
        "schema_version": "qld_ecq_eds_context_v1",
        "parser_name": CONTEXT_PARSER_NAME,
        "parser_version": CONTEXT_PARSER_VERSION,
        "source_id": spec.source_id,
        "source_record_type": spec.source_record_type,
        "context_type": spec.context_type,
        "external_id": external_id,
        "identifier": {
            "identifier_type": spec.identifier_type,
            "identifier_value": external_id,
        },
        "display_name": display_name,
        "normalized_name": normalized,
        "level": level,
        "stable_key": f"{spec.source_id}:{spec.source_record_type}:{external_id}",
        "source_metadata_path": str(source_metadata_path),
        "source_body_path": str(source_body_path),
        "raw_record": raw_record,
        "metadata": {
            "source_lookup": "qld_ecq_eds_public_api",
            "code": raw_record.get("code"),
            "event_type": raw_record.get("eventType"),
            "is_state": raw_record.get("isState"),
            "polling_date": raw_record.get("pollingDate"),
            "start_date": raw_record.get("startDate"),
        },
    }


def normalize_qld_ecq_eds_contexts(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    lookup_metadata_paths: Mapping[str, Path] | None = None,
) -> Path:
    timestamp = _timestamp()
    target_dir = processed_dir / "qld_ecq_eds_contexts"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    total_count = 0
    skipped_count = 0
    source_counts: dict[str, int] = {}
    context_type_counts: dict[str, int] = {}
    source_metadata_paths: dict[str, str] = {}
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for spec in QLD_ECQ_EDS_CONTEXT_LOOKUPS:
            if lookup_metadata_paths is not None:
                if spec.source_id not in lookup_metadata_paths:
                    raise ValueError(
                        f"Missing QLD ECQ context lookup metadata path for {spec.source_id}"
                    )
                metadata_path = Path(lookup_metadata_paths[spec.source_id])
            else:
                metadata_path = _latest_lookup_metadata(spec.source_id, raw_dir=raw_dir)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body_path = Path(metadata["body_path"])
            rows = json.loads(body_path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise RuntimeError(f"Expected JSON list in {body_path}")
            source_metadata_paths[spec.source_id] = str(metadata_path)
            source_count = 0
            for row in rows:
                if not isinstance(row, dict):
                    skipped_count += 1
                    continue
                record = _context_record(
                    spec=spec,
                    source_metadata_path=metadata_path,
                    source_body_path=body_path,
                    raw_record=row,
                )
                if record is None:
                    skipped_count += 1
                    continue
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                source_count += 1
                total_count += 1
                context_type = str(record["context_type"])
                context_type_counts[context_type] = context_type_counts.get(context_type, 0) + 1
            source_counts[spec.source_id] = source_count

    if total_count == 0:
        raise RuntimeError("No QLD ECQ EDS context records normalized from lookup APIs")

    summary = {
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path),
        "source_metadata_paths": source_metadata_paths,
        "total_count": total_count,
        "skipped_count": skipped_count,
        "source_counts": source_counts,
        "context_type_counts": context_type_counts,
        "normalizer_name": CONTEXT_PARSER_NAME,
        "normalizer_version": CONTEXT_PARSER_VERSION,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
