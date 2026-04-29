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
    "paid for by",
    "facilitated by",
    "arranged by",
    "organised by",
    "organized by",
    "as guest of",
    "guest of",
    "at invitation of",
    "on invitation of",
    "invited by",
    "invitation from",
    "with support from",
    "with assistance from",
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
SUBJECT_PROVIDER_PATTERN = re.compile(
    r"\b(?P<name>[A-Z][A-Za-z0-9&'’.,() -]{2,120}?)\s+"
    r"(?P<verb>provided|supplied|hosted|sponsored|funded|paid\s+for|"
    r"donated|gifted|facilitated|arranged|organised|organized|invited)\b",
)
LEADING_PROVIDER_PATTERN = re.compile(
    r"^\s*(?P<name>[A-Z][A-Za-z0-9&'’.,() -]{2,90}?)"
    r"(?:\s+-\s+|,\s+(?:covering|including|for|with|providing)\b)",
)
BENEFIT_CONTEXT_PATTERN = re.compile(
    r"\b(ticket|tickets|pass|passes|hospitality|gift|gifts|travel|flight|flights|"
    r"lounge|membership|dinner|lunch|meal|accommodation|conference|function|"
    r"event|race|match|game|gala|reception)\b",
    flags=re.IGNORECASE,
)
LEADING_PROVIDER_ORG_PATTERN = re.compile(
    r"\b("
    r"aboriginal corporation|association|bank|club|college|company|corporation|"
    r"council|federation|foundation|guild|institute|limited|ltd|network|"
    r"organisation|organization|pty|society|trust|union|university|"
    r"australia|new zealand"
    r")\b",
    flags=re.IGNORECASE,
)
TRAVEL_ROUTE_PATTERN = re.compile(
    r"^[A-Z][A-Za-z'’ -]{2,60}\s+to\s+[A-Z][A-Za-z'’ -]{2,60}$"
)

BRANDED_PROVIDER_PATTERNS = (
    (
        "Qantas",
        "qantas",
        re.compile(r"\b(qantas|chairman'?s lounge|chairmans lounge|qantas club)\b", re.IGNORECASE),
    ),
    (
        "Virgin Australia",
        "virgin_australia",
        re.compile(
            r"\b(virgin australia|virgin beyond|beyond lounge|beyond club|"
            r"virgin club|virgin the club|virgin lounge|virgin velocity lounge|"
            r"velocity lounge|club lounge membership \(virgin\))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "Qatar Airways",
        "qatar_airways",
        re.compile(r"\bqatar airways\b", re.IGNORECASE),
    ),
    (
        "Emirates",
        "emirates",
        re.compile(r"\bemirates\b", re.IGNORECASE),
    ),
    (
        "Etihad Airways",
        "etihad_airways",
        re.compile(r"\betihad\b", re.IGNORECASE),
    ),
    (
        "Foxtel",
        "foxtel",
        re.compile(r"\bfoxtel\b", re.IGNORECASE),
    ),
)

VALUE_PATTERNS = (
    re.compile(
        r"\b(?P<context>valued\s+at|value(?:d)?|cost(?:ing)?|cost\s+of|estimated\s+value|"
        r"estimated\s+at|worth|approx(?:imately)?(?:\s+valued\s+at)?)\s*"
        r"(?P<currency>AUD|AUD\$|A\$|\$)?\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"\(\s*(?P<currency>AUD|AUD\$|A\$|\$)\s*(?P<amount>[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*\)",
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
TEXTUAL_DATE_RANGE_PATTERN = re.compile(
    rf"\b(?P<start_day>[0-3]?\d)(?:st|nd|rd|th)?\s*"
    rf"(?:-|–|to)\s*[0-3]?\d(?:st|nd|rd|th)?\s+"
    rf"(?P<month>{MONTH_PATTERN})\s+(?P<year>(?:19|20)\d{{2}})\b",
    flags=re.IGNORECASE,
)
MONTH_FIRST_DATE_PATTERN = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+"
    rf"(?P<day>[0-3]?\d)(?:st|nd|rd|th)?(?:,)?\s+"
    rf"(?P<year>(?:19|20)\d{{2}})\b",
    flags=re.IGNORECASE,
)


def _clean_text(value: str) -> str:
    return " ".join((value or "").replace("\u2019", "'").split())


def _clean_provider_name(name: str) -> str:
    name = _clean_text(name)
    name = re.sub(r"\s+-\s+.*$", "", name)
    name = re.sub(
        r"\s+(?:on|at|for|to attend|to assist|to support|to participate|to speak|"
        r"to my|to the|valued at|value|cost(?:ing)?|including|estimated at|"
        r"estimated value|worth|approx(?:imately)?)\b.*$",
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
    name = name.strip(" -,:;[]")
    if name.startswith("(") and name.endswith(")"):
        name = name[1:-1].strip()
    return name


def _looks_like_travel_class_change(value: str) -> bool:
    travel_class = r"(?:economy|premium economy|business|first|coach)"
    return bool(
        re.fullmatch(
            rf"{travel_class}(?:\s+class)?\s+to\s+{travel_class}(?:\s+class)?",
            _clean_text(value).lower(),
        )
    )


def _looks_like_travel_route(description: str, match: re.Match[str]) -> bool:
    if match.group("phrase").lower() != "from":
        return False
    start = max(0, match.start() - 24)
    end = min(len(description), match.end() + 24)
    window = description[start:end].lower()
    return bool(re.search(r"\b(flight|travel|trip|journey|airfare)\s+from\b", window)) and bool(
        re.search(r"\bto\b", window)
    )


def _generic_subject_provider(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    tokens = normalized.split()
    if any(token in {"am", "are", "is", "was", "were", "be", "been", "being"} for token in tokens):
        return True
    if tokens and tokens[0] in {
        "i",
        "we",
        "my",
        "our",
        "ticket",
        "tickets",
        "travel",
        "hospitality",
        "flight",
        "flights",
        "airfare",
        "airfares",
        "accommodation",
    }:
        return True
    return normalized in {
        "",
        "i",
        "i was",
        "me",
        "self",
        "the member",
        "member",
        "my office",
        "my office was",
        "parliament house",
        "tickets",
        "tickets were",
        "travel",
        "travel was",
        "hospitality",
        "hospitality was",
    }


def _looks_like_benefit_context(value: str) -> bool:
    return bool(BENEFIT_CONTEXT_PATTERN.search(value or ""))


def _looks_like_leading_provider(value: str) -> bool:
    cleaned = _clean_text(value)
    if TRAVEL_ROUTE_PATTERN.fullmatch(cleaned):
        return False
    return bool(LEADING_PROVIDER_ORG_PATTERN.search(cleaned))


def _leading_provider_payload(text: str, *, source_field: str) -> dict[str, Any] | None:
    if not _looks_like_benefit_context(text):
        return None
    match = LEADING_PROVIDER_PATTERN.search(text)
    if match is None:
        return None
    provider = _clean_provider_name(match.group("name"))
    if not provider or _generic_subject_provider(provider):
        return None
    if not _looks_like_leading_provider(provider):
        return None
    if provider.lower() in GENERIC_PROVIDER_VALUES:
        return None
    if len(provider) < 3 or provider.isdigit():
        return None
    return {
        "value": provider[:250],
        "source_field": source_field,
        "method": "leading_provider_benefit_phrase",
        "raw_span": match.group(0).strip(),
    }


def _explicit_provider_payload(
    match: re.Match[str],
    *,
    source_field: str,
    allow_from_phrase: bool = True,
) -> dict[str, Any] | None:
    phrase = match.group("phrase").lower()
    if phrase == "from" and not allow_from_phrase:
        return None
    provider = _clean_provider_name(match.group("name"))
    if not provider:
        return None
    if provider.lower() in GENERIC_PROVIDER_VALUES:
        return None
    if len(provider) < 3 or provider.isdigit():
        return None
    if phrase == "from" and _looks_like_travel_class_change(provider):
        return None
    return {
        "value": provider[:250],
        "source_field": source_field,
        "method": f"explicit_provider_phrase:{phrase}",
        "raw_span": match.group(0).strip(),
    }


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
                for route_tail_match in PROVIDER_PATTERN.finditer(match.group("name")):
                    payload = _explicit_provider_payload(
                        route_tail_match,
                        source_field=field_name,
                        allow_from_phrase=False,
                    )
                    if payload:
                        return payload
                continue
            payload = _explicit_provider_payload(match, source_field=field_name)
            if payload:
                return payload
    for field_name, text in texts:
        for match in SUBJECT_PROVIDER_PATTERN.finditer(text):
            provider = _clean_provider_name(match.group("name"))
            if not provider or _generic_subject_provider(provider):
                continue
            if provider.lower() in GENERIC_PROVIDER_VALUES:
                continue
            if len(provider) < 3 or provider.isdigit():
                continue
            return {
                "value": provider[:250],
                "source_field": field_name,
                "method": f"subject_provider_verb:{match.group('verb').lower()}",
                "raw_span": match.group(0).strip(),
            }
    for field_name, text in texts:
        payload = _leading_provider_payload(text, source_field=field_name)
        if payload:
            return payload
    for field_name, text in texts:
        for provider, method_suffix, pattern in BRANDED_PROVIDER_PATTERNS:
            match = pattern.search(text)
            if match:
                return {
                    "value": provider,
                    "source_field": field_name,
                    "method": f"known_brand_provider:{method_suffix}",
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

    match = TEXTUAL_DATE_RANGE_PATTERN.search(text)
    if match:
        try:
            parsed = date(
                int(match.group("year")),
                MONTHS[match.group("month").lower()],
                int(match.group("start_day")),
            )
        except ValueError:
            parsed = None
        if parsed is not None:
            return _date_payload(
                parsed,
                "explicit_textual_event_date_range_start",
                match.group(0),
            )

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

    match = MONTH_FIRST_DATE_PATTERN.search(text)
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
            return _date_payload(parsed, "explicit_month_first_event_date", match.group(0))

    return {"value": "", "method": "", "raw_span": ""}


def parse_iso_datetime_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""
