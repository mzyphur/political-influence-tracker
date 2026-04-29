from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.ingest.sources import get_source


PARSER_NAME = "qld_parliament_current_members_mail_merge_xlsx_v1"
PARSER_VERSION = "1"
SOURCE_ID = "qld_parliament_members_mail_merge_xlsx"
EXPECTED_ELECTORATE_COUNT = 93
XLSX_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata_path(source_id: str, raw_dir: Path = RAW_DIR) -> Path | None:
    source_dir = raw_dir / source_id
    if not source_dir.exists():
        return None
    for run_dir in sorted(source_dir.iterdir(), reverse=True):
        metadata_path = run_dir / "metadata.json"
        if not metadata_path.exists():
            continue
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if metadata.get("ok") is False:
            continue
        if Path(metadata.get("body_path", "")).exists():
            return metadata_path
    return None


def fetch_qld_current_members(*, refetch: bool = False) -> Path:
    source = get_source(SOURCE_ID)
    if not refetch:
        latest = _latest_metadata_path(source.source_id)
        if latest is not None:
            return latest
    return fetch_source(source, timeout=120)


def _column_index(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref)
    if not letters:
        return 0
    index = 0
    for char in letters.group(0):
        index = index * 26 + (ord(char) - ord("A") + 1)
    return index - 1


def _shared_strings(zip_file: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.findall(".//m:t", XLSX_NS))
        for item in root.findall("m:si", XLSX_NS)
    ]


def _xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zip_file:
        shared_strings = _shared_strings(zip_file)
        sheet = ET.fromstring(zip_file.read("xl/worksheets/sheet1.xml"))
        rows: list[list[str]] = []
        for row in sheet.findall(".//m:row", XLSX_NS):
            values: list[str] = []
            for cell in row.findall("m:c", XLSX_NS):
                column_index = _column_index(cell.attrib.get("r", "A1"))
                while len(values) <= column_index:
                    values.append("")
                value_node = cell.find("m:v", XLSX_NS)
                inline_node = cell.find("m:is/m:t", XLSX_NS)
                value = ""
                if inline_node is not None:
                    value = inline_node.text or ""
                elif value_node is not None:
                    value = value_node.text or ""
                    if cell.attrib.get("t") == "s" and value:
                        value = shared_strings[int(value)]
                values[column_index] = value.strip()
            rows.append(values)
    if not rows:
        return []
    headers = [re.sub(r"\s+", " ", header.strip().lower()) for header in rows[0]]
    parsed_rows = []
    for source_row_number, row in enumerate(rows[1:], start=2):
        record = {
            headers[index]: row[index].strip()
            for index in range(min(len(headers), len(row)))
            if headers[index]
        }
        if any(value for value in record.values()):
            record["source_row_number"] = str(source_row_number)
            parsed_rows.append(record)
    return parsed_rows


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\xa0", " ")).strip()


def _electorate_name(value: str) -> str:
    return re.sub(r"^member\s+for\s+", "", _clean(value), flags=re.IGNORECASE).strip()


def _last_name(value: str) -> str:
    return re.sub(r"\s+MP$", "", _clean(value), flags=re.IGNORECASE).strip()


def _display_name(row: dict[str, str]) -> str:
    pieces = [_clean(row.get("title")), _clean(row.get("first")), _last_name(row.get("last", ""))]
    return " ".join(piece for piece in pieces if piece)


def _office_from_row(row: dict[str, str]) -> dict[str, Any] | None:
    address_lines = [
        _clean(row.get("address 1")),
        _clean(row.get("address 2")),
        _clean(row.get("address 3")),
    ]
    address_lines = [line for line in address_lines if line]
    email = _clean(row.get("email address")).lower()
    if not address_lines and not email:
        return None
    return {
        "address_lines": address_lines,
        "email": email,
        "source_row_number": int(row.get("source_row_number") or 0),
    }


def _normalize_member_rows(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    by_electorate: dict[str, dict[str, Any]] = {}
    for row in rows:
        electorate = _electorate_name(row.get("electorate", ""))
        if not electorate:
            continue
        record = by_electorate.setdefault(
            electorate,
            {
                "electorate": electorate,
                "title": _clean(row.get("title")),
                "first_name": _clean(row.get("first")),
                "last_name": _last_name(row.get("last", "")),
                "display_name": _display_name(row),
                "party_short_name": _clean(row.get("party")),
                "portfolio": _clean(row.get("portfolio")),
                "salutation": _clean(row.get("salutation")),
                "electorate_offices": [],
                "source_rows": [],
            },
        )
        office = _office_from_row(row)
        if office:
            record["electorate_offices"].append(office)
        record["source_rows"].append(row)

    normalized = []
    for record in by_electorate.values():
        is_vacant = not record["display_name"] or record["party_short_name"] in {"", "-"}
        email = ""
        for office in record["electorate_offices"]:
            if office.get("email"):
                email = str(office["email"])
                break
        normalized.append(
            {
                **record,
                "email": email,
                "is_vacant": is_vacant,
                "chamber": "state_lower",
                "state_or_territory": "QLD",
                "source_dataset": "qld_parliament_current_members",
                "parser_name": PARSER_NAME,
                "parser_version": PARSER_VERSION,
            }
        )
    return sorted(normalized, key=lambda item: item["electorate"])


def extract_qld_current_members(
    *,
    metadata_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
    expected_electorate_count: int = EXPECTED_ELECTORATE_COUNT,
) -> Path:
    metadata_path = metadata_path or fetch_qld_current_members(refetch=False)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata["body_path"])
    records = _normalize_member_rows(_xlsx_rows(body_path))
    if len(records) != expected_electorate_count:
        raise RuntimeError(
            f"Expected {expected_electorate_count} QLD current member electorates; "
            f"found {len(records)}."
        )

    timestamp = _timestamp()
    output_dir = processed_dir / "qld_parliament_current_members"
    output_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = output_dir / f"{timestamp}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            record["source_metadata_path"] = str(metadata_path.resolve())
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "electorate_count": len(records),
        "member_count": sum(1 for record in records if not record["is_vacant"]),
        "vacancy_count": sum(1 for record in records if record["is_vacant"]),
        "office_row_count": sum(len(record["electorate_offices"]) for record in records),
        "generated_at": timestamp,
        "jsonl_path": str(jsonl_path.resolve()),
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "raw_metadata_path": str(metadata_path.resolve()),
        "raw_sha256": metadata.get("sha256"),
        "source_id": metadata["source"]["source_id"],
        "source_url": metadata["source"]["url"],
        "electorates": [record["electorate"] for record in records],
    }
    summary_path = output_dir / f"{timestamp}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_qld_current_members_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    output_dir = processed_dir / "qld_parliament_current_members"
    if not output_dir.exists():
        return None
    candidates = sorted(output_dir.glob("*.jsonl"), reverse=True)
    return candidates[0] if candidates else None
