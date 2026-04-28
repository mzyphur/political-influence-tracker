from __future__ import annotations

import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

import pdfplumber

from au_politics_money.config import PROCESSED_DIR, RAW_DIR

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@aph\.gov\.au", re.IGNORECASE)
OFFICIAL_PROFILE_SEARCH_URL = (
    "https://www.aph.gov.au/Senators_and_Members/Parliamentarian_Search_Results"
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _latest_metadata_for_prefix(prefix: str, raw_dir: Path = RAW_DIR) -> Path:
    candidates = sorted(raw_dir.glob(f"{prefix}*/**/metadata.json"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No raw metadata found for source prefix {prefix!r}")
    return candidates[0]


def _latest_optional_metadata_for_prefix(prefix: str, raw_dir: Path = RAW_DIR) -> Path | None:
    candidates = sorted(raw_dir.glob(f"{prefix}*/**/metadata.json"), reverse=True)
    return candidates[0] if candidates else None


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


def _email_key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _email_lookup_candidates(
    row: dict[str, str],
    chamber: str,
    ambiguous_senate_surnames: set[str] | None = None,
) -> list[str]:
    surname = row.get("Surname", "")
    first = row.get("First Name", "")
    preferred = row.get("Preferred Name", "")
    candidates: list[str] = []
    if chamber == "house":
        for given in (preferred, first):
            if given and surname:
                candidates.append(_email_key(f"{given} {surname} mp"))
    surname_key = _email_key(surname)
    if (
        chamber == "senate"
        and surname
        and surname_key not in (ambiguous_senate_surnames or set())
    ):
        candidates.append(_email_key(f"senator {surname}"))
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _extract_contact_pdf_emails(metadata_path: Path | None) -> dict[str, dict[str, str]]:
    if metadata_path is None:
        return {}
    body_path = _body_path_from_metadata(metadata_path)
    emails: dict[str, dict[str, str]] = {}
    with pdfplumber.open(body_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for email in EMAIL_RE.findall(text):
                key = _email_key(email.split("@", 1)[0])
                emails[key] = {
                    "email": email,
                    "email_source_metadata_path": str(metadata_path),
                    "email_source_body_path": str(body_path),
                }
    return emails


def _contact_email_for_row(
    row: dict[str, str],
    chamber: str,
    email_index: dict[str, dict[str, str]],
    ambiguous_senate_surnames: set[str] | None = None,
) -> dict[str, str]:
    for candidate in _email_lookup_candidates(row, chamber, ambiguous_senate_surnames):
        if candidate in email_index:
            return email_index[candidate]
    return {"email": "", "email_source_metadata_path": "", "email_source_body_path": ""}


def _official_profile_search_url(query: str) -> str:
    return f"{OFFICIAL_PROFILE_SEARCH_URL}?{urlencode({'q': query})}"


def _address_text(
    line_1: str,
    line_2: str,
    suburb: str,
    state: str,
    postcode: str,
) -> str:
    street = _join_name(line_1, line_2)
    locality = _join_name(suburb, state, postcode)
    return ", ".join(part for part in (street, locality) if part)


def _contact_fields(
    row: dict[str, str],
    chamber: str,
    canonical_name: str,
    email_record: dict[str, str],
) -> dict[str, str]:
    parliamentary_phone = row.get("Telephone", "")
    electorate_phone = row.get("Electorate Telephone", "")
    fax = row.get("Electorate Fax", "")
    tollfree = row.get("Electorate TollFree", "")
    physical_address = _address_text(
        row.get("Electorate Address Line 1", ""),
        row.get("Electorate Address Line 2", ""),
        row.get("Electorate Suburb", ""),
        row.get("Electorate State", ""),
        row.get("Electorate PostCode", ""),
    )
    postal_address = _address_text(
        row.get("Electorate Postal Address", "") or row.get("Label Address", ""),
        "",
        row.get("Electorate Postal Suburb", "") or row.get("Label Suburb", ""),
        row.get("Electorate Postal State", "") or row.get("Label State", ""),
        row.get("Electorate Postal Postcode", "")
        or row.get("Label Postcode", "")
        or row.get("Label postcode", ""),
    )
    chamber_label = "House of Representatives" if chamber == "house" else "Senate"
    parliament_address = (
        f"Parliament House, {chamber_label}, Canberra ACT 2600"
        if chamber == "house"
        else "Parliament House, The Senate, Canberra ACT 2600"
    )
    return {
        "email": email_record.get("email", ""),
        "email_source_metadata_path": email_record.get("email_source_metadata_path", ""),
        "email_source_body_path": email_record.get("email_source_body_path", ""),
        "parliamentary_phone": parliamentary_phone,
        "electorate_phone": electorate_phone,
        "electorate_fax": fax,
        "electorate_tollfree": tollfree,
        "electorate_office_address": physical_address,
        "electorate_postal_address": postal_address,
        "parliament_office_address": parliament_address,
        "official_profile_search_url": _official_profile_search_url(canonical_name),
        "contact_data_source": "aph_contacts_csv",
        "email_data_source": "aph_contact_list_pdf" if email_record.get("email") else "",
    }


def _member_record(
    row_number: int,
    row: dict[str, str],
    source_metadata_path: Path,
    email_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    preferred_or_first = row.get("Preferred Name") or row.get("First Name")
    canonical_name = _join_name(preferred_or_first, row.get("Surname"))
    display_name = _join_name(row.get("Honorific"), canonical_name)
    email_record = _contact_email_for_row(row, "house", email_index)
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
        **_contact_fields(row, "house", canonical_name, email_record),
    }


def _senator_record(
    row_number: int,
    row: dict[str, str],
    source_metadata_path: Path,
    email_index: dict[str, dict[str, str]],
    ambiguous_senate_surnames: set[str] | None = None,
) -> dict[str, str]:
    preferred_or_first = row.get("Preferred Name") or row.get("First Name")
    canonical_name = _join_name(preferred_or_first, row.get("Surname"))
    display_name = _join_name(row.get("Title"), canonical_name)
    email_record = _contact_email_for_row(
        row,
        "senate",
        email_index,
        ambiguous_senate_surnames,
    )
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
        **_contact_fields(row, "senate", canonical_name, email_record),
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
    email_index = {
        **_extract_contact_pdf_emails(
            _latest_optional_metadata_for_prefix("aph_members_contact_list_pdf", raw_dir=raw_dir)
        ),
        **_extract_contact_pdf_emails(
            _latest_optional_metadata_for_prefix("aph_senators_contact_list_pdf", raw_dir=raw_dir)
        ),
        **_extract_contact_pdf_emails(
            _latest_optional_metadata_for_prefix(
                "aph_contacts_csv__members_list_pdf__",
                raw_dir=raw_dir,
            )
        ),
        **_extract_contact_pdf_emails(
            _latest_optional_metadata_for_prefix("aph_contacts_csv__los_pdf__", raw_dir=raw_dir)
        ),
    }

    member_rows = list(_read_csv_rows(members_path))
    senator_rows = list(_read_csv_rows(senators_path))
    senate_surname_counts = Counter(
        _email_key(row.get("Surname", "")) for _, row in senator_rows if row.get("Surname")
    )
    ambiguous_senate_surnames = {
        surname for surname, count in senate_surname_counts.items() if surname and count > 1
    }

    people: list[dict[str, str]] = []
    for row_number, row in member_rows:
        if row.get("Surname"):
            people.append(_member_record(row_number, row, members_metadata, email_index))
    for row_number, row in senator_rows:
        if row.get("Surname"):
            people.append(
                _senator_record(
                    row_number,
                    row,
                    senators_metadata,
                    email_index,
                    ambiguous_senate_surnames,
                )
            )

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
        "email_count": sum(1 for person in people if person.get("email")),
        "people": people,
    }
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path
