from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from au_politics_money.config import PROCESSED_DIR


SECTION_RE = re.compile(r"(?m)(^|\n)(?P<number>\d{1,2})\.(?:\s+|(?=[A-Z]))(?P<title>[^\n]+)")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_pdf_text_jsonl(prefix: str = "aph_members_interests_48") -> Path:
    source_dir = PROCESSED_DIR / "pdf_text" / prefix
    candidates = sorted(source_dir.glob("*.jsonl"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No PDF text JSONL found under {source_dir}")
    return candidates[0]


def split_numbered_sections(text: str) -> list[dict[str, str]]:
    matches = list(SECTION_RE.finditer(text))
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start("number")
        end = matches[index + 1].start("number") if index + 1 < len(matches) else len(text)
        number = match.group("number")
        title = " ".join(match.group("title").split())
        body = text[start:end].strip()
        sections.append(
            {
                "section_number": number,
                "section_title": title,
                "section_text": body,
            }
        )
    return sections


def _extract_member_metadata(full_text: str) -> dict[str, str]:
    family_match = re.search(r"FAMILY NAME\s+([^\n]+)", full_text)
    if family_match and family_match.group(1).strip().startswith("("):
        family_match = None
    if family_match is None:
        family_match = re.search(
            r"FAMILY NAME\s*(?:\([^\n]+\)\s*)?\n?\s*([A-Z][A-Za-z' -]+)",
            full_text,
        )

    given_match = re.search(r"GIVEN NAMES\s+([^\n]+)", full_text)
    if given_match is None:
        given_match = re.search(r"NAMES\s*\nGIVEN\s+([^\n]+)", full_text)

    state_match = re.search(r"\bSTATE\s+([A-Za-z ]+)", full_text)
    electorate_match = re.search(r"GIVEN NAMES\s+[^\n]+\nELECTORAL\s*\n([^\n]+?)\s+STATE", full_text)
    if electorate_match is None:
        electorate_match = re.search(r"ELECTORAL\s*DIVISION\s+([^\n]+?)\s+STATE", full_text)
    if electorate_match is None:
        electorate_match = re.search(r"ELECTORALDIVISION\s+([^\n]+)", full_text)

    family_name = family_match.group(1).strip() if family_match else ""
    given_names = given_match.group(1).strip() if given_match else ""
    return {
        "family_name": family_name,
        "given_names": given_names,
        "member_name": " ".join(part for part in [given_names, family_name] if part),
        "electorate": electorate_match.group(1).strip() if electorate_match else "",
        "state": state_match.group(1).strip() if state_match else "",
    }


def extract_house_interest_sections(
    pdf_text_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if pdf_text_path is None:
        pdf_text_path = latest_pdf_text_jsonl()

    timestamp = _timestamp()
    target_dir = processed_dir / "house_interest_sections"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    document_count = 0
    skipped_count = 0
    section_count = 0
    gifts_section_count = 0

    with pdf_text_path.open("r", encoding="utf-8") as source_handle, jsonl_path.open(
        "w", encoding="utf-8"
    ) as output_handle:
        for line in source_handle:
            document = json.loads(line)
            full_text = "\n".join(page["text"] for page in document["pages"])
            member_metadata = _extract_member_metadata(full_text)
            if not member_metadata["family_name"] or not member_metadata["given_names"]:
                skipped_count += 1
                continue

            document_count += 1
            for section in split_numbered_sections(full_text):
                record = {
                    "source_id": document["source_id"],
                    "source_name": document["source_name"],
                    "source_metadata_path": document["source_metadata_path"],
                    "body_path": document["body_path"],
                    "url": document["url"],
                    **member_metadata,
                    **section,
                }
                if section["section_number"] == "11":
                    gifts_section_count += 1
                section_count += 1
                output_handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_pdf_text_path": str(pdf_text_path),
        "jsonl_path": str(jsonl_path),
        "document_count": document_count,
        "skipped_count": skipped_count,
        "section_count": section_count,
        "gifts_section_count": gifts_section_count,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
