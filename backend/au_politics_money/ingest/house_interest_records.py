from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from au_politics_money.config import PROCESSED_DIR
from au_politics_money.ingest.interest_extraction import (
    extract_event_date,
    extract_provider,
    extract_reported_value,
)


HOUSE_INTEREST_CATEGORIES = {
    "1": "Shareholdings",
    "2": "Family and business trusts and nominee companies",
    "3": "Real estate",
    "4": "Directorships of companies",
    "5": "Partnerships",
    "6": "Liabilities",
    "7": "Investments",
    "8": "Savings or investment accounts",
    "9": "Other assets",
    "10": "Other income",
    "11": "Gifts",
    "12": "Sponsored travel or hospitality",
    "13": "Memberships with possible conflicts",
    "14": "Other interests",
}

HEADER_LINES = {
    "activities of company",
    "activities of partnership",
    "beneficial interest",
    "beneficial interests",
    "beneficiary of the trust",
    "body in which investment is held",
    "creditor",
    "detail of gifts",
    "details",
    "details of travel/hospitality",
    "details of travel hospitality",
    "electoral division",
    "electoral division i state",
    "electoral division state",
    "family name",
    "given names",
    "hospitality exceeds $300",
    "house of representatives",
    "item details",
    "location purpose for which owned",
    "name",
    "name nature of interest activities of partnership",
    "name of bank/institution",
    "name of bank institution",
    "name of company",
    "name of organisation",
    "name of trust/nominee company",
    "nature of account",
    "nature of any other assets",
    "nature of income",
    "nature of interest",
    "nature of liability creditor",
    "nature of operation",
    "parliament of australia",
    "purpose for which owned",
    "register of members interests",
    "signed",
    "signed date",
    "signature date",
    "state",
    "type of investment",
    "48th parliament",
    "notification of alteration s of interests",
    "notification of al teration s of interests",
}

INSTRUCTION_LINE_PREFIXES = (
    "any sponsored travel or hospitality received",
    "electoral division",
    "family and business trusts and nominee companies",
    "family name",
    "given names",
    "held by the member",
    "hospitality exceeds",
    "in public and private companies",
    "in which a beneficial interest is held",
    "in which the member",
    "including the location",
    "indicating the name",
    "indicate the nature",
    "list any other interest",
    "member for support",
    "membership of any organisation",
    "name of",
    "nature of its operation",
    "i wish to alter my statement",
    "the nature of",
)

NON_VALUES = {
    "as above",
    "n/a",
    "na",
    "nil",
    "nil applicable",
    "no",
    "none",
    "not applicable",
    "not applicable not applicable",
    "not applicable not applicable not applicable",
    "not disclosed",
    "surrendered",
    "unknown",
    "value unknown",
}

STOP_MARKERS = (
    "notification of alteration",
    "i wish to notify an alteration",
    "addition",
    "deletion",
    "submitted date:",
    "processed by registrar",
)

EXPLANATORY_SECTION_MARKERS = (
    "it is suggested that the accompanying explanatory notes be read before this statement is completed",
    "itis suggested that the accompanying explanatory notes be read before this statement is completed",
    "lt is suggested that the accompanying explanatory notes be read before this statement is completed",
    "the information which you are required to provide is contained in resolutions agreed to by the house",
    "if there is insufficient space on this form for the information you are required to provide",
    "received from other than official sources. gifts received by a member",
    "need not be registered unless the member judges",
    "appearance of conflict of interest may be seen to exist",
)

SHORT_HEADING_PREFIXES = (
    "directorships of companies",
    "family and business trusts and nominee companies",
    "gifts",
    "income",
    "investments",
    "liabilities",
    "memberships",
    "other assets",
    "other interests",
    "partnerships",
    "real estate",
    "saving or investment accounts",
    "shareholdings",
    "travel or hospitality",
)

STATE_ABBREVIATIONS = {
    "australian capital territory": "act",
    "new south wales": "nsw",
    "northern territory": "nt",
    "queensland": "qld",
    "south australia": "sa",
    "tasmania": "tas",
    "victoria": "vic",
    "western australia": "wa",
}
STATE_ABBREVIATION_VALUES = set(STATE_ABBREVIATIONS.values())
MONTH_NAME_PATTERN = (
    "january|february|march|april|may|june|july|august|september|october|"
    "november|december"
)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def latest_house_sections_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path:
    source_dir = processed_dir / "house_interest_sections"
    candidates = sorted(source_dir.glob("*.jsonl"), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No House interest section JSONL found under {source_dir}")
    return candidates[0]


def _clean_line(line: str) -> str:
    return " ".join(line.replace("\u2019", "'").split())


def _normal_value(value: str) -> str:
    lowered = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return " ".join(lowered.split())


def _normalized_non_values() -> set[str]:
    return {_normal_value(value) for value in NON_VALUES}


def _is_noise_line(line: str) -> bool:
    cleaned = _clean_line(line)
    lowered = cleaned.lower()
    normalized = _normal_value(cleaned)
    if not cleaned:
        return True
    if "\ufffd" in cleaned:
        return True
    if "(please print)" in lowered:
        return True
    if re.fullmatch(r"\d{1,3}", cleaned):
        return True
    if re.fullmatch(r"\d+", normalized):
        return True
    if normalized in {"australia", "australi"}:
        return True
    if normalized in {"a u", "db", "1 jk", "1 australia j", "grayndler nsw"}:
        return True
    tokens = normalized.split()
    if (
        tokens
        and tokens[-1] in STATE_ABBREVIATION_VALUES
        and "state" in tokens
        and len(tokens) <= 5
        and cleaned.upper() == cleaned
    ):
        return True
    if re.fullmatch(r"(?:\d{1,2})?(?:st|nd|rd|th)?\s*parliament", normalized):
        return True
    if normalized in {_normal_value(value) for value in HEADER_LINES}:
        return True
    if normalized in _normalized_non_values():
        return True
    value_probe = lowered.strip(" -–—")
    money_value_pattern = r"\$?\d[\d,]*(?:\.\d{1,2})?"
    if re.fullmatch(rf"(?:valued at|value|at)\s+{money_value_pattern}", value_probe):
        return True
    if re.fullmatch(
        rf"(?:\d{{4}}|[a-z]+\s+\d{{4}})\s+[-–]\s+valued at\s+{money_value_pattern}",
        value_probe,
    ):
        return True
    if re.fullmatch(rf"(?:{MONTH_NAME_PATTERN})\s+(?:19|20)\d{{2}}", normalized):
        return True
    if normalized == "self entries":
        return True
    if re.match(r"^\([ivx]+\)\s+", lowered):
        return True
    if any(normalized.startswith(_normal_value(prefix)) for prefix in INSTRUCTION_LINE_PREFIXES):
        return True
    if lowered in {"register of members' interests", "self", "spouse/", "partner", "dependent", "children"}:
        return True
    if lowered.startswith("page ") and lowered[5:].isdigit():
        return True
    return False


def _strip_section_heading(section_text: str) -> list[str]:
    lines = [_clean_line(line) for line in section_text.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    if not lines:
        return []
    first = re.sub(r"^\d{1,2}\.(?:\s*)", "", lines[0]).strip()
    normalized_first = _normal_value(first)
    for prefix in SHORT_HEADING_PREFIXES:
        normalized_prefix = _normal_value(prefix)
        if normalized_first == normalized_prefix:
            return lines[1:]
        if normalized_first.startswith(f"{normalized_prefix} "):
            remainder = first[len(prefix) :].strip(" -:;,")
            return [remainder, *lines[1:]] if remainder else lines[1:]
    return lines[1:]


def _consume_context_prefix(line: str, current_context: str) -> tuple[str, str, bool]:
    patterns = (
        (r"^Self\b\s*(?P<value>.*)$", "self"),
        (r"^Spouse(?:/)?\s*(?P<value>.*)$", "spouse_partner"),
        (r"^Partner\b\s*(?P<value>.*)$", "spouse_partner"),
        (r"^Dependent\b\s*(?P<value>.*)$", "dependent_children"),
        (r"^Children\b\s*(?P<value>.*)$", "dependent_children"),
    )
    for pattern, context in patterns:
        match = re.match(pattern, line, flags=re.IGNORECASE)
        if match:
            return context, match.group("value").strip(), True
    return current_context, line, False


def _line_has_context_prefix(line: str) -> bool:
    _, _, consumed = _consume_context_prefix(line, "member_unspecified")
    return consumed


def _looks_like_value(value: str) -> bool:
    normalized = _normal_value(value)
    return bool(normalized) and normalized not in _normalized_non_values()


def _section_metadata_noise_values(section: dict[str, Any]) -> set[str]:
    raw_values = [
        str(section.get("member_name") or ""),
        str(section.get("family_name") or ""),
        str(section.get("given_names") or ""),
        str(section.get("electorate") or ""),
        str(section.get("state") or ""),
    ]
    family_name = str(section.get("family_name") or "")
    given_names = str(section.get("given_names") or "")
    electorate = str(section.get("electorate") or "")
    state = str(section.get("state") or "")
    if family_name and given_names:
        raw_values.extend([f"{family_name} {given_names}", f"{given_names} {family_name}"])
    if electorate and state:
        state_variants = {state}
        state_abbreviation = STATE_ABBREVIATIONS.get(_normal_value(state))
        if state_abbreviation:
            state_variants.add(state_abbreviation)
        for state_variant in state_variants:
            raw_values.extend(
                [
                    f"{electorate} {state_variant}",
                    f"{electorate} state {state_variant}",
                    f"{electorate} i state {state_variant}",
                ]
            )
    return {normalized for value in raw_values if (normalized := _normal_value(value))}


def extracted_interest_fields(description: str) -> dict[str, Any]:
    provider = extract_provider(description)
    reported_value = extract_reported_value(description)
    event_date = extract_event_date(description)
    return {
        "counterparty_raw_name": provider["value"],
        "counterparty_extraction": provider,
        "estimated_value": reported_value["value"],
        "estimated_value_currency": reported_value["currency"],
        "estimated_value_extraction": reported_value,
        "event_date": event_date["value"],
        "event_date_extraction": event_date,
    }


def guess_counterparty(description: str) -> str:
    return str(extracted_interest_fields(description)["counterparty_raw_name"])


def _should_append_to_previous(previous: str, value: str) -> bool:
    previous_lower = previous.lower().strip()
    value_lower = value.lower().strip()
    if previous.count("(") > previous.count(")"):
        return True
    if previous_lower.endswith((" for", " from", " of", " by", " at", " valued at")):
        return True
    if value_lower.startswith(("(", "$")):
        return True
    if value_lower in {"membership", "pontiff"}:
        return True
    return False


def records_from_house_section(section: dict[str, Any]) -> list[dict[str, Any]]:
    section_number = str(section["section_number"])
    category = HOUSE_INTEREST_CATEGORIES.get(section_number)
    if category is None:
        return []
    normalized_section_text = _normal_value(section["section_text"])
    if any(_normal_value(marker) in normalized_section_text for marker in EXPLANATORY_SECTION_MARKERS):
        return []

    current_context = "member_unspecified"
    output: list[dict[str, Any]] = []
    section_digest = hashlib.sha1(section["section_text"].encode("utf-8")).hexdigest()[:12]
    lines = _strip_section_heading(section["section_text"])
    section_uses_owner_context = any(_line_has_context_prefix(line) for line in lines)
    metadata_noise_values = _section_metadata_noise_values(section)
    for line in lines:
        if _is_noise_line(line):
            continue
        if _normal_value(line) in STOP_MARKERS:
            break
        if any(_normal_value(line).startswith(_normal_value(marker)) for marker in STOP_MARKERS):
            break

        current_context, value, consumed_context = _consume_context_prefix(line, current_context)
        if section_uses_owner_context and current_context == "member_unspecified" and not consumed_context:
            continue
        if _normal_value(value) in metadata_noise_values:
            continue
        if not _looks_like_value(value) or _is_noise_line(value):
            continue

        if output and output[-1]["owner_context"] == current_context and _should_append_to_previous(
            output[-1]["description"], value
        ):
            output[-1]["description"] = f"{output[-1]['description']} {value}"
            output[-1].update(extracted_interest_fields(output[-1]["description"]))
            continue

        digest = hashlib.sha1(
            (
                f"{section['source_id']}:{section_number}:{section_digest}:"
                f"{current_context}:{len(output)}:{value}"
            ).encode("utf-8")
        ).hexdigest()[:12]
        extracted = extracted_interest_fields(value)
        output.append(
            {
                "external_key": f"aph_house_interests:{section['source_id']}:{section_number}:{digest}",
                "source_id": section["source_id"],
                "source_name": section["source_name"],
                "source_metadata_path": section["source_metadata_path"],
                "body_path": section["body_path"],
                "url": section["url"],
                "member_name": section["member_name"],
                "family_name": section["family_name"],
                "given_names": section["given_names"],
                "electorate": section["electorate"],
                "state": section["state"],
                "section_number": section_number,
                "section_title": section["section_title"],
                "interest_category": category,
                "owner_context": current_context,
                "description": value,
                **extracted,
                "original_section_text": section["section_text"],
            }
        )
    return output


def extract_house_interest_records(
    sections_path: Path | None = None,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    if sections_path is None:
        sections_path = latest_house_sections_jsonl(processed_dir=processed_dir)

    timestamp = _timestamp()
    target_dir = processed_dir / "house_interest_records"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    section_count = 0
    record_count = 0
    duplicate_external_key_count = 0
    seen_external_keys: set[str] = set()
    category_counts = {category: 0 for category in HOUSE_INTEREST_CATEGORIES.values()}
    with sections_path.open("r", encoding="utf-8") as source_handle, jsonl_path.open(
        "w", encoding="utf-8"
    ) as output_handle:
        for line in source_handle:
            section = json.loads(line)
            section_count += 1
            for record in records_from_house_section(section):
                if record["external_key"] in seen_external_keys:
                    duplicate_external_key_count += 1
                    continue
                seen_external_keys.add(record["external_key"])
                category_counts[record["interest_category"]] += 1
                record_count += 1
                output_handle.write(json.dumps(record, sort_keys=True) + "\n")

    summary = {
        "generated_at": timestamp,
        "source_sections_path": str(sections_path),
        "jsonl_path": str(jsonl_path),
        "section_count": section_count,
        "record_count": record_count,
        "unique_external_key_count": len(seen_external_keys),
        "duplicate_external_key_count": duplicate_external_key_count,
        "category_counts": category_counts,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
