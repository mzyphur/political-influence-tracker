from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


PROVIDER_PHRASES = (
    "provided by",
    "supplied by",
    "hosted by",
    "courtesy of",
    "donated by",
    "gifted by",
    "sponsored by",
    "funded by",
    "paid by",
    "as guest of",
    "guest of",
    "invited by",
    "invitation from",
    "from",
    "by organisers",
    "by organizers",
)

GENERIC_PROVIDER_VALUES = {
    "organisers",
    "organizers",
    "the organisers",
    "the organizers",
    "conference organisers",
    "conference organizers",
    "official sources",
    "unknown",
}

MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_PATTERN = "|".join(MONTHS)

PROVIDER_PATTERN = re.compile(
    r"\b(?P<phrase>"
    + "|".join(re.escape(phrase) for phrase in PROVIDER_PHRASES)
    + r")\s+(?P<name>[^.;\n]+)",
    flags=re.IGNORECASE,
)

VALUE_PATTERNS = (
    re.compile(
        r"\b(?P<context>valued\s+at|value(?:d)?|cost(?:ing)?|cost\s+of|estimated\s+value)\s*"
        r"(?P<currency>AUD|A\$|\$)?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\(\s*(?P<currency>AUD|A\$|\$)\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*\)",
        flags=re.IGNORECASE,
    ),
)

NUMERIC_DATE_PATTERN = re.compile(
    r"\b(?P<day>[0-3]?\d)[/.](?P<month>[01]?\d)[/.](?P<year>\d{2,4})\b"
)
TEXTUAL_DATE_PATTERN = re.compile(
    rf"\b(?P<day>[0-3]?\d)(?:st|nd|rd|th)?\s+"
    rf"(?P<month>{MONTH_PATTERN})\s+(?P<year>(?:19|20)\d{{2}})\b",
    flags=re.IGNORECASE,
)


def _clean_text(value: str) -> str:
    return " ".join((value or "").replace("\u2019", "'").split())


def _clean_provider_name(name: str) -> str:
    name = _clean_text(name)
    name = re.sub(r"\s+-\s+.*$", "", name)
    name = re.sub(
        r"\s+(?:on|at|for|to attend|to the|valued at|value|cost(?:ing)?|including)\b.*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    name = re.sub(r"\s+\(?\d{1,2}[/.]\d{1,2}[/.]\d{2,4}\)?.*$", "", name)
    name = re.sub(
        rf"\s+\(?\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTH_PATTERN})\s+(?:19|20)\d{{2}}\)?.*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return name.strip(" -,:;()[]")


def _looks_like_travel_route(description: str, match: re.Match[str]) -> bool:
    if match.group("phrase").lower() != "from":
        return False
    start = max(0, match.start() - 24)
    end = min(len(description), match.end() + 24)
    window = description[start:end].lower()
    return bool(re.search(r"\b(flight|travel|trip|journey|airfare)\s+from\b", window)) and bool(
        re.search(r"\bto\b", window)
    )


def extract_provider(description: str, *, fields: dict[str, Any] | None = None) -> dict[str, Any]:
    texts: list[tuple[str, str]] = []
    if fields:
        for field_name, value in fields.items():
            if value not in ("", None):
                texts.append((field_name, str(value)))
    texts.append(("description", description or ""))

    for field_name, text in texts:
        for match in PROVIDER_PATTERN.finditer(text):
            if _looks_like_travel_route(text, match):
                continue
            provider = _clean_provider_name(match.group("name"))
            if not provider:
                continue
            if provider.lower() in GENERIC_PROVIDER_VALUES:
                continue
            if len(provider) < 3 or provider.isdigit():
                continue
            return {
                "value": provider[:250],
                "source_field": field_name,
                "method": f"explicit_provider_phrase:{match.group('phrase').lower()}",
                "raw_span": match.group(0).strip(),
            }
    return {"value": "", "source_field": "", "method": "", "raw_span": ""}


def extract_reported_value(description: str) -> dict[str, Any]:
    for pattern in VALUE_PATTERNS:
        match = pattern.search(description or "")
        if not match:
            continue
        raw_amount = match.group("amount").replace(",", "")
        try:
            amount = Decimal(raw_amount)
        except InvalidOperation:
            continue
        return {
            "value": str(amount),
            "currency": "AUD",
            "method": "explicit_reported_value",
            "raw_span": match.group(0).strip(),
        }
    return {"value": "", "currency": "", "method": "", "raw_span": ""}


def _normalize_year(value: str) -> int:
    year = int(value)
    if year < 100:
        return 2000 + year
    return year


def _date_payload(parsed: date, method: str, raw_span: str) -> dict[str, Any]:
    if parsed.year < 2000 or parsed.year > 2100:
        return {"value": "", "method": "", "raw_span": ""}
    return {"value": parsed.isoformat(), "method": method, "raw_span": raw_span.strip()}


def extract_event_date(description: str) -> dict[str, Any]:
    text = description or ""
    match = NUMERIC_DATE_PATTERN.search(text)
    if match:
        try:
            parsed = date(
                _normalize_year(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            parsed = None
        if parsed is not None:
            return _date_payload(parsed, "explicit_numeric_event_date", match.group(0))

    match = TEXTUAL_DATE_PATTERN.search(text)
    if match:
        try:
            parsed = date(
                int(match.group("year")),
                MONTHS[match.group("month").lower()],
                int(match.group("day")),
            )
        except ValueError:
            parsed = None
        if parsed is not None:
            return _date_payload(parsed, "explicit_textual_event_date", match.group(0))

    return {"value": "", "method": "", "raw_span": ""}


def parse_iso_datetime_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""
