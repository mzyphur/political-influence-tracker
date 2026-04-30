from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, PROJECT_ROOT, RAW_DIR
from au_politics_money.ingest.fetch import fetch_source
from au_politics_money.models import SourceRecord


PARSER_NAME = "aec_electorate_finder_postcode_normalizer"
PARSER_VERSION = "1"
SOURCE_DATASET = "aec_electorate_finder_postcode"
SOURCE_ID_PREFIX = "aec_electorate_finder_postcode"
SOURCE_URL_TEMPLATE = (
    "https://electorate.aec.gov.au/LocalitySearchResults.aspx"
    "?filter={postcode}&filterby=Postcode"
)
SOURCE_BOUNDARY_CONTEXT = "next_federal_election_electorates"
CURRENT_MEMBER_CONTEXT = "previous_election_or_subsequent_by_election_member"
POSTCODE_CAVEAT = (
    "AEC postcode search can return multiple federal electorates because a postcode "
    "can contain multiple localities or split across boundaries. Postcode results "
    "are electorate candidates, not address-level determinations. The AEC electorate "
    "finder can reflect electorates for the next federal election; current local "
    "members remain tied to the electorates in place at the previous federal election "
    "or a subsequent by-election."
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _project_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _postcodes_hash(postcodes: list[str]) -> str:
    payload = "\n".join(postcodes) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_postcode(value: str) -> str:
    postcode = (value or "").strip()
    if not re.fullmatch(r"\d{4}", postcode):
        raise ValueError(f"Expected a four-digit Australian postcode, got {value!r}")
    return postcode


def _source_for_postcode(postcode: str) -> SourceRecord:
    postcode = _validate_postcode(postcode)
    return SourceRecord(
        source_id=f"{SOURCE_ID_PREFIX}_{postcode}",
        name=f"AEC Electorate Finder postcode {postcode}",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="postcode_locality_electorate_lookup",
        url=SOURCE_URL_TEMPLATE.format(postcode=postcode),
        expected_format="html",
        update_frequency="redistribution_or_aec_update",
        priority="high",
        notes=POSTCODE_CAVEAT,
    )


def _latest_metadata(source_id: str, raw_dir: Path = RAW_DIR) -> Path | None:
    source_dir = raw_dir / source_id
    if not source_dir.exists():
        return None
    for candidate in sorted(source_dir.glob("*/metadata.json"), reverse=True):
        try:
            metadata = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if metadata.get("ok") is False:
            continue
        body_path = Path(metadata.get("body_path", ""))
        if body_path.exists():
            return candidate
    return None


def latest_aec_electorate_finder_postcodes_jsonl(
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    candidates = sorted((processed_dir / "aec_electorate_finder_postcodes").glob("*.jsonl"))
    return candidates[-1] if candidates else None


def fetch_aec_electorate_finder_postcodes(
    postcodes: list[str],
    *,
    refetch: bool = False,
) -> Path:
    if not postcodes:
        raise ValueError("At least one postcode is required.")

    fetched: list[dict[str, str]] = []
    for raw_postcode in postcodes:
        postcode = _validate_postcode(raw_postcode)
        source = _source_for_postcode(postcode)
        metadata_path = None if refetch else _latest_metadata(source.source_id)
        if metadata_path is None:
            metadata_path = fetch_source(source)
        fetched.append(
            {
                "postcode": postcode,
                "source_id": source.source_id,
                "metadata_path": _project_relative(metadata_path),
            }
        )

    timestamp = _timestamp()
    normalized_postcodes = sorted({_validate_postcode(postcode) for postcode in postcodes})
    target_dir = PROCESSED_DIR / "aec_electorate_finder_postcode_fetches"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "source_dataset": SOURCE_DATASET,
        "postcodes_requested": normalized_postcodes,
        "postcodes_sha256": _postcodes_hash(normalized_postcodes),
        "postcodes_fetched": len(fetched),
        "metadata_paths": fetched,
        "caveat": POSTCODE_CAVEAT,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def _page_updated_text(soup: BeautifulSoup) -> str:
    text = soup.get_text(" ", strip=True)
    match = re.search(r"This page last updated\s+([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4})", text)
    return match.group(1) if match else ""


def _boundary_note(soup: BeautifulSoup) -> str:
    alert = soup.select_one(".alerts--info")
    return _normalize_text(alert.get_text(" ", strip=True)) if alert else ""


def _electorate_links(cell) -> list[dict[str, object]]:
    links: list[dict[str, object]] = []
    for anchor in cell.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        match = re.search(r"(?:[?&])divid=(\d+)", href)
        if not match:
            continue
        links.append(
            {
                "electorate_name": _normalize_text(anchor.get_text(" ", strip=True)),
                "aec_division_id": int(match.group(1)),
                "href": urljoin("https://electorate.aec.gov.au/", href),
            }
        )
    return links


_PAGINATION_CELL_RE = re.compile(r"^\d{1,3}(?:\s+\d{1,3})*$")


def _looks_like_pagination_row(cells: list[str]) -> bool:
    """Return True if every non-empty cell looks like a small set of
    pagination page numbers (the AEC GridView footer renders page
    numbers as one or more short numeric anchors, with whitespace
    separators when multiple anchors collapse into a single cell). The
    cells therefore look like ``"1"``, ``"2"``, ``"1 2"``, or
    ``"1 2 3 4"``. Without this guard the row is mistaken for a real
    locality data row and the postcode validator raises mid-normalize.
    """
    nonempty = [cell for cell in cells if cell]
    if not nonempty:
        return False
    return all(_PAGINATION_CELL_RE.match(cell) for cell in nonempty)


def _table_rows(soup: BeautifulSoup) -> list[dict[str, object]]:
    table = soup.find("table", id="ContentPlaceHolderBody_gridViewLocalities")
    if table is None:
        return []
    headers: list[str] = []
    rows: list[dict[str, object]] = []
    for tr in table.find_all("tr"):
        raw_cells = tr.find_all(["th", "td"])
        cells = [_normalize_text(cell.get_text(" ", strip=True)) for cell in raw_cells]
        if not cells:
            continue
        if not headers:
            headers = cells
            continue
        if _looks_like_pagination_row(cells):
            # AEC GridView pagination footer; skip silently.
            continue
        row: dict[str, object] = {
            headers[index]: value for index, value in enumerate(cells[: len(headers)])
        }
        for index, header in enumerate(headers[: len(raw_cells)]):
            if header == "Electorate(s)":
                row["electorate_links"] = _electorate_links(raw_cells[index])
            elif header == "Redistributed Electorate(s)":
                row["redistributed_electorate_links"] = _electorate_links(raw_cells[index])
        rows.append(row)
    return rows


def _split_electorates(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return []
    return [
        part.strip()
        for part in re.split(r"\s*(?:,|;|/|\band\b)\s*", cleaned)
        if part.strip()
    ]


def parse_aec_electorate_finder_postcode_html(
    html: str,
    *,
    postcode: str,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    postcode = _validate_postcode(postcode)
    soup = BeautifulSoup(html, "html.parser")
    page_updated_text = _page_updated_text(soup)
    boundary_note = _boundary_note(soup)
    source_rows = _table_rows(soup)
    grouped: dict[tuple[str, str], dict[str, object]] = {}
    electorate_names_by_postcode: set[str] = set()

    for row_number, source_row in enumerate(source_rows, start=1):
        # Defensive: if a row escapes the pagination filter and lands
        # here with a non-postcode "Postcode" cell, skip it instead of
        # raising. Pagination rows should already be filtered by
        # `_table_rows`, but keeping this guard means a future AEC
        # template change cannot crash the entire normalize step on a
        # single weird row.
        raw_row_postcode = str(source_row.get("Postcode", postcode) or postcode)
        try:
            row_postcode = _validate_postcode(raw_row_postcode)
        except ValueError:
            continue
        if row_postcode != postcode:
            continue
        state = str(source_row.get("State", ""))
        locality = str(source_row.get("Locality/Suburb", ""))
        electorates = _split_electorates(str(source_row.get("Electorate(s)", "")))
        redistributed = _split_electorates(str(source_row.get("Redistributed Electorate(s)", "")))
        other_locality = str(source_row.get("Other Locality(s)", ""))
        electorate_links = [
            item for item in source_row.get("electorate_links", []) if isinstance(item, dict)
        ]
        for electorate in electorates:
            electorate_names_by_postcode.add(electorate)
            key = (row_postcode, electorate)
            record = grouped.setdefault(
                key,
                {
                    "source_dataset": SOURCE_DATASET,
                    "postcode": row_postcode,
                    "state_or_territory": state,
                    "electorate_name": electorate,
                    "match_method": "aec_postcode_locality_search",
                    "localities": [],
                    "redistributed_electorates": [],
                    "other_localities": [],
                    "aec_division_ids": [],
                    "original_rows": [],
                    "page_updated_text": page_updated_text,
                    "source_boundary_context": SOURCE_BOUNDARY_CONTEXT,
                    "current_member_context": CURRENT_MEMBER_CONTEXT,
                    "aec_boundary_note": boundary_note,
                    "normalizer_name": PARSER_NAME,
                    "normalizer_version": PARSER_VERSION,
                    "caveat": POSTCODE_CAVEAT,
                },
            )
            if locality and locality not in record["localities"]:
                record["localities"].append(locality)
            for redistributed_name in redistributed:
                if redistributed_name not in record["redistributed_electorates"]:
                    record["redistributed_electorates"].append(redistributed_name)
            if other_locality and other_locality not in record["other_localities"]:
                record["other_localities"].append(other_locality)
            for link in electorate_links:
                if _normalize_text(str(link.get("electorate_name") or "")) != electorate:
                    continue
                division_id = link.get("aec_division_id")
                if division_id and division_id not in record["aec_division_ids"]:
                    record["aec_division_ids"].append(division_id)
            record["original_rows"].append(
                {
                    "source_row_number": row_number,
                    "row": source_row,
                }
            )

    electorate_count = max(1, len(electorate_names_by_postcode))
    records: list[dict[str, object]] = []
    for record in grouped.values():
        record["locality_count"] = len(record["localities"])
        record["confidence"] = round(1 / electorate_count, 4)
        record["ambiguity"] = "ambiguous_postcode" if electorate_count > 1 else "single_electorate"
        records.append(record)

    records.sort(key=lambda item: (str(item["postcode"]), str(item["electorate_name"])))
    summary = {
        "postcode": postcode,
        "source_row_count": len(source_rows),
        "electorate_count": len(electorate_names_by_postcode),
        "records": len(records),
        "page_updated_text": page_updated_text,
        "source_boundary_context": SOURCE_BOUNDARY_CONTEXT,
        "current_member_context": CURRENT_MEMBER_CONTEXT,
        "aec_boundary_note": boundary_note,
        "caveat": POSTCODE_CAVEAT,
    }
    return records, summary


def _metadata_paths_for_postcodes(
    postcodes: list[str] | None,
    raw_dir: Path = RAW_DIR,
) -> list[Path]:
    if postcodes:
        paths: list[Path] = []
        for raw_postcode in postcodes:
            postcode = _validate_postcode(raw_postcode)
            source_id = f"{SOURCE_ID_PREFIX}_{postcode}"
            metadata_path = _latest_metadata(source_id, raw_dir=raw_dir)
            if metadata_path is None:
                raise FileNotFoundError(
                    f"No AEC electorate finder raw metadata found for postcode {postcode}. "
                    "Run `fetch-aec-electorate-finder-postcodes` first."
                )
            paths.append(metadata_path)
        return paths

    source_dirs = sorted(raw_dir.glob(f"{SOURCE_ID_PREFIX}_*"))
    paths_by_postcode: dict[str, Path] = {}
    for source_dir in source_dirs:
        postcode = source_dir.name.removeprefix(f"{SOURCE_ID_PREFIX}_")
        if not re.fullmatch(r"\d{4}", postcode):
            continue
        metadata_path = _latest_metadata(source_dir.name, raw_dir=raw_dir)
        if metadata_path is not None:
            paths_by_postcode[postcode] = metadata_path
    return [paths_by_postcode[key] for key in sorted(paths_by_postcode)]


def normalize_aec_electorate_finder_postcodes(
    postcodes: list[str] | None = None,
    *,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    metadata_paths = _metadata_paths_for_postcodes(postcodes, raw_dir=raw_dir)
    if not metadata_paths:
        raise FileNotFoundError(
            "No AEC electorate finder postcode raw metadata found. "
            "Run `fetch-aec-electorate-finder-postcodes --postcode <POSTCODE>` first."
        )

    records: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for metadata_path in metadata_paths:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        source_id = metadata["source"]["source_id"]
        postcode = source_id.removeprefix(f"{SOURCE_ID_PREFIX}_")
        body_path = Path(metadata["body_path"])
        parsed_records, parsed_summary = parse_aec_electorate_finder_postcode_html(
            body_path.read_text(encoding="utf-8", errors="replace"),
            postcode=postcode,
        )
        for record in parsed_records:
            record["source_metadata_path"] = _project_relative(metadata_path)
            record["source_body_path"] = _project_relative(body_path)
        records.extend(parsed_records)
        summaries.append(
            {
                **parsed_summary,
                "source_id": source_id,
                "source_metadata_path": _project_relative(metadata_path),
            }
        )

    timestamp = _timestamp()
    input_postcodes = sorted(
        {
            _validate_postcode(str(summary.get("postcode") or ""))
            for summary in summaries
            if summary.get("postcode")
        }
    )
    target_dir = processed_dir / "aec_electorate_finder_postcodes"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_dataset": SOURCE_DATASET,
        "jsonl_path": _project_relative(jsonl_path),
        "normalizer_name": PARSER_NAME,
        "normalizer_version": PARSER_VERSION,
        "postcodes_requested": input_postcodes,
        "postcodes_sha256": _postcodes_hash(input_postcodes),
        "postcodes_processed": len(summaries),
        "record_count": len(records),
        "ambiguous_postcode_count": sum(
            1 for item in summaries if int(item.get("electorate_count") or 0) > 1
        ),
        "postcodes": summaries,
        "caveat": POSTCODE_CAVEAT,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
