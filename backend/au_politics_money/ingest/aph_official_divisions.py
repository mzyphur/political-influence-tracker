from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR
from au_politics_money.ingest.aph_decision_records import (
    latest_aph_decision_record_documents_summary,
)


PARSER_NAME = "aph_official_divisions_v1"
PARSER_VERSION = "1"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())


def _normalize_name_key(value: str) -> str:
    cleaned = (value or "").replace("*", "")
    cleaned = cleaned.replace("’", "'")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned.lower())
    return " ".join(cleaned.split())


def latest_roster_path(*, processed_dir: Path = PROCESSED_DIR) -> Path | None:
    roster_dir = processed_dir / "rosters"
    if not roster_dir.exists():
        return None
    candidates = sorted(roster_dir.glob("aph_current_parliament_*.json"), reverse=True)
    return candidates[0] if candidates else None


def latest_official_aph_divisions_jsonl(*, processed_dir: Path = PROCESSED_DIR) -> Path | None:
    target_dir = processed_dir / "aph_official_divisions"
    if not target_dir.exists():
        return None
    candidates = sorted(target_dir.glob("*.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def _label_pattern(label: str) -> re.Pattern[str]:
    escaped = re.escape(label).replace(r"\'", r"['’]")
    escaped = escaped.replace("'", r"['’]")
    escaped = escaped.replace(r"\ ", r"\s+")
    return re.compile(rf"^{escaped}\*{{0,2}}(?=\s|$)")


def _roster_vote_labels(
    *,
    roster_path: Path | None,
    chamber: str,
) -> list[dict[str, str]]:
    if roster_path is None or not roster_path.exists():
        return []
    payload = json.loads(roster_path.read_text(encoding="utf-8"))
    people = [person for person in payload.get("people", []) if person.get("chamber") == chamber]
    surname_counts: dict[str, int] = {}
    for person in people:
        surname_counts[_normalize_name_key(str(person.get("surname") or ""))] = (
            surname_counts.get(_normalize_name_key(str(person.get("surname") or "")), 0) + 1
        )

    labels: dict[str, dict[str, str]] = {}
    for person in people:
        surname = str(person.get("surname") or "").strip()
        first = str(person.get("preferred_name") or person.get("first_name") or "").strip()
        canonical_name = str(person.get("canonical_name") or "").strip()
        for label in (
            surname if surname_counts.get(_normalize_name_key(surname)) == 1 else "",
            f"{surname}, {first}" if surname and first else "",
            canonical_name,
        ):
            label = _clean_text(label)
            if not label:
                continue
            labels[label] = {
                "label": label,
                "name_key": _normalize_name_key(label),
                "canonical_name": canonical_name,
                "state": str(person.get("state") or ""),
                "party": str(person.get("party") or ""),
            }

    rows = list(labels.values())
    rows.sort(key=lambda item: len(item["label"]), reverse=True)
    for row in rows:
        row["pattern"] = _label_pattern(row["label"])  # type: ignore[assignment]
    return rows


def _parse_vote_name_lines(
    lines: list[str],
    *,
    vote: str,
    labels: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    votes: list[dict[str, Any]] = []
    warnings: list[str] = []
    for line in lines:
        remaining = _clean_text(line)
        while remaining:
            match_row = None
            match_text = ""
            for label in labels:
                match = label["pattern"].match(remaining)
                if not match:
                    continue
                match_row = label
                match_text = match.group(0)
                break
            if match_row is None:
                warnings.append(f"Unparsed {vote} vote names: {remaining}")
                break
            raw_name = match_text.strip()
            is_teller = raw_name.endswith("*")
            raw_name = raw_name.rstrip("*")
            votes.append(
                {
                    "vote": vote,
                    "raw_name": raw_name,
                    "name_key": match_row["name_key"],
                    "matched_roster_canonical_name": match_row.get("canonical_name", ""),
                    "party": match_row.get("party", ""),
                    "state": match_row.get("state", ""),
                    "is_teller": is_teller,
                    "source_line": line,
                }
            )
            remaining = remaining[match.end() :].strip()
    return votes, warnings


def _find_name_lines(lines: list[str], start: int, stop: int) -> list[str]:
    cursor = start
    while cursor < stop and not re.match(r"^(Senators|Members)[—-]?$", lines[cursor]):
        cursor += 1
    if cursor < stop:
        cursor += 1
    name_lines = []
    while cursor < stop:
        line = lines[cursor]
        if re.match(r"^(No\.|\d+\s+No\.)", line):
            cursor += 1
            continue
        if not line or line.startswith("* Tellers"):
            break
        name_lines.append(line)
        cursor += 1
    return name_lines


def _context_value(lines: list[str], marker_index: int, pattern: str) -> str:
    for line in reversed(lines[max(0, marker_index - 35) : marker_index]):
        if re.search(pattern, line, flags=re.IGNORECASE):
            return line
    return ""


def _division_outcome(lines: list[str], start: int) -> str:
    for line in lines[start : min(len(lines), start + 8)]:
        if re.search(r"\b(Question|Bill|Amendment)\b.*\b(agreed|negatived|passed)\b", line):
            return line
    return ""


def parse_official_divisions_from_text(
    *,
    text: str,
    chamber: str,
    record: dict[str, Any],
    document: dict[str, Any],
    roster_path: Path | None = None,
) -> list[dict[str, Any]]:
    if chamber not in {"senate", "house"}:
        raise ValueError(f"Unsupported APH division chamber: {chamber}")
    chamber_label = "Senate" if chamber == "senate" else "House"
    labels = _roster_vote_labels(roster_path=roster_path, chamber=chamber)
    lines = [_clean_text(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    marker_pattern = re.compile(rf"^The {chamber_label} divided[—-]?$", re.IGNORECASE)
    divisions: list[dict[str, Any]] = []
    marker_indexes = [index for index, line in enumerate(lines) if marker_pattern.match(line)]
    for local_index, marker_index in enumerate(marker_indexes, start=1):
        next_marker = marker_indexes[local_index] if local_index < len(marker_indexes) else len(lines)
        block_lines = lines[marker_index:next_marker]
        try:
            ayes_index = next(
                index
                for index in range(marker_index, next_marker)
                if re.match(r"^AYES?,\s*\d+", lines[index], flags=re.IGNORECASE)
            )
            noes_index = next(
                index
                for index in range(ayes_index + 1, next_marker)
                if re.match(r"^NOES?,\s*\d+", lines[index], flags=re.IGNORECASE)
            )
        except StopIteration:
            continue

        aye_count = int(re.search(r"\d+", lines[ayes_index]).group(0))  # type: ignore[union-attr]
        no_count = int(re.search(r"\d+", lines[noes_index]).group(0))  # type: ignore[union-attr]
        aye_lines = _find_name_lines(lines, ayes_index + 1, noes_index)
        no_lines = _find_name_lines(lines, noes_index + 1, next_marker)
        aye_votes, aye_warnings = _parse_vote_name_lines(aye_lines, vote="aye", labels=labels)
        no_votes, no_warnings = _parse_vote_name_lines(no_lines, vote="no", labels=labels)

        motion_text = _context_value(lines, marker_index, r"\bQuestion\b.*\bput\b|Main question put")
        section_heading = _context_value(lines, marker_index, r"^\d+\s+[A-Z].+")
        bill_name = _context_value(lines, marker_index, r"\bBill\s+\d{4}\b")
        outcome = _division_outcome(lines, noes_index + 1)
        external_seed = (
            f"{record.get('external_key')}|{document.get('source_id')}|"
            f"{document.get('representation_url')}|{local_index}|{motion_text}"
        )
        divisions.append(
            {
                "schema_version": "aph_official_division_v1",
                "parser_name": PARSER_NAME,
                "parser_version": PARSER_VERSION,
                "external_id": (
                    "official_aph:"
                    f"{chamber}:{record.get('record_date')}:{local_index}:"
                    f"{hashlib.sha256(external_seed.encode('utf-8')).hexdigest()[:12]}"
                ),
                "chamber": chamber,
                "division_date": record.get("record_date"),
                "division_number": local_index,
                "title": motion_text or section_heading or f"{chamber_label} division {local_index}",
                "bill_name": bill_name,
                "motion_text": motion_text,
                "aye_count": aye_count,
                "no_count": no_count,
                "possible_turnout": aye_count + no_count,
                "votes": aye_votes + no_votes,
                "source_metadata_path": document.get("metadata_path"),
                "source_url": document.get("representation_url"),
                "official_decision_record_external_key": record.get("external_key"),
                "official_decision_record_title": record.get("title"),
                "representation_kind": document.get("representation_kind"),
                "evidence_status": "official_record_parsed",
                "metadata": {
                    "source": "aph_official_decision_record",
                    "source_evidence_class": "official_record_parsed",
                    "parser_name": PARSER_NAME,
                    "parser_version": PARSER_VERSION,
                    "section_heading": section_heading,
                    "outcome": outcome,
                    "raw_block": "\n".join(block_lines[:120]),
                    "aye_name_lines": aye_lines,
                    "no_name_lines": no_lines,
                    "name_parse_warnings": aye_warnings + no_warnings,
                    "parsed_vote_count": len(aye_votes) + len(no_votes),
                    "expected_vote_count": aye_count + no_count,
                    "vote_count_matches": len(aye_votes) == aye_count and len(no_votes) == no_count,
                    "document_source_id": document.get("source_id"),
                    "document_summary_status": document.get("status"),
                },
            }
        )
    return divisions


def _body_text(metadata_path: Path) -> str:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    body_path = Path(metadata["body_path"])
    if body_path.suffix.lower() == ".pdf":
        chunks: list[str] = []
        with pdfplumber.open(body_path) as pdf:
            for page in pdf.pages:
                chunks.append(page.extract_text(x_tolerance=1, y_tolerance=3) or "")
        return "\n".join(chunks)
    return BeautifulSoup(
        body_path.read_text(encoding="utf-8", errors="replace"),
        "html.parser",
    ).get_text("\n", strip=True)


def extract_official_aph_divisions(
    *,
    document_summary_path: Path | None = None,
    roster_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    summary_path = document_summary_path or latest_aph_decision_record_documents_summary(
        processed_dir=processed_dir
    )
    if summary_path is None:
        raise FileNotFoundError(
            "No APH decision-record document summary found. Run "
            "`au-politics-money fetch-aph-decision-record-documents` first."
        )
    roster_path = roster_path or latest_roster_path(processed_dir=processed_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    divisions: list[dict[str, Any]] = []
    skipped_documents = 0
    documents_seen = 0

    for document in summary.get("documents") or []:
        if document.get("status") not in {"fetched", "skipped_existing"}:
            skipped_documents += 1
            continue
        record = document.get("official_decision_record") or {}
        chamber = record.get("chamber")
        representation_kind = str(document.get("representation_kind") or "")
        if chamber == "senate" and "pdf" not in representation_kind:
            skipped_documents += 1
            continue
        if chamber == "house" and "html" not in representation_kind:
            skipped_documents += 1
            continue
        metadata_path = Path(str(document.get("metadata_path") or ""))
        if not metadata_path.exists():
            skipped_documents += 1
            continue
        documents_seen += 1
        divisions.extend(
            parse_official_divisions_from_text(
                text=_body_text(metadata_path),
                chamber=chamber,
                record=record,
                document=document,
                roster_path=roster_path,
            )
        )

    timestamp = _timestamp()
    target_dir = processed_dir / "aph_official_divisions"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for division in divisions:
            handle.write(json.dumps(division, sort_keys=True) + "\n")

    summary_output = {
        "generated_at": timestamp,
        "document_summary_path": str(summary_path),
        "roster_path": str(roster_path) if roster_path else "",
        "documents_seen": documents_seen,
        "skipped_documents": skipped_documents,
        "division_count": len(divisions),
        "vote_count": sum(len(division.get("votes") or []) for division in divisions),
        "count_mismatch_divisions": sum(
            1
            for division in divisions
            if not (division.get("metadata") or {}).get("vote_count_matches")
        ),
        "jsonl_path": str(jsonl_path),
    }
    summary_json_path = target_dir / f"{timestamp}.summary.json"
    summary_json_path.write_text(
        json.dumps(summary_output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_json_path
