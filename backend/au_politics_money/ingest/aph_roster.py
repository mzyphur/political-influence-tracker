from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from au_politics_money.config import PROCESSED_DIR, RAW_DIR


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata_for_prefix(prefix: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted(raw_dir.glob(f"{prefix}*/**/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No raw metadata found for source prefix {prefix!r}")
    return candidates[0]


def _body_path_from_metadata(metadata_path: Path) -> Path:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return Path(metadata["body_path"])


def _read_csv_rows(csv_path: Path) -> Iterable[tuple[int, dict[str, str]]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            yield row_number, {key: (value or "").strip() for key, value in row.items()}


def _join_name(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _member_record(row_number: int, row: dict[str, str], source_metadata_path: Path) -> dict[str, str]:
    preferred_or_first = row.get("Preferred Name") or row.get("First Name")
    canonical_name = _join_name(preferred_or_first, row.get("Surname"))
    display_name = _join_name(row.get("Honorific"), canonical_name)
    return {
        "chamber": "house",
        "display_name": display_name,
        "canonical_name": canonical_name,
        "honorific": row.get("Honorific", ""),
        "first_name": row.get("First Name", ""),
        "other_name": row.get("Other Name", ""),
        "preferred_name": row.get("Preferred Name", ""),
        "surname": row.get("Surname", ""),
        "post_nominals": row.get("Post Nominals", ""),
        "state": row.get("State", ""),
        "electorate": row.get("Electorate", ""),
        "party": row.get("Political Party", ""),
        "gender": row.get("Gender", ""),
        "parliamentary_title": row.get("Parliamentary Title", ""),
        "ministerial_title": row.get("Ministerial Title", ""),
        "source_row_number": str(row_number),
        "source_metadata_path": str(source_metadata_path),
    }


def _senator_record(row_number: int, row: dict[str, str], source_metadata_path: Path) -> dict[str, str]:
    preferred_or_first = row.get("Preferred Name") or row.get("First Name")
    canonical_name = _join_name(preferred_or_first, row.get("Surname"))
    display_name = _join_name(row.get("Title"), canonical_name)
    return {
        "chamber": "senate",
        "display_name": display_name,
        "canonical_name": canonical_name,
        "honorific": row.get("Title", ""),
        "first_name": row.get("First Name", ""),
        "other_name": row.get("Other Name", ""),
        "preferred_name": row.get("Preferred Name", ""),
        "surname": row.get("Surname", ""),
        "post_nominals": row.get("Post Nominals", ""),
        "state": row.get("State", ""),
        "electorate": "",
        "party": row.get("Political Party", ""),
        "gender": row.get("Gender", ""),
        "parliamentary_title": row.get("Parliamentary Titles", ""),
        "ministerial_title": "",
        "source_row_number": str(row_number),
        "source_metadata_path": str(source_metadata_path),
    }


def build_current_parliament_roster(
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    members_metadata = _latest_metadata_for_prefix(
        "aph_contacts_csv__all_members_by_name_csv__",
        raw_dir=raw_dir,
    )
    senators_metadata = _latest_metadata_for_prefix(
        "aph_contacts_csv__allsenstate_csv__",
        raw_dir=raw_dir,
    )

    members_path = _body_path_from_metadata(members_metadata)
    senators_path = _body_path_from_metadata(senators_metadata)

    people: list[dict[str, str]] = []
    for row_number, row in _read_csv_rows(members_path):
        if row.get("Surname"):
            people.append(_member_record(row_number, row, members_metadata))
    for row_number, row in _read_csv_rows(senators_path):
        if row.get("Surname"):
            people.append(_senator_record(row_number, row, senators_metadata))

    timestamp = _timestamp()
    target_dir = processed_dir / "rosters"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"aph_current_parliament_{timestamp}.json"
    payload = {
        "generated_at": timestamp,
        "source_metadata_paths": [str(members_metadata), str(senators_metadata)],
        "people_count": len(people),
        "house_count": sum(1 for person in people if person["chamber"] == "house"),
        "senate_count": sum(1 for person in people if person["chamber"] == "senate"),
        "people": people,
    }
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path

