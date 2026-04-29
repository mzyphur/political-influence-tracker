from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from au_politics_money.config import PROCESSED_DIR, PROJECT_ROOT
from au_politics_money.ingest.aec_boundaries import (
    BOUNDARY_SET,
    PARSER_NAME as BOUNDARY_PARSER_NAME,
    PARSER_VERSION as BOUNDARY_PARSER_VERSION,
    latest_aec_boundaries_geojson,
)
from au_politics_money.ingest.aec_electorate_finder import (
    latest_aec_electorate_finder_postcodes_jsonl,
)
from au_politics_money.ingest.aph_decision_records import (
    latest_aph_decision_record_index_jsonl_paths,
    latest_aph_decision_record_documents_summary,
)
from au_politics_money.ingest.aph_official_divisions import latest_official_aph_divisions_jsonl
from au_politics_money.ingest.entity_classification import (
    CLASSIFIER_NAME,
    PUBLIC_INTEREST_SECTORS,
    latest_entity_classifications_jsonl,
)
from au_politics_money.ingest.land_mask import (
    AIMS_COASTLINE_PARSER_NAME,
    AIMS_COASTLINE_PARSER_VERSION,
    AIMS_COASTLINE_LIMITATIONS,
    AIMS_COASTLINE_SOURCE_ID,
    PARSER_NAME as LAND_MASK_PARSER_NAME,
    PARSER_VERSION as LAND_MASK_PARSER_VERSION,
    extract_aims_australian_coastline_land_mask,
    extract_natural_earth_country_land_mask,
    extract_natural_earth_physical_land_mask,
    latest_aims_australian_coastline_land_mask_geojson,
    latest_country_land_mask_geojson,
    latest_physical_land_mask_geojson,
)
from au_politics_money.ingest.official_identifiers import (
    ANZSIC_SECTIONS,
    OFFICIAL_IDENTIFIER_PARSER_NAME,
    latest_official_identifier_jsonl_paths,
)
from au_politics_money.ingest.qld_ecq_eds import (
    CONTEXT_PARSER_NAME as QLD_ECQ_CONTEXT_PARSER_NAME,
    QLD_ECQ_EDS_CONTEXT_LOOKUPS,
    PARTICIPANT_PARSER_NAME as QLD_ECQ_PARTICIPANT_PARSER_NAME,
    QLD_ECQ_EDS_PARTICIPANT_LOOKUPS,
)
from au_politics_money.ingest.they_vote_for_you import latest_they_vote_for_you_divisions_jsonl

STATE_CODES = {
    "Australian Capital Territory": "ACT",
    "ACT": "ACT",
    "New South Wales": "NSW",
    "NSW": "NSW",
    "Northern Territory": "NT",
    "NT": "NT",
    "Queensland": "QLD",
    "QLD": "QLD",
    "South Australia": "SA",
    "SA": "SA",
    "Tasmania": "TAS",
    "TAS": "TAS",
    "Victoria": "VIC",
    "VIC": "VIC",
    "Western Australia": "WA",
    "WA": "WA",
}

INFLUENCE_EVENT_LOADER_NAME = "load_influence_events_v1"
DISPLAY_GEOMETRY_REPAIR_PROJECTION_SRID = 3577
MAX_COASTLINE_REPAIR_BUFFER_METERS = 10_000
DEFAULT_COASTLINE_REPAIR_BUFFER_METERS = 100
CAMPAIGN_SUPPORT_FLOW_KINDS = {
    "election_candidate_or_senate_group_campaign_expenditure",
    "election_candidate_or_senate_group_discretionary_benefit",
    "election_candidate_or_senate_group_donation_received",
    "election_candidate_or_senate_group_return_summary",
    "election_media_advertising_expenditure",
    "election_public_funding_paid",
    "election_third_party_campaign_expenditure",
    "qld_electoral_expenditure",
}
QLD_ECQ_AUTO_ACCEPT_PARTICIPANT_ENTITY_TYPES = {
    "associated_entity",
    "local_group",
    "political_party",
}
QLD_ECQ_OFFICIAL_PARTICIPANT_ENTITY_TYPES = {
    "associated_entity",
    "candidate_or_elector",
    "local_group",
    "political_party",
}

REPRESENTATIVE_RETURN_TITLE_TOKENS = {
    "dr",
    "hon",
    "mr",
    "mrs",
    "ms",
    "sen",
    "senator",
    "the",
}

REPRESENTATIVE_RETURN_POSTNOMINAL_TOKENS = {
    "ac",
    "afsm",
    "am",
    "ao",
    "apm",
    "csc",
    "dsc",
    "dsm",
    "kc",
    "mg",
    "mp",
    "oam",
    "psm",
    "qc",
    "sc",
    "vc",
}

PRIVATE_INTEREST_EVENT_TYPES = {
    "Shareholdings": "shareholding",
    "Family and business trusts and nominee companies": "trust_or_nominee_company",
    "Trusts": "trust_or_nominee_company",
    "Real estate": "real_estate",
    "Directorships of companies": "company_directorship",
    "Registered directorships of companies": "company_directorship",
    "Partnerships": "partnership",
    "Liabilities": "liability",
    "Investments": "investment",
    "Savings or investment accounts": "savings_or_investment_account",
    "Other assets": "other_asset",
    "Other income": "other_income",
}

ORG_ROLE_EVENT_TYPES = {
    "Memberships with possible conflicts": "membership",
    "Organisations to which office-holder donations are made": "office_holder_or_donation",
}

BENEFIT_KEYWORD_EVENT_TYPES = (
    (
        "private_aircraft_or_flight",
        (
            "airfare",
            "airline",
            "air travel",
            "airport parking",
            "business class",
            "charter flight",
            "chartered aircraft",
            "chartered flight",
            "flight",
            "flights",
            "helicopter",
            "jet",
            "private aircraft",
            "private jet",
            "qatar airways",
            "return travel",
            "upgrade",
        ),
    ),
    (
        "accommodation_or_travel_hospitality",
        (
            "accommodation",
            "hotel",
        ),
    ),
    (
        "meal_or_reception",
        (
            "breakfast",
            "dinner",
            "drinks",
            "lunch",
            "reception",
        ),
    ),
    (
        "event_ticket_or_pass",
        (
            "concert",
            "afl",
            "australian open",
            "basketball",
            "cinema",
            "cricket",
            "football",
            "festival",
            "gala",
            "grand final",
            "movie",
            "netball",
            "nrl",
            "opera",
            "race day",
            "rugby",
            "soccer",
            "sport",
            "theatre",
            "ticket",
            "tickets",
        ),
    ),
    (
        "membership_or_lounge_access",
        (
            "chairman",
            "chairman's",
            "chairmans",
            "club",
            "lounge",
            "member",
            "membership",
            "pass",
            "virgin beyond",
        ),
    ),
    (
        "subscription_or_service",
        (
            "foxtel",
            "service",
            "subscription",
            "television",
        ),
    ),
)


def normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def normalize_representative_return_name(value: str) -> str:
    tokens = normalize_name(value).split()
    while tokens and tokens[0] in REPRESENTATIVE_RETURN_TITLE_TOKENS:
        tokens.pop(0)
    while tokens and tokens[-1] in REPRESENTATIVE_RETURN_POSTNOMINAL_TOKENS:
        tokens.pop()
    return " ".join(tokens)


def is_direct_representative_return_type(value: str) -> bool:
    normalized = normalize_name(value)
    return normalized in {
        "member of hor return",
        "member of house of representatives return",
        "member of parliament return",
        "senate return",
        "senator return",
    }


def parse_date(value: str) -> date | None:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    for fmt in (
        "%d/%m/%Y",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%m/%d/%Y %I:%M:%S %p",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def parse_financial_year_bounds(value: str) -> tuple[date, date] | None:
    match = re.match(r"^\s*(\d{4})\s*[-/]\s*(\d{2}|\d{4})\s*$", value or "")
    if not match:
        return None
    start_year = int(match.group(1))
    end_token = match.group(2)
    if len(end_token) == 2:
        end_year = (start_year // 100) * 100 + int(end_token)
        if end_year < start_year:
            end_year += 100
    else:
        end_year = int(end_token)
    if end_year < start_year:
        return None
    return date(start_year, 7, 1), date(end_year, 6, 30)


def parse_aec_money_flow_date(
    value: str,
    financial_year: str,
) -> tuple[date | None, dict[str, str]]:
    cleaned = (value or "").strip()
    validation = {
        "raw_date": cleaned,
        "financial_year": financial_year or "",
        "status": "not_disclosed" if not cleaned else "unparseable",
    }
    parsed = parse_date(cleaned)
    if parsed is None:
        return None, validation

    validation["parsed_date"] = parsed.isoformat()
    bounds = parse_financial_year_bounds(financial_year or "")
    if bounds is None:
        validation["status"] = "accepted_without_financial_year_bounds"
        return parsed, validation

    start_date, end_date = bounds
    validation["expected_start"] = start_date.isoformat()
    validation["expected_end"] = end_date.isoformat()
    if not start_date <= parsed <= end_date:
        validation["status"] = "outside_financial_year"
        return None, validation

    validation["status"] = "accepted"
    return parsed, validation


def parse_decimal(value: str) -> Decimal | None:
    cleaned = (value or "").replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def parse_datetime(value: str) -> datetime | None:
    cleaned = (value or "").strip()
    if not cleaned or cleaned.startswith("0001-"):
        return None
    for fmt in ("%Y%m%dT%H%M%SZ", "%Y%m%dT%H%M%S%z"):
        try:
            parsed = datetime.strptime(cleaned, fmt)
            return (
                parsed.replace(tzinfo=timezone.utc)
                if parsed.tzinfo is None
                else parsed.astimezone(timezone.utc)
            )
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError:
        parsed_date = parse_date(cleaned)
        if parsed_date is None:
            return None
        return datetime.combine(parsed_date, datetime.min.time(), tzinfo=timezone.utc)


def senate_api_name_to_canonical(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if "," not in cleaned:
        return cleaned
    surname, given_names = [part.strip() for part in cleaned.split(",", maxsplit=1)]
    return " ".join(part for part in [given_names, surname] if part)


def aec_candidate_name_to_canonical(value: str) -> str:
    return senate_api_name_to_canonical(value)


def normalize_electorate_name(value: str) -> str:
    normalized = normalize_name(value)
    return re.sub(r"\bold$", "", normalized).strip()


def state_code(value: str) -> str:
    cleaned = " ".join((value or "").split())
    return STATE_CODES.get(cleaned, cleaned)


def slugify(value: str, default: str) -> str:
    slug = normalize_name(value).replace(" ", "_")
    return slug or default


def classify_money_event_type(disclosure_category: str, receipt_type: str) -> str:
    category = normalize_name(disclosure_category)
    receipt = normalize_name(receipt_type)
    combined = f"{category} {receipt}".strip()
    if "discretionary benefit" in combined:
        return "discretionary_benefit"
    if "advertis" in combined or "broadcast" in combined or "campaign material" in combined:
        return "campaign_expenditure"
    if "gift" in combined or "donation" in combined:
        return "donation_or_gift"
    if "receipt" in combined:
        return "receipt"
    if "debt" in combined:
        return "debt"
    if "loan" in combined:
        return "loan"
    return slugify(disclosure_category or receipt_type, "money_flow")


def is_campaign_support_money_flow(metadata: dict[str, Any]) -> bool:
    return (
        metadata.get("source_dataset") in {"aec_election", "aec_public_funding", "qld_ecq_eds"}
        and metadata.get("flow_kind") in CAMPAIGN_SUPPORT_FLOW_KINDS
    )


def campaign_support_event_type(metadata: dict[str, Any], fallback_event_type: str) -> str:
    flow_kind = metadata.get("flow_kind")
    if flow_kind == "election_candidate_or_senate_group_donation_received":
        return "candidate_or_senate_group_donation"
    if flow_kind == "election_candidate_or_senate_group_discretionary_benefit":
        return "candidate_or_senate_group_discretionary_benefit"
    if flow_kind == "election_candidate_or_senate_group_campaign_expenditure":
        return "candidate_or_senate_group_campaign_expenditure"
    if flow_kind == "election_candidate_or_senate_group_return_summary":
        context = metadata.get("candidate_context") if isinstance(metadata.get("candidate_context"), dict) else {}
        if context.get("is_nil_return"):
            return "candidate_or_senate_group_nil_return"
        return "candidate_or_senate_group_return_summary"
    if flow_kind == "election_media_advertising_expenditure":
        return "observed_media_ad_activity"
    if flow_kind == "election_public_funding_paid":
        return "election_public_funding_paid"
    if flow_kind == "election_third_party_campaign_expenditure":
        return "third_party_campaign_expenditure"
    if flow_kind == "qld_electoral_expenditure":
        return "state_local_electoral_expenditure"
    return fallback_event_type


def campaign_support_attribution(metadata: dict[str, Any]) -> dict[str, Any]:
    attribution = metadata.get("campaign_support_attribution")
    if isinstance(attribution, dict):
        return attribution
    return {
        "tier": metadata.get("attribution_tier") or "source_backed_campaign_support_record",
        "not_personal_receipt": True,
        "notes": [
            "AEC election disclosure row connected to campaign support; not treated as money personally received by a representative."
        ],
    }


def benefit_subtype(description: str) -> str | None:
    lowered = description.lower()
    for subtype, keywords in BENEFIT_KEYWORD_EVENT_TYPES:
        if any(keyword in lowered for keyword in keywords):
            return subtype
    return None


def is_airline_lounge_benefit(description: str) -> bool:
    lowered = description.lower()
    return any(
        keyword in lowered
        for keyword in (
            "beyond lounge",
            "chairman",
            "chairman's",
            "chairmans",
            "lounge",
            "qantas club",
            "virgin beyond",
        )
    )


def classify_interest_event(interest_category: str, description: str) -> tuple[str, str, str | None]:
    category = interest_category.strip()
    subtype = benefit_subtype(description)

    if category in PRIVATE_INTEREST_EVENT_TYPES:
        return "private_interest", PRIVATE_INTEREST_EVENT_TYPES[category], None

    if category in ORG_ROLE_EVENT_TYPES:
        return "organisational_role", ORG_ROLE_EVENT_TYPES[category], None

    if category == "Sponsored travel or hospitality":
        return "benefit", "sponsored_travel_or_hospitality", subtype

    if category == "Gifts":
        return "benefit", "gift", subtype

    if category == "Other interests":
        if subtype == "membership_or_lounge_access" and not is_airline_lounge_benefit(description):
            return "organisational_role", "membership", None
        if subtype:
            return "benefit", "other_declared_benefit", subtype
        return "other", "other_declared_interest", None

    return "other", slugify(category, "declared_interest"), None


def missing_money_flags(
    *,
    source_raw_name: str,
    recipient_raw_name: str,
    amount: Decimal | None,
    date_received: date | None,
) -> list[str]:
    flags = []
    if not normalize_name(source_raw_name) or normalize_name(source_raw_name) == "unknown":
        flags.append("source_not_disclosed")
    if not normalize_name(recipient_raw_name) or normalize_name(recipient_raw_name) == "unknown":
        flags.append("recipient_not_disclosed")
    if amount is None:
        flags.append("amount_not_disclosed")
    if date_received is None:
        flags.append("event_date_not_disclosed")
    return flags


def missing_interest_flags(
    *,
    source_raw_name: str,
    amount: Decimal | None,
    date_received: date | None,
    date_reported: date | None,
    extraction_method: str,
) -> list[str]:
    flags = []
    if not normalize_name(source_raw_name):
        flags.append("provider_not_disclosed_or_not_extracted")
    if amount is None:
        flags.append("value_not_disclosed")
    if date_received is None:
        flags.append("event_date_not_disclosed")
    if date_reported is None:
        flags.append("reported_date_not_disclosed")
    if "heuristic" in extraction_method:
        flags.append("parsed_from_pdf_heuristic")
    return flags


def latest_file(directory: Path, pattern: str) -> Path:
    candidates = sorted(directory.glob(pattern), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No files matching {pattern!r} in {directory}")
    return candidates[0]


def connect(database_url: str | None = None):
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only in incomplete envs.
        raise RuntimeError("Install database dependencies with `pip install -e '.[dev]'`.") from exc

    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL loading.")
    return psycopg.connect(url)


def as_jsonb(value: Any):
    try:
        from psycopg.types.json import Jsonb
    except ImportError as exc:  # pragma: no cover - exercised only in incomplete envs.
        raise RuntimeError("Install database dependencies with `pip install -e '.[dev]'`.") from exc
    return Jsonb(value)


def apply_schema(conn, schema_path: Path | None = None) -> None:
    path = schema_path or PROJECT_ROOT / "backend" / "schema" / "001_initial.sql"
    with conn.cursor() as cur:
        cur.execute(path.read_text(encoding="utf-8"))
    conn.commit()


def apply_migrations(conn, schema_dir: Path | None = None) -> dict[str, int]:
    directory = schema_dir or PROJECT_ROOT / "backend" / "schema"
    migration_paths = sorted(path for path in directory.glob("*.sql") if path.name != "001_initial.sql")
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        cur.execute("SELECT to_regclass('source_document')")
        if cur.fetchone()[0] is None:
            raise RuntimeError(
                "Cannot apply incremental migrations before the baseline schema exists. "
                "Run `load-postgres --apply-schema` first for a fresh database."
            )
        applied = {
            row[0]
            for row in cur.execute("SELECT filename FROM schema_migrations").fetchall()
        }
        for path in migration_paths:
            if path.name in applied:
                continue
            cur.execute(path.read_text(encoding="utf-8"))
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
    conn.commit()
    return {"migrations_applied": len(migration_paths) - len(applied & {p.name for p in migration_paths})}


def upsert_source_document(conn, metadata_path: Path) -> int:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    source = metadata["source"]
    fetched_at_raw = metadata["fetched_at"]
    fetched_at = datetime.strptime(fetched_at_raw, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_document (
                source_id, source_name, source_type, jurisdiction, url, final_url,
                fetched_at, http_status, content_type, sha256, storage_path, metadata
            )
            VALUES (
                %(source_id)s, %(source_name)s, %(source_type)s, %(jurisdiction)s,
                %(url)s, %(final_url)s, %(fetched_at)s, %(http_status)s,
                %(content_type)s, %(sha256)s, %(storage_path)s, %(metadata)s
            )
            ON CONFLICT (source_id, sha256) DO UPDATE SET
                final_url = EXCLUDED.final_url,
                fetched_at = GREATEST(source_document.fetched_at, EXCLUDED.fetched_at),
                http_status = EXCLUDED.http_status,
                content_type = EXCLUDED.content_type,
                storage_path = EXCLUDED.storage_path,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            {
                "source_id": source["source_id"],
                "source_name": source["name"],
                "source_type": source["source_type"],
                "jurisdiction": source["jurisdiction"],
                "url": source["url"],
                "final_url": metadata.get("final_url"),
                "fetched_at": fetched_at,
                "http_status": metadata.get("http_status"),
                "content_type": metadata.get("content_type"),
                "sha256": metadata["sha256"],
                "storage_path": metadata["body_path"],
                "metadata": as_jsonb(metadata),
            },
        )
        row = cur.fetchone()
    return int(row[0])


def get_or_create_jurisdiction(conn, name: str, level: str, code: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM jurisdiction
            WHERE name = %s
               OR code = %s
            ORDER BY CASE WHEN code = %s THEN 0 ELSE 1 END, id
            LIMIT 1
            """,
            (name, code, code),
        )
        row = cur.fetchone()
        if row is not None:
            cur.execute(
                """
                UPDATE jurisdiction
                SET level = %s,
                    code = COALESCE(code, %s)
                WHERE id = %s
                RETURNING id
                """,
                (level, code, row[0]),
            )
            return int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO jurisdiction (name, level, code)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (name, level, code),
        )
        row = cur.fetchone()
    return int(row[0])


def get_or_create_party(conn, name: str, jurisdiction_id: int) -> int | None:
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO party (name, short_name, jurisdiction_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (name, jurisdiction_id) DO UPDATE SET short_name = EXCLUDED.short_name
            RETURNING id
            """,
            (name, name, jurisdiction_id),
        )
        row = cur.fetchone()
    return int(row[0])


def get_or_create_electorate(conn, name: str, chamber: str, state: str, jurisdiction_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO electorate (name, jurisdiction_id, chamber, state_or_territory)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (name, jurisdiction_id, chamber) DO UPDATE SET
                state_or_territory = EXCLUDED.state_or_territory
            RETURNING id
            """,
            (name, jurisdiction_id, chamber, state),
        )
        row = cur.fetchone()
    return int(row[0])


def get_or_create_boundary_electorate(
    conn,
    *,
    name: str,
    jurisdiction_id: int,
    source_document_id: int,
) -> int:
    normalized = normalize_electorate_name(name)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT electorate.id, electorate.name, count(office_term.id) AS office_count
            FROM electorate
            LEFT JOIN office_term
              ON office_term.electorate_id = electorate.id
             AND office_term.chamber = 'house'
             AND office_term.term_end IS NULL
            WHERE electorate.jurisdiction_id = %s
              AND electorate.chamber = 'house'
            GROUP BY electorate.id, electorate.name
            ORDER BY office_count DESC, electorate.id
            """,
            (jurisdiction_id,),
        )
        for electorate_id, electorate_name, _office_count in cur.fetchall():
            if normalize_electorate_name(electorate_name) != normalized:
                continue
            cur.execute(
                """
                UPDATE electorate
                SET source_document_id = COALESCE(electorate.source_document_id, %s),
                    metadata = electorate.metadata || %s
                WHERE id = %s
                """,
                (
                    source_document_id,
                    as_jsonb(
                        {
                            "boundary_source": BOUNDARY_SET,
                            "boundary_loader": "aec_federal_boundaries_postgis_v1",
                        }
                    ),
                    electorate_id,
                ),
            )
            return int(electorate_id)

        cur.execute(
            """
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, source_document_id, metadata
            )
            VALUES (%s, %s, 'house', %s, %s)
            ON CONFLICT (name, jurisdiction_id, chamber) DO UPDATE SET
                source_document_id = COALESCE(electorate.source_document_id, EXCLUDED.source_document_id),
                metadata = electorate.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                name,
                jurisdiction_id,
                source_document_id,
                as_jsonb(
                    {
                        "boundary_source": BOUNDARY_SET,
                        "boundary_loader": "aec_federal_boundaries_postgis_v1",
                    }
                ),
            ),
        )
        row = cur.fetchone()
    return int(row[0])


def get_or_create_entity(conn, raw_name: str, entity_type: str = "unknown") -> int:
    canonical_name = raw_name.strip() or "Unknown"
    normalized_name = normalize_name(canonical_name) or "unknown"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM entity
            WHERE normalized_name = %s
            ORDER BY
                CASE
                    WHEN entity_type = %s THEN 0
                    WHEN entity_type = 'unknown' THEN 1
                    ELSE 2
                END,
                id
            LIMIT 1
            """,
            (normalized_name, entity_type),
        )
        existing = cur.fetchone()
        if existing is not None:
            entity_id = int(existing[0])
            cur.execute(
                """
                UPDATE entity
                SET canonical_name = %s
                WHERE id = %s AND entity_type = 'unknown'
                """,
                (canonical_name, entity_id),
            )
            return entity_id

        cur.execute(
            """
            INSERT INTO entity (canonical_name, normalized_name, entity_type)
            VALUES (%s, %s, %s)
            ON CONFLICT (normalized_name, entity_type) DO UPDATE SET
                canonical_name = EXCLUDED.canonical_name
            RETURNING id
            """,
            (canonical_name, normalized_name, entity_type),
        )
        row = cur.fetchone()
    return int(row[0])


def _find_house_electorate_id(
    conn,
    *,
    electorate_name: str,
    state_or_territory: str | None = None,
) -> int | None:
    normalized = normalize_electorate_name(electorate_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT electorate.id, electorate.name, electorate.state_or_territory
            FROM electorate
            JOIN jurisdiction ON jurisdiction.id = electorate.jurisdiction_id
            WHERE jurisdiction.level = 'federal'
              AND (
                    jurisdiction.code IN ('CWLTH', 'Cth', 'AU')
                 OR jurisdiction.name ILIKE 'Commonwealth%'
              )
              AND electorate.chamber = 'house'
            ORDER BY electorate.id
            """
        )
        for electorate_id, name, state in cur.fetchall():
            if normalize_electorate_name(name) != normalized:
                continue
            if state_or_territory and state and state != state_or_territory:
                continue
            return int(electorate_id)
    return None


def _resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _postcode_artifact_postcodes(path: Path, records: list[dict[str, Any]]) -> set[str]:
    summary_path = path.with_name(f"{path.stem}.summary.json")
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            summary = {}
        postcodes = {
            str(postcode)
            for postcode in summary.get("postcodes_requested", [])
            if str(postcode)
        }
        if postcodes:
            return postcodes
        postcodes = {
            str(item.get("postcode"))
            for item in summary.get("postcodes", [])
            if isinstance(item, dict) and item.get("postcode")
        }
        if postcodes:
            return postcodes
    return {str(record.get("postcode")) for record in records if record.get("postcode")}


def _postcode_record_metadata(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_dataset": record.get("source_dataset"),
        "normalizer_name": record.get("normalizer_name"),
        "normalizer_version": record.get("normalizer_version"),
        "caveat": record.get("caveat"),
        "ambiguity": record.get("ambiguity"),
        "source_boundary_context": record.get("source_boundary_context"),
        "current_member_context": record.get("current_member_context"),
        "aec_boundary_note": record.get("aec_boundary_note"),
        "original_rows": record.get("original_rows", []),
    }


def _postcode_source_document_id(
    conn,
    record: dict[str, Any],
    source_doc_cache: dict[str, int],
) -> int | None:
    metadata_path = str(record.get("source_metadata_path") or "")
    if not metadata_path:
        return None
    if metadata_path not in source_doc_cache:
        source_doc_cache[metadata_path] = upsert_source_document(
            conn,
            _resolve_project_path(metadata_path),
        )
    return source_doc_cache[metadata_path]


def _insert_unresolved_postcode_candidate(
    conn,
    *,
    record: dict[str, Any],
    source_document_id: int | None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO postcode_electorate_crosswalk_unresolved (
                postcode, electorate_name, state_or_territory, match_method,
                confidence, locality_count, localities,
                redistributed_electorates, other_localities,
                aec_division_ids, source_document_id, source_updated_text,
                source_boundary_context, current_member_context, metadata
            )
            VALUES (
                %(postcode)s, %(electorate_name)s, %(state_or_territory)s,
                %(match_method)s, %(confidence)s, %(locality_count)s,
                %(localities)s, %(redistributed_electorates)s,
                %(other_localities)s, %(aec_division_ids)s,
                %(source_document_id)s, %(source_updated_text)s,
                %(source_boundary_context)s, %(current_member_context)s,
                %(metadata)s
            )
            ON CONFLICT (postcode, electorate_name, state_or_territory, match_method)
            DO UPDATE SET
                confidence = EXCLUDED.confidence,
                locality_count = EXCLUDED.locality_count,
                localities = EXCLUDED.localities,
                redistributed_electorates = EXCLUDED.redistributed_electorates,
                other_localities = EXCLUDED.other_localities,
                aec_division_ids = EXCLUDED.aec_division_ids,
                source_document_id = EXCLUDED.source_document_id,
                source_updated_text = EXCLUDED.source_updated_text,
                source_boundary_context = EXCLUDED.source_boundary_context,
                current_member_context = EXCLUDED.current_member_context,
                metadata = EXCLUDED.metadata,
                updated_at = now()
            """,
            {
                "postcode": str(record.get("postcode") or ""),
                "electorate_name": str(record.get("electorate_name") or ""),
                "state_or_territory": str(record.get("state_or_territory") or ""),
                "match_method": record.get("match_method") or "aec_postcode_locality_search",
                "confidence": Decimal(str(record.get("confidence") or "0")),
                "locality_count": int(record.get("locality_count") or 0),
                "localities": as_jsonb(record.get("localities") or []),
                "redistributed_electorates": as_jsonb(
                    record.get("redistributed_electorates") or []
                ),
                "other_localities": as_jsonb(record.get("other_localities") or []),
                "aec_division_ids": as_jsonb(record.get("aec_division_ids") or []),
                "source_document_id": source_document_id,
                "source_updated_text": record.get("page_updated_text") or None,
                "source_boundary_context": record.get("source_boundary_context")
                or "next_federal_election_electorates",
                "current_member_context": record.get("current_member_context")
                or "previous_election_or_subsequent_by_election_member",
                "metadata": as_jsonb(_postcode_record_metadata(record)),
            },
        )


def load_postcode_electorate_crosswalk(
    conn,
    jsonl_path: Path | None = None,
) -> dict[str, Any]:
    path = jsonl_path or latest_aec_electorate_finder_postcodes_jsonl()
    if path is None:
        return {
            "postcode_electorate_crosswalk_rows": 0,
            "skipped_reason": "no_processed_aec_electorate_finder_postcodes",
        }
    path = _resolve_project_path(path)

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    artifact_postcodes = _postcode_artifact_postcodes(path, records)
    artifact_match_methods = {
        str(record.get("match_method") or "aec_postcode_locality_search")
        for record in records
    } or {"aec_postcode_locality_search"}

    resolved_records: list[tuple[dict[str, Any], int]] = []
    unresolved_records: list[dict[str, Any]] = []
    skipped_missing_electorate = 0
    for record in records:
        postcode = str(record.get("postcode") or "")
        electorate_name = str(record.get("electorate_name") or "")
        state = str(record.get("state_or_territory") or "")
        if not postcode or not electorate_name:
            continue
        electorate_id = _find_house_electorate_id(
            conn,
            electorate_name=electorate_name,
            state_or_territory=state or None,
        )
        if electorate_id is None:
            skipped_missing_electorate += 1
            unresolved_records.append(record)
            continue
        resolved_records.append((record, electorate_id))

    if artifact_postcodes:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM postcode_electorate_crosswalk
                WHERE postcode = ANY(%s)
                  AND match_method = ANY(%s)
                """,
                (sorted(artifact_postcodes), sorted(artifact_match_methods)),
            )
            cur.execute(
                """
                DELETE FROM postcode_electorate_crosswalk_unresolved
                WHERE postcode = ANY(%s)
                  AND match_method = ANY(%s)
                """,
                (sorted(artifact_postcodes), sorted(artifact_match_methods)),
            )

    source_doc_cache: dict[str, int] = {}
    inserted_or_updated = 0
    unresolved_inserted_or_updated = 0
    postcode_count: set[str] = set()
    ambiguous_postcodes: set[str] = set()

    for record in unresolved_records:
        postcode = str(record.get("postcode") or "")
        if not postcode:
            continue
        source_document_id = _postcode_source_document_id(
            conn,
            record,
            source_doc_cache,
        )
        _insert_unresolved_postcode_candidate(
            conn,
            record=record,
            source_document_id=source_document_id,
        )
        unresolved_inserted_or_updated += 1
        postcode_count.add(postcode)
        if record.get("ambiguity") == "ambiguous_postcode":
            ambiguous_postcodes.add(postcode)

    for record, electorate_id in resolved_records:
        postcode = str(record.get("postcode") or "")
        state = str(record.get("state_or_territory") or "")
        source_document_id = _postcode_source_document_id(
            conn,
            record,
            source_doc_cache,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                    INSERT INTO postcode_electorate_crosswalk (
                        postcode, electorate_id, state_or_territory, match_method,
                        confidence, locality_count, localities,
                        redistributed_electorates, other_localities,
                        aec_division_ids, source_document_id, source_updated_text,
                        source_boundary_context, current_member_context, metadata
                    )
                    VALUES (
                        %(postcode)s, %(electorate_id)s, %(state_or_territory)s,
                        %(match_method)s, %(confidence)s, %(locality_count)s,
                        %(localities)s, %(redistributed_electorates)s,
                        %(other_localities)s, %(aec_division_ids)s,
                        %(source_document_id)s, %(source_updated_text)s,
                        %(source_boundary_context)s, %(current_member_context)s,
                        %(metadata)s
                    )
                    ON CONFLICT (postcode, electorate_id, match_method) DO UPDATE SET
                        state_or_territory = EXCLUDED.state_or_territory,
                        confidence = EXCLUDED.confidence,
                        locality_count = EXCLUDED.locality_count,
                        localities = EXCLUDED.localities,
                        redistributed_electorates = EXCLUDED.redistributed_electorates,
                        other_localities = EXCLUDED.other_localities,
                        aec_division_ids = EXCLUDED.aec_division_ids,
                        source_document_id = EXCLUDED.source_document_id,
                        source_updated_text = EXCLUDED.source_updated_text,
                        source_boundary_context = EXCLUDED.source_boundary_context,
                        current_member_context = EXCLUDED.current_member_context,
                        metadata = EXCLUDED.metadata
                    """,
                {
                    "postcode": postcode,
                    "electorate_id": electorate_id,
                    "state_or_territory": state or None,
                    "match_method": record.get("match_method") or "aec_postcode_locality_search",
                    "confidence": Decimal(str(record.get("confidence") or "0")),
                    "locality_count": int(record.get("locality_count") or 0),
                    "localities": as_jsonb(record.get("localities") or []),
                    "redistributed_electorates": as_jsonb(
                        record.get("redistributed_electorates") or []
                    ),
                    "other_localities": as_jsonb(record.get("other_localities") or []),
                    "aec_division_ids": as_jsonb(record.get("aec_division_ids") or []),
                    "source_document_id": source_document_id,
                    "source_updated_text": record.get("page_updated_text") or None,
                    "source_boundary_context": record.get("source_boundary_context")
                    or "next_federal_election_electorates",
                    "current_member_context": record.get("current_member_context")
                    or "previous_election_or_subsequent_by_election_member",
                    "metadata": as_jsonb(_postcode_record_metadata(record)),
                },
            )
        inserted_or_updated += 1
        postcode_count.add(postcode)
        if record.get("ambiguity") == "ambiguous_postcode":
            ambiguous_postcodes.add(postcode)
    conn.commit()
    return {
        "postcode_electorate_crosswalk_rows": inserted_or_updated,
        "postcodes": len(postcode_count),
        "postcodes_refreshed": len(artifact_postcodes),
        "ambiguous_postcodes": len(ambiguous_postcodes),
        "source_documents_upserted": len(source_doc_cache),
        "skipped_missing_electorate": skipped_missing_electorate,
        "unresolved_postcode_candidates": unresolved_inserted_or_updated,
        "jsonl_path": str(path),
    }


def get_or_create_industry_code(conn, scheme: str, code: str, label: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO industry_code (scheme, code, label)
            VALUES (%s, %s, %s)
            ON CONFLICT (scheme, code) DO UPDATE SET label = EXCLUDED.label
            RETURNING id
            """,
            (scheme, code, label),
        )
        row = cur.fetchone()
    return int(row[0])


def load_roster(conn, roster_path: Path | None = None) -> dict[str, int]:
    path = roster_path or latest_file(PROCESSED_DIR / "rosters", "aph_current_parliament_*.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "CWLTH")
    source_doc_cache: dict[str, int] = {}
    roster_generated_at = parse_datetime(payload.get("generated_at", ""))
    roster_generated_date = roster_generated_at.date() if roster_generated_at else date.today()

    people_count = 0
    office_count = 0
    current_office_external_keys: set[str] = set()
    for person in payload["people"]:
        source_metadata_path = person["source_metadata_path"]
        if source_metadata_path not in source_doc_cache:
            source_doc_cache[source_metadata_path] = upsert_source_document(conn, Path(source_metadata_path))
        source_document_id = source_doc_cache[source_metadata_path]

        party_id = get_or_create_party(conn, person["party"], jurisdiction_id)
        chamber = person["chamber"]
        electorate_name = (
            person["electorate"] if chamber == "house" else f"Senate - {person['state']}"
        )
        electorate_id = get_or_create_electorate(
            conn,
            electorate_name,
            "house" if chamber == "house" else "senate",
            person["state"],
            jurisdiction_id,
        )

        external_key = (
            f"aph_current:{chamber}:{person['state']}:{person['electorate']}:"
            f"{normalize_name(person['canonical_name'])}"
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO person (
                    external_key, display_name, canonical_name, first_name, last_name,
                    honorific, gender, source_document_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_key) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    canonical_name = EXCLUDED.canonical_name,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    honorific = EXCLUDED.honorific,
                    gender = EXCLUDED.gender,
                    source_document_id = EXCLUDED.source_document_id,
                    metadata = EXCLUDED.metadata
                RETURNING id
                """,
                (
                    external_key,
                    person["display_name"],
                    person["canonical_name"],
                    person["first_name"],
                    person["surname"],
                    person["honorific"],
                    person["gender"],
                    source_document_id,
                    as_jsonb(person),
                ),
            )
            person_id = int(cur.fetchone()[0])

            office_external_key = f"{external_key}:current_office"
            current_office_external_keys.add(office_external_key)
            cur.execute(
                """
                INSERT INTO office_term (
                    external_key, person_id, chamber, electorate_id, party_id,
                    role_title, source_document_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_key) DO UPDATE SET
                    person_id = EXCLUDED.person_id,
                    chamber = EXCLUDED.chamber,
                    electorate_id = EXCLUDED.electorate_id,
                    party_id = EXCLUDED.party_id,
                    role_title = EXCLUDED.role_title,
                    term_end = NULL,
                    source_document_id = EXCLUDED.source_document_id,
                    metadata = EXCLUDED.metadata
                """,
                (
                    office_external_key,
                    person_id,
                    chamber,
                    electorate_id,
                    party_id,
                    person["parliamentary_title"],
                    source_document_id,
                    as_jsonb(person),
                ),
            )
        people_count += 1
        office_count += 1

    closed_office_terms = 0
    if current_office_external_keys:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE office_term
                SET
                    term_end = %s,
                    metadata = office_term.metadata || %s
                WHERE term_end IS NULL
                  AND external_key LIKE 'aph_current:%%:current_office'
                  AND external_key <> ALL(%s)
                  AND metadata ? 'source_row_number'
                """,
                (
                    roster_generated_date,
                    as_jsonb(
                        {
                            "ended_by_loader": "load_roster",
                            "ended_reason": "absent_from_current_aph_roster_snapshot",
                            "roster_generated_at": payload.get("generated_at"),
                            "roster_path": str(path),
                        }
                    ),
                    list(current_office_external_keys),
                ),
            )
            closed_office_terms = cur.rowcount

    conn.commit()
    return {
        "people": people_count,
        "office_terms": office_count,
        "stale_office_terms_closed": closed_office_terms,
    }


def _load_aec_money_flow_jsonl(
    conn,
    path: Path,
    *,
    default_source_dataset: str,
) -> dict[str, int]:
    source_doc_cache: dict[str, int] = {}
    jurisdiction_cache: dict[tuple[str, str, str], int] = {}

    def record_jurisdiction_id(record: dict[str, Any]) -> int:
        name = record.get("jurisdiction_name") or "Commonwealth"
        level = record.get("jurisdiction_level") or "federal"
        code = record.get("jurisdiction_code") or "CWLTH"
        key = (str(name), str(level), str(code))
        if key not in jurisdiction_cache:
            jurisdiction_cache[key] = get_or_create_jurisdiction(conn, *key)
        return jurisdiction_cache[key]

    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            metadata_path = record["source_metadata_path"]
            if metadata_path not in source_doc_cache:
                source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
            source_document_id = source_doc_cache[metadata_path]

            source_entity_id = get_or_create_entity(conn, record.get("source_raw_name") or "")
            recipient_entity_id = get_or_create_entity(conn, record.get("recipient_raw_name") or "")
            amount = Decimal(record["amount_aud"]) if record["amount_aud"] else None
            date_received, date_validation = parse_aec_money_flow_date(
                record.get("date") or "",
                record.get("financial_year") or "",
            )
            source_dataset = record.get("source_dataset") or default_source_dataset
            jurisdiction_id = record_jurisdiction_id(record)
            external_key = (
                f"{source_dataset}:{record['source_table']}:{record['source_row_number']}:"
                f"{record.get('financial_year') or record.get('event_name') or ''}:"
                f"{normalize_name(record.get('source_raw_name') or '')}:"
                f"{normalize_name(record.get('recipient_raw_name') or '')}:"
                f"{record['amount_aud']}"
            )

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_entity_id, source_raw_name,
                        recipient_entity_id, recipient_raw_name, amount,
                        financial_year, date_received, return_type, receipt_type,
                        disclosure_category, jurisdiction_id, source_document_id,
                        source_row_ref, original_text, confidence, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    ON CONFLICT (external_key) DO UPDATE SET
                        source_entity_id = EXCLUDED.source_entity_id,
                        source_raw_name = EXCLUDED.source_raw_name,
                        recipient_entity_id = EXCLUDED.recipient_entity_id,
                        recipient_raw_name = EXCLUDED.recipient_raw_name,
                        amount = EXCLUDED.amount,
                        financial_year = EXCLUDED.financial_year,
                        date_received = EXCLUDED.date_received,
                        return_type = EXCLUDED.return_type,
                        receipt_type = EXCLUDED.receipt_type,
                        disclosure_category = EXCLUDED.disclosure_category,
                        jurisdiction_id = EXCLUDED.jurisdiction_id,
                        source_document_id = EXCLUDED.source_document_id,
                        source_row_ref = EXCLUDED.source_row_ref,
                        original_text = EXCLUDED.original_text,
                        confidence = EXCLUDED.confidence,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        external_key,
                        source_entity_id,
                        record.get("source_raw_name") or "Unknown",
                        recipient_entity_id,
                        record.get("recipient_raw_name") or "Unknown",
                        amount,
                        record.get("financial_year") or None,
                        date_received,
                        record.get("return_type") or None,
                        record.get("receipt_type") or None,
                        record.get("flow_kind") or source_dataset,
                        jurisdiction_id,
                        source_document_id,
                        f"{record['source_table']}:{record['source_row_number']}",
                        json.dumps(record["original"], sort_keys=True),
                        "unresolved",
                        as_jsonb({**record, "date_validation": date_validation}),
                    ),
                )
            count += 1

    conn.commit()
    direct_link_summary = link_aec_direct_representative_money_flows(conn)
    campaign_link_summary = link_aec_candidate_campaign_money_flows(conn)
    return {"money_flows": count, **direct_link_summary, **campaign_link_summary}


def load_aec_money_flows(conn, jsonl_path: Path | None = None) -> dict[str, int]:
    path = jsonl_path or latest_file(PROCESSED_DIR / "aec_annual_money_flows", "*.jsonl")
    return _load_aec_money_flow_jsonl(conn, path, default_source_dataset="aec_annual")


def load_aec_election_money_flows(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_file(PROCESSED_DIR / "aec_election_money_flows", "*.jsonl")
    except FileNotFoundError:
        return {
            "money_flows": 0,
            "skipped_reason": "no_processed_aec_election_money_flows",
        }
    return _load_aec_money_flow_jsonl(conn, path, default_source_dataset="aec_election")


def load_aec_public_funding_money_flows(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_file(PROCESSED_DIR / "aec_public_funding_money_flows", "*.jsonl")
    except FileNotFoundError:
        return {
            "money_flows": 0,
            "skipped_reason": "no_processed_aec_public_funding_money_flows",
        }
    return _load_aec_money_flow_jsonl(conn, path, default_source_dataset="aec_public_funding")


def load_qld_ecq_eds_money_flows(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_file(PROCESSED_DIR / "qld_ecq_eds_money_flows", "*.jsonl")
    except FileNotFoundError:
        return {
            "money_flows": 0,
            "skipped_reason": "no_processed_qld_ecq_eds_money_flows",
        }
    return _load_aec_money_flow_jsonl(conn, path, default_source_dataset="qld_ecq_eds")


def _latest_qld_contexts_jsonl() -> Path:
    return latest_file(PROCESSED_DIR / "qld_ecq_eds_contexts", "*.jsonl")


def _qld_ecq_eds_entity_ids_by_normalized_name(conn, normalized_name: str) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT entity.id
            FROM entity
            WHERE entity.normalized_name = %s
              AND EXISTS (
                  SELECT 1
                  FROM money_flow
                  WHERE money_flow.metadata->>'source_dataset' = 'qld_ecq_eds'
                    AND (
                        money_flow.source_entity_id = entity.id
                        OR money_flow.recipient_entity_id = entity.id
                    )
              )
            ORDER BY entity.id
            """,
            (normalized_name,),
        )
        return [int(row[0]) for row in cur.fetchall()]


def _qld_identifier_coverage_counts(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                count(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM entity_identifier
                        WHERE entity_identifier.entity_id = money_flow.source_entity_id
                          AND entity_identifier.identifier_type LIKE 'qld_ecq_%%'
                    )
                ) AS source_identifier_backed_rows,
                count(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM entity_identifier
                        WHERE entity_identifier.entity_id = money_flow.recipient_entity_id
                          AND entity_identifier.identifier_type LIKE 'qld_ecq_%%'
                    )
                ) AS recipient_identifier_backed_rows
            FROM money_flow
            WHERE money_flow.metadata->>'source_dataset' = 'qld_ecq_eds'
            """
        )
        row = cur.fetchone()
    return {
        "source_identifier_backed_money_flows": int(row[0] or 0),
        "recipient_identifier_backed_money_flows": int(row[1] or 0),
    }


def load_qld_ecq_eds_participants(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_file(PROCESSED_DIR / "qld_ecq_eds_participants", "*.jsonl")
    except FileNotFoundError:
        return {
            "participant_records": 0,
            "skipped_reason": "no_processed_qld_ecq_eds_participants",
        }

    records: list[dict[str, Any]] = []
    source_doc_cache: dict[str, int] = {}
    expected_source_scope = {
        (spec.source_id, spec.source_record_type)
        for spec in QLD_ECQ_EDS_PARTICIPANT_LOOKUPS
    }
    observed_source_scope: set[tuple[str, str]] = set()
    normalized_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            records.append(record)
            observed_source_scope.add((record["source_id"], record["source_record_type"]))
            normalized_counts[record["normalized_name"]] += 1

    stale_entity_ids: set[int] = set()
    with conn.cursor() as cur:
        for source_id, source_record_type in sorted(expected_source_scope):
            cur.execute(
                """
                DELETE FROM entity_identifier
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'source_id' = %s
                  AND metadata->>'source_record_type' = %s
                RETURNING entity_id
                """,
                (QLD_ECQ_PARTICIPANT_PARSER_NAME, source_id, source_record_type),
            )
            stale_entity_ids.update(int(row[0]) for row in cur.fetchall())
            cur.execute(
                """
                DELETE FROM entity_alias
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'source_id' = %s
                  AND metadata->>'source_record_type' = %s
                """,
                (QLD_ECQ_PARTICIPANT_PARSER_NAME, source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM entity_match_candidate
                WHERE observation_id IN (
                    SELECT id
                    FROM official_identifier_observation
                    WHERE source_id = %s
                      AND source_record_type = %s
                )
                """,
                (source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM official_identifier_observation
                WHERE source_id = %s
                  AND source_record_type = %s
                  AND metadata->>'official_parser_name' = %s
                """,
                (source_id, source_record_type, QLD_ECQ_PARTICIPANT_PARSER_NAME),
            )
        for entity_id in sorted(stale_entity_ids):
            cur.execute(
                """
                UPDATE entity
                SET entity_type = 'unknown'
                WHERE id = %s
                  AND entity_type IN (
                      'associated_entity',
                      'candidate_or_elector',
                      'local_group',
                      'political_party'
                  )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM entity_identifier
                      WHERE entity_identifier.entity_id = entity.id
                        AND entity_identifier.metadata->>'official_parser_name' = %s
                  )
                """,
                (entity_id, QLD_ECQ_PARTICIPANT_PARSER_NAME),
            )

    observed = 0
    auto_accepted = 0
    needs_review = 0
    identifiers_inserted = 0
    aliases_inserted = 0
    observations_without_qld_money_flow_match = 0
    duplicate_lookup_names_skipped = 0
    candidate_or_elector_name_only_matches_needing_review = 0
    source_counts: Counter[str] = Counter()
    for record in records:
        metadata_path = record.get("source_metadata_path")
        source_document_id = None
        if metadata_path:
            if metadata_path not in source_doc_cache:
                source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
            source_document_id = source_doc_cache[metadata_path]

        observation_id = _insert_official_identifier_observation(conn, record, source_document_id)
        observed += 1
        source_counts[record["source_record_type"]] += 1

        candidate_entity_ids = _qld_ecq_eds_entity_ids_by_normalized_name(
            conn,
            record["normalized_name"],
        )
        if normalized_counts[record["normalized_name"]] != 1:
            duplicate_lookup_names_skipped += 1
            for candidate_entity_id in candidate_entity_ids:
                _insert_match_candidate(
                    conn,
                    entity_id=candidate_entity_id,
                    observation_id=observation_id,
                    match_method="qld_ecq_exact_name_duplicate_lookup",
                    confidence="unresolved",
                    status="needs_review",
                    evidence_note=(
                        "QLD ECQ lookup has duplicate normalized participant names; "
                        "manual review is required before attaching the identifier."
                    ),
                    metadata={
                        "candidate_count": len(candidate_entity_ids),
                        "lookup_name_count": normalized_counts[record["normalized_name"]],
                    },
                )
                needs_review += 1
            continue

        if len(candidate_entity_ids) != 1:
            if candidate_entity_ids:
                needs_review += len(candidate_entity_ids)
            else:
                observations_without_qld_money_flow_match += 1
            for candidate_entity_id in candidate_entity_ids:
                _insert_match_candidate(
                    conn,
                    entity_id=candidate_entity_id,
                    observation_id=observation_id,
                    match_method="qld_ecq_exact_name_context_ambiguous",
                    confidence="unresolved",
                    status="needs_review",
                    evidence_note=(
                        "Exact QLD ECQ participant name matched multiple QLD disclosure entities."
                    ),
                    metadata={"candidate_count": len(candidate_entity_ids)},
                )
            continue

        entity_id = candidate_entity_ids[0]
        if record.get("entity_type") not in QLD_ECQ_AUTO_ACCEPT_PARTICIPANT_ENTITY_TYPES:
            _insert_match_candidate(
                conn,
                entity_id=entity_id,
                observation_id=observation_id,
                match_method="qld_ecq_exact_name_requires_participant_context",
                confidence="unresolved",
                status="needs_review",
                evidence_note=(
                    "Exact QLD ECQ participant name matched one QLD disclosure entity, "
                    "but candidate/elector identity still requires event, electorate, "
                    "or role context before attaching the ECQ identifier."
                ),
                metadata={
                    "candidate_count": 1,
                    "entity_type": record.get("entity_type"),
                    "auto_accept_blocked_reason": "name_only_candidate_or_elector_match",
                },
            )
            needs_review += 1
            candidate_or_elector_name_only_matches_needing_review += 1
            continue

        _insert_match_candidate(
            conn,
            entity_id=entity_id,
            observation_id=observation_id,
            match_method="qld_ecq_exact_name_in_disclosure_context",
            confidence="exact_name_context",
            status="auto_accepted",
            evidence_note=(
                "Exact normalized participant name matched one entity already present "
                "in QLD ECQ disclosure rows."
            ),
            metadata={"candidate_count": 1},
        )
        auto_accepted += 1
        _update_entity_type_from_official(conn, entity_id, record.get("entity_type", ""))
        for identifier in record.get("identifiers") or []:
            if _insert_entity_identifier(
                conn,
                entity_id=entity_id,
                identifier=identifier,
                source_document_id=source_document_id,
                record=record,
            ):
                identifiers_inserted += 1
        aliases_inserted += _insert_entity_aliases(
            conn,
            entity_id=entity_id,
            aliases=record.get("aliases") or [],
            source_document_id=source_document_id,
            record=record,
        )

    conn.commit()
    coverage_counts = _qld_identifier_coverage_counts(conn)
    return {
        "participant_records": observed,
        "auto_accepted_matches": auto_accepted,
        "needs_review_matches": needs_review,
        "observations_without_qld_money_flow_match": observations_without_qld_money_flow_match,
        "duplicate_lookup_names_skipped": duplicate_lookup_names_skipped,
        "candidate_or_elector_name_only_matches_needing_review": (
            candidate_or_elector_name_only_matches_needing_review
        ),
        "identifiers_inserted": identifiers_inserted,
        "aliases_inserted": aliases_inserted,
        "source_record_type_counts": dict(sorted(source_counts.items())),
        "expected_source_scope": [
            {"source_id": source_id, "source_record_type": source_record_type}
            for source_id, source_record_type in sorted(expected_source_scope)
        ],
        "observed_source_scope": [
            {"source_id": source_id, "source_record_type": source_record_type}
            for source_id, source_record_type in sorted(observed_source_scope)
        ],
        "jsonl_path": str(path),
        **coverage_counts,
    }


def _qld_context_source_scope() -> list[dict[str, str]]:
    return [
        {"source_id": spec.source_id, "source_record_type": spec.source_record_type}
        for spec in QLD_ECQ_EDS_CONTEXT_LOOKUPS
    ]


def _qld_context_compact_record(
    record: dict[str, Any],
    source_document_id: int | None,
    *,
    match_method: str,
) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    compact = {
        "status": "matched",
        "match_method": match_method,
        "source_id": record.get("source_id"),
        "source_record_type": record.get("source_record_type"),
        "context_type": record.get("context_type"),
        "external_id": record.get("external_id"),
        "identifier": record.get("identifier") or {},
        "name": record.get("display_name"),
        "normalized_name": record.get("normalized_name"),
        "level": record.get("level"),
        "code": metadata.get("code"),
        "event_type": metadata.get("event_type"),
        "is_state": metadata.get("is_state"),
        "polling_date": metadata.get("polling_date"),
        "start_date": metadata.get("start_date"),
        "date_caveat": (
            "ECQ event polling/start dates describe the election event, not the "
            "gift, donation, or expenditure transaction date."
            if record.get("context_type") == "political_event"
            else None
        ),
        "source_document_id": source_document_id,
    }
    return {key: value for key, value in compact.items() if value is not None}


def _unique_qld_contexts_by_name(
    records: list[dict[str, Any]],
    context_type: str,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("context_type") == context_type:
            grouped[str(record.get("normalized_name") or "")].append(record)
    return (
        {
            normalized_name: matches[0]
            for normalized_name, matches in grouped.items()
            if normalized_name and len(matches) == 1
        },
        {normalized_name for normalized_name, matches in grouped.items() if len(matches) > 1},
    )


def load_qld_ecq_eds_contexts(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_file(PROCESSED_DIR / "qld_ecq_eds_contexts", "*.jsonl")
    except FileNotFoundError:
        return {
            "context_records": 0,
            "skipped_reason": "no_processed_qld_ecq_eds_contexts",
        }

    records: list[dict[str, Any]] = []
    source_doc_cache: dict[str, int] = {}
    source_document_by_stable_key: dict[str, int | None] = {}
    source_counts: Counter[str] = Counter()
    context_type_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            records.append(record)
            source_counts[str(record.get("source_record_type") or "unknown")] += 1
            context_type_counts[str(record.get("context_type") or "unknown")] += 1
            metadata_path = record.get("source_metadata_path")
            source_document_id = None
            if metadata_path:
                if metadata_path not in source_doc_cache:
                    source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
                source_document_id = source_doc_cache[metadata_path]
            source_document_by_stable_key[str(record.get("stable_key") or "")] = source_document_id

    events_by_name, duplicate_event_names = _unique_qld_contexts_by_name(
        records,
        "political_event",
    )
    local_electorates_by_name, duplicate_local_electorate_names = _unique_qld_contexts_by_name(
        records,
        "local_electorate",
    )

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, metadata
            FROM money_flow
            WHERE metadata->>'source_dataset' = 'qld_ecq_eds'
            ORDER BY id
            """
        )
        rows = [(int(row[0]), row[1] or {}) for row in cur.fetchall()]

    event_matched = 0
    event_unmatched = 0
    event_ambiguous = 0
    event_missing = 0
    local_electorate_matched = 0
    local_electorate_unmatched = 0
    local_electorate_ambiguous = 0
    local_electorate_missing = 0

    with conn.cursor() as cur:
        for money_flow_id, metadata in rows:
            updated_metadata = dict(metadata)
            event_name = str(updated_metadata.get("event_name") or "").strip()
            local_electorate_name = str(updated_metadata.get("local_electorate") or "").strip()
            qld_context: dict[str, Any] = {
                "loader_name": QLD_ECQ_CONTEXT_PARSER_NAME,
                "source_scope": _qld_context_source_scope(),
            }

            if event_name:
                normalized_event_name = normalize_name(event_name)
                if normalized_event_name in events_by_name:
                    event_record = events_by_name[normalized_event_name]
                    qld_context["event"] = _qld_context_compact_record(
                        event_record,
                        source_document_by_stable_key.get(str(event_record.get("stable_key") or "")),
                        match_method="qld_ecq_exact_normalized_event_name",
                    )
                    event_matched += 1
                elif normalized_event_name in duplicate_event_names:
                    qld_context["event"] = {
                        "status": "ambiguous",
                        "match_method": "qld_ecq_event_name_duplicate_lookup",
                        "name": event_name,
                        "normalized_name": normalized_event_name,
                    }
                    event_ambiguous += 1
                else:
                    qld_context["event"] = {
                        "status": "unmatched",
                        "match_method": "qld_ecq_exact_normalized_event_name",
                        "name": event_name,
                        "normalized_name": normalized_event_name,
                    }
                    event_unmatched += 1
            else:
                qld_context["event"] = {"status": "not_present_in_export"}
                event_missing += 1

            if local_electorate_name:
                normalized_local_electorate_name = normalize_name(local_electorate_name)
                if normalized_local_electorate_name in local_electorates_by_name:
                    local_electorate_record = local_electorates_by_name[
                        normalized_local_electorate_name
                    ]
                    qld_context["local_electorate"] = _qld_context_compact_record(
                        local_electorate_record,
                        source_document_by_stable_key.get(
                            str(local_electorate_record.get("stable_key") or "")
                        ),
                        match_method="qld_ecq_exact_normalized_local_electorate_name",
                    )
                    local_electorate_matched += 1
                elif normalized_local_electorate_name in duplicate_local_electorate_names:
                    qld_context["local_electorate"] = {
                        "status": "ambiguous",
                        "match_method": "qld_ecq_local_electorate_duplicate_lookup",
                        "name": local_electorate_name,
                        "normalized_name": normalized_local_electorate_name,
                    }
                    local_electorate_ambiguous += 1
                else:
                    qld_context["local_electorate"] = {
                        "status": "unmatched",
                        "match_method": "qld_ecq_exact_normalized_local_electorate_name",
                        "name": local_electorate_name,
                        "normalized_name": normalized_local_electorate_name,
                    }
                    local_electorate_unmatched += 1
            else:
                qld_context["local_electorate"] = {"status": "not_present_in_export"}
                local_electorate_missing += 1

            updated_metadata["qld_ecq_context"] = qld_context
            cur.execute(
                """
                UPDATE money_flow
                SET metadata = %s
                WHERE id = %s
                """,
                (as_jsonb(updated_metadata), money_flow_id),
            )

    conn.commit()
    return {
        "context_records": len(records),
        "money_flow_rows_considered": len(rows),
        "event_context_matched_money_flows": event_matched,
        "event_context_unmatched_money_flows": event_unmatched,
        "event_context_ambiguous_money_flows": event_ambiguous,
        "event_context_missing_money_flows": event_missing,
        "local_electorate_context_matched_money_flows": local_electorate_matched,
        "local_electorate_context_unmatched_money_flows": local_electorate_unmatched,
        "local_electorate_context_ambiguous_money_flows": local_electorate_ambiguous,
        "local_electorate_context_missing_money_flows": local_electorate_missing,
        "duplicate_event_lookup_names": len(duplicate_event_names),
        "duplicate_local_electorate_lookup_names": len(duplicate_local_electorate_names),
        "source_record_type_counts": dict(sorted(source_counts.items())),
        "context_type_counts": dict(sorted(context_type_counts.items())),
        "source_documents_upserted": len(source_doc_cache),
        "jsonl_path": str(path),
    }


def _person_lookup(conn) -> dict[str, int]:
    lookup: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute("SELECT id, display_name, canonical_name FROM person")
        for person_id, display_name, canonical_name in cur.fetchall():
            for name in (display_name, canonical_name):
                normalized = normalize_name(name or "")
                if normalized:
                    lookup[normalized] = int(person_id)
    return lookup


def _unique_representative_name_lookup(conn) -> dict[str, int]:
    candidate_ids: dict[str, set[int]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name, canonical_name, first_name, last_name
            FROM person
            """
        )
        for person_id, display_name, canonical_name, first_name, last_name in cur.fetchall():
            names = {
                display_name or "",
                canonical_name or "",
                " ".join(part for part in (first_name or "", last_name or "") if part),
            }
            for name in names:
                normalized = normalize_representative_return_name(name)
                if normalized:
                    candidate_ids[normalized].add(int(person_id))
    return {
        normalized: next(iter(person_ids))
        for normalized, person_ids in candidate_ids.items()
        if len(person_ids) == 1
    }


def link_aec_direct_representative_money_flows(conn) -> dict[str, int]:
    unique_lookup = _unique_representative_name_lookup(conn)
    all_candidates: dict[str, set[int]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, display_name, canonical_name, first_name, last_name
            FROM person
            """
        )
        for person_id, display_name, canonical_name, first_name, last_name in cur.fetchall():
            for name in (
                display_name or "",
                canonical_name or "",
                " ".join(part for part in (first_name or "", last_name or "") if part),
            ):
                normalized = normalize_representative_return_name(name)
                if normalized:
                    all_candidates[normalized].add(int(person_id))

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, recipient_raw_name, return_type
            FROM money_flow
            WHERE return_type IS NOT NULL
            """
        )
        rows = [
            (int(row[0]), row[1] or "", row[2] or "")
            for row in cur.fetchall()
            if is_direct_representative_return_type(row[2] or "")
        ]

    considered = len(rows)
    linked = 0
    unmatched = 0
    ambiguous = 0
    for money_flow_id, recipient_raw_name, return_type in rows:
        normalized = normalize_representative_return_name(recipient_raw_name)
        candidate_ids = all_candidates.get(normalized, set())
        person_id = unique_lookup.get(normalized)
        if person_id is not None:
            status = "linked"
            confidence = "exact_name_context"
            linked += 1
        elif candidate_ids:
            person_id = None
            status = "ambiguous"
            confidence = "unresolved"
            ambiguous += 1
        else:
            person_id = None
            status = "unmatched"
            confidence = "unresolved"
            unmatched += 1
        metadata_patch = {
            "recipient_person_match": {
                "method": "aec_direct_representative_return_cleaned_name_exact_unique",
                "status": status,
                "return_type": return_type,
                "raw_recipient_name": recipient_raw_name,
                "normalized_recipient_name": normalized,
                "candidate_person_count": len(candidate_ids),
            }
        }
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE money_flow
                SET
                    recipient_person_id = %s,
                    confidence = %s,
                    metadata = money_flow.metadata || %s
                WHERE id = %s
                """,
                (
                    person_id,
                    confidence,
                    as_jsonb(metadata_patch),
                    money_flow_id,
                ),
            )

    conn.commit()
    return {
        "direct_representative_money_flows_considered": considered,
        "direct_representative_money_flows_linked": linked,
        "direct_representative_money_flows_unmatched": unmatched,
        "direct_representative_money_flows_ambiguous": ambiguous,
    }


def _unique_house_candidate_campaign_lookup(conn) -> dict[tuple[str, str, str], int]:
    candidate_ids: dict[tuple[str, str, str], set[int]] = defaultdict(set)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                person.id,
                person.display_name,
                person.canonical_name,
                person.first_name,
                person.last_name,
                electorate.name,
                COALESCE(NULLIF(electorate.state_or_territory, ''), office_term.metadata->>'state')
            FROM office_term
            JOIN person ON person.id = office_term.person_id
            JOIN electorate ON electorate.id = office_term.electorate_id
            WHERE office_term.chamber = 'house'
            """
        )
        for (
            person_id,
            display_name,
            canonical_name,
            first_name,
            last_name,
            electorate_name,
            state,
        ) in cur.fetchall():
            electorate_key = normalize_electorate_name(electorate_name or "")
            state_key = state_code(state or "")
            if not electorate_key or not state_key:
                continue
            names = {
                display_name or "",
                canonical_name or "",
                " ".join(part for part in (first_name or "", last_name or "") if part),
            }
            for name in names:
                person_key = normalize_representative_return_name(name)
                if person_key:
                    candidate_ids[(person_key, electorate_key, state_key)].add(int(person_id))

    return {
        key: next(iter(person_ids))
        for key, person_ids in candidate_ids.items()
        if len(person_ids) == 1
    }


def link_aec_candidate_campaign_money_flows(conn) -> dict[str, int]:
    unique_lookup = _unique_house_candidate_campaign_lookup(conn)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id,
                recipient_raw_name,
                metadata->'candidate_context'->>'name' AS candidate_name,
                metadata->'candidate_context'->>'electorate_name' AS electorate_name,
                metadata->'candidate_context'->>'electorate_state' AS electorate_state,
                metadata->'candidate_context'->>'return_type' AS candidate_return_type,
                metadata->>'flow_kind' AS flow_kind,
                metadata->'campaign_support_attribution' AS campaign_support_attribution
            FROM money_flow
            WHERE metadata->>'source_dataset' = 'aec_election'
              AND metadata ? 'candidate_context'
              AND lower(COALESCE(metadata->'candidate_context'->>'return_type', '')) = 'candidate'
            """
        )
        rows = cur.fetchall()

    considered = len(rows)
    linked = 0
    unmatched = 0
    for (
        money_flow_id,
        recipient_raw_name,
        candidate_name,
        electorate_name,
        electorate_state,
        candidate_return_type,
        flow_kind,
        existing_attribution,
    ) in rows:
        raw_candidate_name = candidate_name or recipient_raw_name or ""
        person_key = normalize_representative_return_name(
            aec_candidate_name_to_canonical(raw_candidate_name)
        )
        electorate_key = normalize_electorate_name(electorate_name or "")
        state_key = state_code(electorate_state or "")
        person_id = unique_lookup.get((person_key, electorate_key, state_key))
        if person_id is None:
            confidence = "unresolved"
            status = "unmatched"
            unmatched += 1
        else:
            confidence = "name_electorate_context_without_temporal_check"
            status = "linked"
            linked += 1

        linked_attribution = (
            dict(existing_attribution) if isinstance(existing_attribution, dict) else {}
        )
        linked_attribution.setdefault("tier", "source_backed_candidate_campaign_return")
        linked_attribution["not_personal_receipt"] = True
        linked_attribution["linked_to_person_by"] = "candidate_name_electorate_state_exact_unique"
        linked_attribution["person_link_status"] = status
        metadata_patch = {
            "recipient_person_match": {
                "method": "aec_election_candidate_name_electorate_state_exact_unique",
                "status": status,
                "raw_candidate_name": raw_candidate_name,
                "normalized_candidate_name": person_key,
                "electorate_name": electorate_name or "",
                "normalized_electorate_name": electorate_key,
                "electorate_state": state_key,
                "return_type": candidate_return_type or "",
                "flow_kind": flow_kind or "",
                "attribution_scope": "campaign_context_not_personal_receipt",
                "temporal_check": "not_applied",
            },
            "campaign_support_attribution": linked_attribution,
        }
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE money_flow
                SET
                    recipient_person_id = %s,
                    confidence = %s,
                    metadata = money_flow.metadata || %s
                WHERE id = %s
                """,
                (
                    person_id,
                    confidence,
                    as_jsonb(metadata_patch),
                    money_flow_id,
                ),
            )

    conn.commit()
    return {
        "candidate_campaign_money_flows_considered": considered,
        "candidate_campaign_money_flows_linked": linked,
        "candidate_campaign_money_flows_unmatched": unmatched,
    }


def _house_electorate_person_lookup(conn) -> dict[str, int]:
    lookup: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT person.id, electorate.name
            FROM office_term
            JOIN person ON person.id = office_term.person_id
            JOIN electorate ON electorate.id = office_term.electorate_id
            WHERE office_term.chamber = 'house'
            """
        )
        for person_id, electorate_name in cur.fetchall():
            normalized = normalize_electorate_name(electorate_name or "")
            if normalized:
                lookup[normalized] = int(person_id)
    return lookup


def _can_create_house_interest_person(record: dict[str, Any]) -> bool:
    if not normalize_name(record.get("member_name", "")):
        return False
    if not normalize_name(record.get("given_names", "")):
        return False
    if not normalize_name(record.get("family_name", "")):
        return False
    if len(normalize_electorate_name(record.get("electorate", ""))) < 3:
        return False
    if not state_code(record.get("state", "")):
        return False
    return True


def get_or_create_house_interest_person(
    conn,
    record: dict[str, Any],
    source_document_id: int,
    jurisdiction_id: int,
) -> int:
    state = state_code(record["state"])
    canonical_name = " ".join(record["member_name"].split())
    external_key = (
        f"aph_current:house:{state}:{record['electorate']}:"
        f"{normalize_name(canonical_name)}"
    )
    electorate_id = get_or_create_electorate(
        conn,
        record["electorate"],
        "house",
        state,
        jurisdiction_id,
    )
    metadata = {
        "source": "derived_from_house_interest_register",
        "source_id": record["source_id"],
        "source_name": record["source_name"],
        "source_metadata_path": record["source_metadata_path"],
        "member_name": canonical_name,
        "given_names": record["given_names"],
        "family_name": record["family_name"],
        "electorate": record["electorate"],
        "state": record["state"],
        "url": record["url"],
    }
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, first_name, last_name,
                honorific, gender, source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (external_key) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                canonical_name = EXCLUDED.canonical_name,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                source_document_id = EXCLUDED.source_document_id,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (
                external_key,
                canonical_name,
                canonical_name,
                record["given_names"],
                record["family_name"],
                "",
                "",
                source_document_id,
                as_jsonb(metadata),
            ),
        )
        person_id = int(cur.fetchone()[0])
        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id,
                role_title, source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (external_key) DO UPDATE SET
                person_id = EXCLUDED.person_id,
                chamber = EXCLUDED.chamber,
                electorate_id = EXCLUDED.electorate_id,
                source_document_id = EXCLUDED.source_document_id,
                metadata = EXCLUDED.metadata
            """,
            (
                f"{external_key}:current_office",
                person_id,
                "house",
                electorate_id,
                None,
                "",
                source_document_id,
                as_jsonb(metadata),
            ),
        )
    return person_id


def load_house_interest_records(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    path = jsonl_path or latest_file(PROCESSED_DIR / "house_interest_records", "*.jsonl")
    person_lookup = _person_lookup(conn)
    electorate_lookup = _house_electorate_person_lookup(conn)
    source_doc_cache: dict[str, int] = {}
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "CWLTH")

    row_count = 0
    skipped_unmatched = 0
    unmatched: set[str] = set()
    fallback_people: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            person_id = person_lookup.get(normalize_name(record["member_name"]))
            if person_id is None:
                person_id = electorate_lookup.get(normalize_electorate_name(record["electorate"]))

            metadata_path = record["source_metadata_path"]
            if metadata_path not in source_doc_cache:
                source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
            source_document_id = source_doc_cache[metadata_path]

            if person_id is None and _can_create_house_interest_person(record):
                person_id = get_or_create_house_interest_person(
                    conn,
                    record,
                    source_document_id,
                    jurisdiction_id,
                )
                person_lookup[normalize_name(record["member_name"])] = person_id
                electorate_lookup[normalize_electorate_name(record["electorate"])] = person_id
                fallback_people.add(f"{record['member_name']} ({record['electorate']})")

            if person_id is None:
                skipped_unmatched += 1
                unmatched.add(f"{record['member_name']} ({record['electorate']})")
                continue

            counterparty = record.get("counterparty_raw_name") or ""
            source_entity_id = get_or_create_entity(conn, counterparty) if counterparty else None
            estimated_value = parse_decimal(str(record.get("estimated_value") or ""))
            date_received = parse_date(str(record.get("event_date") or ""))
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gift_interest (
                        external_key, person_id, source_entity_id, source_raw_name,
                        interest_category, description, parliament_number, chamber,
                        estimated_value, currency, date_received,
                        source_document_id, source_page_ref, original_text,
                        extraction_confidence, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_key) DO UPDATE SET
                        person_id = EXCLUDED.person_id,
                        source_entity_id = EXCLUDED.source_entity_id,
                        source_raw_name = EXCLUDED.source_raw_name,
                        interest_category = EXCLUDED.interest_category,
                        description = EXCLUDED.description,
                        estimated_value = EXCLUDED.estimated_value,
                        currency = EXCLUDED.currency,
                        date_received = EXCLUDED.date_received,
                        source_document_id = EXCLUDED.source_document_id,
                        source_page_ref = EXCLUDED.source_page_ref,
                        original_text = EXCLUDED.original_text,
                        extraction_confidence = EXCLUDED.extraction_confidence,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        record["external_key"],
                        person_id,
                        source_entity_id,
                        counterparty or None,
                        record["interest_category"],
                        record["description"],
                        "48",
                        "house",
                        estimated_value,
                        record.get("estimated_value_currency") or "AUD",
                        date_received,
                        source_document_id,
                        f"section:{record['section_number']}:owner:{record['owner_context']}",
                        record["original_section_text"],
                        "pdf_section_line_heuristic",
                        as_jsonb(record),
                    ),
                )
            row_count += 1

    conn.commit()
    return {
        "house_interest_records": row_count,
        "fallback_people_from_house_interests": sorted(fallback_people),
        "fallback_people_from_house_interests_count": len(fallback_people),
        "skipped_unmatched_people": skipped_unmatched,
        "unmatched_people": sorted(unmatched),
    }


def _senate_interest_extraction_confidence(record: dict[str, Any]) -> str:
    extraction = record.get("counterparty_extraction")
    provider_method = (
        str(extraction.get("method") or "") if isinstance(extraction, dict) else ""
    )
    if provider_method.startswith("subject_provider_verb:"):
        return "official_api_structured_provider_heuristic"
    return "official_api_structured"


def load_senate_interest_records(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    path = jsonl_path or latest_file(PROCESSED_DIR / "senate_interest_records", "*.jsonl")
    person_lookup = _person_lookup(conn)
    source_doc_cache: dict[str, int] = {}

    row_count = 0
    skipped_unmatched = 0
    unmatched_names: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            canonical_name = senate_api_name_to_canonical(record["senator_name"])
            person_id = person_lookup.get(normalize_name(canonical_name))
            if person_id is None:
                skipped_unmatched += 1
                unmatched_names.add(record["senator_name"])
                continue

            metadata_path = record["source_metadata_path"]
            if metadata_path not in source_doc_cache:
                source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
            source_document_id = source_doc_cache[metadata_path]

            counterparty = record.get("counterparty_raw_name") or ""
            source_entity_id = get_or_create_entity(conn, counterparty) if counterparty else None
            description = record.get("description") or json.dumps(
                record.get("original", {}),
                sort_keys=True,
            )
            estimated_value = parse_decimal(str(record.get("estimated_value") or ""))
            date_received = parse_date(str(record.get("event_date") or ""))
            date_reported = parse_date(
                str(record.get("reported_date") or record.get("lodgement_date") or "")
            )
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gift_interest (
                        external_key, person_id, source_entity_id, source_raw_name,
                        interest_category, description, estimated_value, currency,
                        date_received, date_reported,
                        parliament_number, chamber, source_document_id, source_page_ref,
                        original_text, extraction_confidence, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_key) DO UPDATE SET
                        person_id = EXCLUDED.person_id,
                        source_entity_id = EXCLUDED.source_entity_id,
                        source_raw_name = EXCLUDED.source_raw_name,
                        interest_category = EXCLUDED.interest_category,
                        description = EXCLUDED.description,
                        estimated_value = EXCLUDED.estimated_value,
                        currency = EXCLUDED.currency,
                        date_received = EXCLUDED.date_received,
                        date_reported = EXCLUDED.date_reported,
                        source_document_id = EXCLUDED.source_document_id,
                        source_page_ref = EXCLUDED.source_page_ref,
                        original_text = EXCLUDED.original_text,
                        extraction_confidence = EXCLUDED.extraction_confidence,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        record["external_key"],
                        person_id,
                        source_entity_id,
                        counterparty or None,
                        record["interest_category_label"],
                        description,
                        estimated_value,
                        record.get("estimated_value_currency") or "AUD",
                        date_received,
                        date_reported,
                        "48",
                        "senate",
                        source_document_id,
                        f"cdap:{record['cdap_id']}:interest:{record['interest_id']}",
                        json.dumps(record.get("original", {}), sort_keys=True),
                        _senate_interest_extraction_confidence(record),
                        as_jsonb(record),
                    ),
                )
            row_count += 1

    conn.commit()
    return {
        "senate_interest_records": row_count,
        "skipped_unmatched_people": skipped_unmatched,
        "unmatched_people": sorted(unmatched_names),
    }


def _delete_stale_influence_events(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM influence_event
            WHERE metadata->>'derived_loader' = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM claim_evidence
                  WHERE claim_evidence.influence_event_id = influence_event.id
              )
            """,
            (INFLUENCE_EVENT_LOADER_NAME,),
        )


def _upsert_influence_event(conn, event: dict[str, Any]) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO influence_event (
                external_key, event_family, event_type, event_subtype,
                source_entity_id, source_raw_name, recipient_entity_id,
                recipient_person_id, recipient_party_id, recipient_raw_name,
                jurisdiction_id, money_flow_id, gift_interest_id, amount,
                currency, amount_status, event_date, reporting_period,
                date_reported, chamber, disclosure_system, disclosure_threshold,
                evidence_status, extraction_method, review_status, description,
                source_document_id, source_ref, original_text, missing_data_flags,
                metadata
            )
            VALUES (
                %(external_key)s, %(event_family)s, %(event_type)s,
                %(event_subtype)s, %(source_entity_id)s, %(source_raw_name)s,
                %(recipient_entity_id)s, %(recipient_person_id)s,
                %(recipient_party_id)s, %(recipient_raw_name)s,
                %(jurisdiction_id)s, %(money_flow_id)s, %(gift_interest_id)s,
                %(amount)s, %(currency)s, %(amount_status)s, %(event_date)s,
                %(reporting_period)s, %(date_reported)s, %(chamber)s,
                %(disclosure_system)s, %(disclosure_threshold)s,
                %(evidence_status)s, %(extraction_method)s, %(review_status)s,
                %(description)s, %(source_document_id)s, %(source_ref)s,
                %(original_text)s, %(missing_data_flags)s, %(metadata)s
            )
            ON CONFLICT (external_key) DO UPDATE SET
                event_family = EXCLUDED.event_family,
                event_type = EXCLUDED.event_type,
                event_subtype = EXCLUDED.event_subtype,
                source_entity_id = EXCLUDED.source_entity_id,
                source_raw_name = EXCLUDED.source_raw_name,
                recipient_entity_id = EXCLUDED.recipient_entity_id,
                recipient_person_id = EXCLUDED.recipient_person_id,
                recipient_party_id = EXCLUDED.recipient_party_id,
                recipient_raw_name = EXCLUDED.recipient_raw_name,
                jurisdiction_id = EXCLUDED.jurisdiction_id,
                money_flow_id = EXCLUDED.money_flow_id,
                gift_interest_id = EXCLUDED.gift_interest_id,
                amount = EXCLUDED.amount,
                currency = EXCLUDED.currency,
                amount_status = EXCLUDED.amount_status,
                event_date = EXCLUDED.event_date,
                reporting_period = EXCLUDED.reporting_period,
                date_reported = EXCLUDED.date_reported,
                chamber = EXCLUDED.chamber,
                disclosure_system = EXCLUDED.disclosure_system,
                disclosure_threshold = EXCLUDED.disclosure_threshold,
                evidence_status = EXCLUDED.evidence_status,
                extraction_method = EXCLUDED.extraction_method,
                review_status = CASE
                    WHEN influence_event.metadata->>'manual_review_status'
                         IN ('accepted', 'rejected', 'revised')
                    THEN influence_event.review_status
                    ELSE EXCLUDED.review_status
                END,
                description = EXCLUDED.description,
                source_document_id = EXCLUDED.source_document_id,
                source_ref = EXCLUDED.source_ref,
                original_text = EXCLUDED.original_text,
                missing_data_flags = EXCLUDED.missing_data_flags,
                metadata = EXCLUDED.metadata || jsonb_strip_nulls(
                    jsonb_build_object(
                        'manual_review_status',
                        influence_event.metadata->>'manual_review_status',
                        'last_manual_review_decision_id',
                        influence_event.metadata->>'last_manual_review_decision_id',
                        'last_manual_review_decision_key',
                        influence_event.metadata->>'last_manual_review_decision_key',
                        'last_manual_review_decision',
                        influence_event.metadata->>'last_manual_review_decision',
                        'last_manual_review_reviewer',
                        influence_event.metadata->>'last_manual_review_reviewer',
                        'last_manual_reviewed_at',
                        influence_event.metadata->>'last_manual_reviewed_at'
                    )
                )
            """,
            event,
        )


def load_influence_events(conn) -> dict[str, Any]:
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "CWLTH")
    _delete_stale_influence_events(conn)

    money_count = 0
    interest_count = 0
    family_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()
    review_counts: Counter[str] = Counter()

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id, external_key, source_entity_id, source_raw_name,
                recipient_entity_id, recipient_person_id, recipient_party_id,
                recipient_raw_name, amount, currency, financial_year,
                date_received, date_reported, return_type, receipt_type,
                disclosure_category, jurisdiction_id, source_document_id,
                source_row_ref, original_text, confidence, metadata
            FROM money_flow
            """
        )
        money_rows = cur.fetchall()

    for row in money_rows:
        (
            money_flow_id,
            external_key,
            source_entity_id,
            source_raw_name,
            recipient_entity_id,
            recipient_person_id,
            recipient_party_id,
            recipient_raw_name,
            amount,
            currency,
            financial_year,
            date_received,
            date_reported,
            return_type,
            receipt_type,
            disclosure_category,
            row_jurisdiction_id,
            source_document_id,
            source_row_ref,
            original_text,
            confidence,
            metadata,
        ) = row
        base_metadata = metadata or {}
        event_type = classify_money_event_type(disclosure_category or "", receipt_type or "")
        campaign_support_record = is_campaign_support_money_flow(base_metadata)
        if campaign_support_record:
            event_family = "campaign_support"
            event_type = campaign_support_event_type(base_metadata, event_type)
        else:
            event_family = "benefit" if event_type == "discretionary_benefit" else "money"
        attribution = (
            campaign_support_attribution(base_metadata) if campaign_support_record else None
        )
        public_amount_counting_role = base_metadata.get("public_amount_counting_role")
        duplicate_observation = public_amount_counting_role == "duplicate_observation"
        campaign_expenditure = event_type == "campaign_expenditure"
        flags = missing_money_flags(
            source_raw_name=source_raw_name or "",
            recipient_raw_name=recipient_raw_name or "",
            amount=amount,
            date_received=date_received,
        )
        if duplicate_observation:
            flags.append("duplicate_disclosure_observation_not_counted_in_reported_total")
        if campaign_support_record:
            flags.append("campaign_support_not_personal_receipt")
            if amount is not None:
                flags.append("campaign_support_amount_not_direct_personal_receipt")
            if attribution and attribution.get("tier") == "candidate_nil_return_with_party_branch_context":
                flags.append("candidate_nil_return_with_party_branch_context")
        elif campaign_expenditure:
            flags.append("campaign_expenditure_not_counted_in_reported_total")
        description_amount = f"{amount} {currency}" if amount is not None else "amount not disclosed"
        if campaign_support_record:
            context = (
                base_metadata.get("candidate_context")
                if isinstance(base_metadata.get("candidate_context"), dict)
                else {}
            )
            electorate_label = " ".join(
                part
                for part in (
                    context.get("electorate_name") if isinstance(context, dict) else "",
                    context.get("electorate_state") if isinstance(context, dict) else "",
                )
                if part
            )
            context_label = f" ({electorate_label})" if electorate_label else ""
            if event_type == "candidate_or_senate_group_nil_return":
                description = (
                    f"AEC records a nil election return for {recipient_raw_name or 'Unknown'}"
                    f"{context_label}; this is campaign-disclosure context, not a personal receipt."
                )
            elif "expenditure" in event_type or event_type == "observed_media_ad_activity":
                description = (
                    f"{source_raw_name or 'Unknown'} campaign-support expenditure connected to "
                    f"{recipient_raw_name or 'campaign activity'}{context_label}: {description_amount}; "
                    "not a personal receipt."
                )
            else:
                description = (
                    f"{source_raw_name or 'Unknown'} to {recipient_raw_name or 'Unknown'}"
                    f"{context_label}: {description_amount}; campaign-support record, not a "
                    "personal receipt."
                )
        else:
            description = (
                f"{source_raw_name or 'Unknown'} to {recipient_raw_name or 'Unknown'}: "
                f"{description_amount}"
            )
        extraction_method = base_metadata.get("normalizer_name") or "aec_annual_money_flow_normalizer"
        disclosure_system = base_metadata.get("disclosure_system") or "aec_financial_disclosure"
        if duplicate_observation:
            amount_status = "not_applicable"
        elif event_type in {
            "candidate_or_senate_group_nil_return",
            "candidate_or_senate_group_return_summary",
        }:
            amount_status = "not_applicable"
        elif amount is not None and campaign_support_record:
            amount_status = "reported"
        elif amount is not None and campaign_expenditure:
            amount_status = "not_applicable"
        elif amount is not None:
            amount_status = "reported"
        else:
            amount_status = "unknown"
        event = {
            "external_key": f"money_flow:{external_key or money_flow_id}",
            "event_family": event_family,
            "event_type": event_type,
            "event_subtype": slugify(disclosure_category or receipt_type or "", "unspecified"),
            "source_entity_id": source_entity_id,
            "source_raw_name": source_raw_name,
            "recipient_entity_id": recipient_entity_id,
            "recipient_person_id": recipient_person_id,
            "recipient_party_id": recipient_party_id,
            "recipient_raw_name": recipient_raw_name,
            "jurisdiction_id": row_jurisdiction_id or jurisdiction_id,
            "money_flow_id": money_flow_id,
            "gift_interest_id": None,
            "amount": amount,
            "currency": currency or "AUD",
            "amount_status": amount_status,
            "event_date": date_received,
            "reporting_period": financial_year or base_metadata.get("event_name"),
            "date_reported": date_reported,
            "chamber": None,
            "disclosure_system": disclosure_system,
            "disclosure_threshold": "AEC financial disclosure threshold for the reporting period.",
            "evidence_status": "official_record_parsed",
            "extraction_method": extraction_method,
            "review_status": "not_required",
            "description": description,
            "source_document_id": source_document_id,
            "source_ref": source_row_ref,
            "original_text": original_text,
            "missing_data_flags": as_jsonb(flags),
            "metadata": as_jsonb(
                {
                    "derived_loader": INFLUENCE_EVENT_LOADER_NAME,
                    "base_table": "money_flow",
                    "base_id": money_flow_id,
                    "return_type": return_type,
                    "receipt_type": receipt_type,
                    "disclosure_category": disclosure_category,
                    "source_confidence": confidence,
                    "campaign_support_attribution": attribution,
                    "base_metadata": base_metadata,
                }
            ),
        }
        _upsert_influence_event(conn, event)
        money_count += 1
        family_counts[event["event_family"]] += 1
        type_counts[event["event_type"]] += 1
        review_counts[event["review_status"]] += 1

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                id, external_key, person_id, source_entity_id, source_raw_name,
                interest_category, description, estimated_value, currency,
                date_received, date_reported, parliament_number, chamber,
                source_document_id, source_page_ref, original_text,
                extraction_confidence, metadata
            FROM gift_interest
            """
        )
        interest_rows = cur.fetchall()

    for row in interest_rows:
        (
            gift_interest_id,
            external_key,
            person_id,
            source_entity_id,
            source_raw_name,
            interest_category,
            description,
            estimated_value,
            currency,
            date_received,
            date_reported,
            parliament_number,
            chamber,
            source_document_id,
            source_page_ref,
            original_text,
            extraction_confidence,
            metadata,
        ) = row
        event_family, event_type, event_subtype = classify_interest_event(
            interest_category or "",
            description or "",
        )
        extraction_method = extraction_confidence or "unknown"
        flags = missing_interest_flags(
            source_raw_name=source_raw_name or "",
            amount=estimated_value,
            date_received=date_received,
            date_reported=date_reported,
            extraction_method=extraction_method,
        )
        review_status = "needs_review" if "heuristic" in extraction_method else "not_required"
        event = {
            "external_key": f"gift_interest:{external_key or gift_interest_id}",
            "event_family": event_family,
            "event_type": event_type,
            "event_subtype": event_subtype,
            "source_entity_id": source_entity_id,
            "source_raw_name": source_raw_name,
            "recipient_entity_id": None,
            "recipient_person_id": person_id,
            "recipient_party_id": None,
            "recipient_raw_name": None,
            "jurisdiction_id": jurisdiction_id,
            "money_flow_id": None,
            "gift_interest_id": gift_interest_id,
            "amount": estimated_value,
            "currency": currency or "AUD",
            "amount_status": "reported" if estimated_value is not None else "not_disclosed",
            "event_date": date_received,
            "reporting_period": parliament_number,
            "date_reported": date_reported,
            "chamber": chamber,
            "disclosure_system": "aph_register_of_interests",
            "disclosure_threshold": "APH register disclosure rules vary by chamber and category.",
            "evidence_status": "official_record_parsed",
            "extraction_method": extraction_method,
            "review_status": review_status,
            "description": description or interest_category or "Declared interest",
            "source_document_id": source_document_id,
            "source_ref": source_page_ref,
            "original_text": original_text,
            "missing_data_flags": as_jsonb(flags),
            "metadata": as_jsonb(
                {
                    "derived_loader": INFLUENCE_EVENT_LOADER_NAME,
                    "base_table": "gift_interest",
                    "base_id": gift_interest_id,
                    "interest_category": interest_category,
                    "parliament_number": parliament_number,
                    "base_metadata": metadata or {},
                }
            ),
        }
        _upsert_influence_event(conn, event)
        interest_count += 1
        family_counts[event["event_family"]] += 1
        type_counts[event["event_type"]] += 1
        review_counts[event["review_status"]] += 1

    conn.commit()
    return {
        "influence_events": money_count + interest_count,
        "money_flow_events": money_count,
        "interest_events": interest_count,
        "event_family_counts": dict(sorted(family_counts.items())),
        "event_type_counts": dict(sorted(type_counts.items())),
        "review_status_counts": dict(sorted(review_counts.items())),
    }


def _entity_id_by_normalized_name(conn, normalized_name: str) -> int | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM entity
            WHERE normalized_name = %s
            ORDER BY CASE WHEN entity_type = 'unknown' THEN 1 ELSE 0 END, id
            LIMIT 1
            """,
            (normalized_name,),
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else None


def _update_entity_type_from_classification(conn, entity_id: int, entity_type: str) -> None:
    if not entity_type or entity_type == "unknown":
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entity
            SET entity_type = %s
            WHERE id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM entity duplicate
                  WHERE duplicate.normalized_name = entity.normalized_name
                    AND duplicate.entity_type = %s
                    AND duplicate.id <> entity.id
              )
            """,
            (entity_type, entity_id, entity_type),
        )


def _update_entity_type_from_official(conn, entity_id: int, entity_type: str) -> None:
    if entity_type in {"", "unknown", "individual"}:
        return
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE entity
            SET entity_type = %s
            WHERE id = %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM entity duplicate
                  WHERE duplicate.normalized_name = entity.normalized_name
                    AND duplicate.entity_type = %s
                    AND duplicate.id <> entity.id
              )
            """,
            (entity_type, entity_id, entity_type),
        )


def load_entity_classifications(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        path = jsonl_path or latest_entity_classifications_jsonl()
    except FileNotFoundError:
        return {
            "entity_classifications": 0,
            "skipped_entities": 0,
            "skipped_reason": "no_entity_classification_artifact",
        }

    code_ids = {
        sector["code"]: get_or_create_industry_code(
            conn,
            "public_interest_sector",
            sector["code"],
            sector["label"],
        )
        for sector in PUBLIC_INTEREST_SECTORS
    }

    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM entity_industry_classification
            WHERE method = 'rule_based'
              AND metadata->>'classifier_name' = %s
            """,
            (CLASSIFIER_NAME,),
        )

    inserted = 0
    skipped = 0
    sector_counts: Counter[str] = Counter()
    entity_type_counts: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            entity_id = _entity_id_by_normalized_name(conn, record["normalized_name"])
            if entity_id is None:
                skipped += 1
                continue

            industry_code_id = code_ids.get(record["public_sector"])
            metadata = {
                "classifier_name": record["classifier_name"],
                "matched_rule_id": record["matched_rule_id"],
                "raw_name_variants": record["raw_name_variants"],
                "source_contexts": record["source_contexts"],
                "money_flow_source_count": record["money_flow_source_count"],
                "money_flow_recipient_count": record["money_flow_recipient_count"],
                "gift_interest_source_count": record["gift_interest_source_count"],
                "total_source_amount_aud": record["total_source_amount_aud"],
                "total_recipient_amount_aud": record["total_recipient_amount_aud"],
                "sample_source_ids": record["sample_source_ids"],
                "review_recommended": record["review_recommended"],
                "classification_artifact_path": str(path),
            }
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO entity_industry_classification (
                        entity_id, industry_code_id, public_sector, method, confidence,
                        evidence_note, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        entity_id,
                        industry_code_id,
                        record["public_sector"],
                        record["method"],
                        record["confidence"],
                        record["evidence_note"],
                        as_jsonb(metadata),
                    ),
                )
            inserted += 1
            sector_counts[record["public_sector"]] += 1
            entity_type_counts[record["entity_type"]] += 1
            confidence_counts[record["confidence"]] += 1

    conn.commit()
    return {
        "entity_classifications": inserted,
        "skipped_entities": skipped,
        "public_sector_counts": dict(sorted(sector_counts.items())),
        "entity_type_counts": dict(sorted(entity_type_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
    }


def load_anzsic_sections(conn) -> dict[str, int]:
    inserted = 0
    for section in ANZSIC_SECTIONS:
        get_or_create_industry_code(
            conn,
            "ANZSIC_2006_section",
            section["code"],
            section["label"],
        )
        inserted += 1
    conn.commit()
    return {"anzsic_sections": inserted}


def _public_interest_code_ids(conn) -> dict[str, int]:
    return {
        sector["code"]: get_or_create_industry_code(
            conn,
            "public_interest_sector",
            sector["code"],
            sector["label"],
        )
        for sector in PUBLIC_INTEREST_SECTORS
    }


def _insert_official_identifier_observation(
    conn,
    record: dict[str, Any],
    source_document_id: int | None,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO official_identifier_observation (
                stable_key, source_document_id, source_id, source_record_type,
                external_id, display_name, normalized_name, entity_type, public_sector,
                confidence, status, source_updated_at, evidence_note, identifiers,
                aliases, raw_record, metadata
            )
            VALUES (
                %(stable_key)s, %(source_document_id)s, %(source_id)s,
                %(source_record_type)s, %(external_id)s, %(display_name)s,
                %(normalized_name)s, %(entity_type)s, %(public_sector)s,
                %(confidence)s, %(status)s, %(source_updated_at)s, %(evidence_note)s,
                %(identifiers)s, %(aliases)s, %(raw_record)s, %(metadata)s
            )
            ON CONFLICT (stable_key) DO UPDATE SET
                source_document_id = EXCLUDED.source_document_id,
                external_id = EXCLUDED.external_id,
                display_name = EXCLUDED.display_name,
                normalized_name = EXCLUDED.normalized_name,
                entity_type = EXCLUDED.entity_type,
                public_sector = EXCLUDED.public_sector,
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status,
                source_updated_at = EXCLUDED.source_updated_at,
                evidence_note = EXCLUDED.evidence_note,
                identifiers = EXCLUDED.identifiers,
                aliases = EXCLUDED.aliases,
                raw_record = EXCLUDED.raw_record,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            {
                "stable_key": record["stable_key"],
                "source_document_id": source_document_id,
                "source_id": record["source_id"],
                "source_record_type": record["source_record_type"],
                "external_id": record.get("external_id") or None,
                "display_name": record["display_name"],
                "normalized_name": record["normalized_name"],
                "entity_type": record.get("entity_type") or "unknown",
                "public_sector": record.get("public_sector") or "unknown",
                "confidence": record.get("confidence") or "unresolved",
                "status": record.get("status") or None,
                "source_updated_at": parse_datetime(record.get("source_updated_at", "")),
                "evidence_note": record.get("evidence_note") or None,
                "identifiers": as_jsonb(record.get("identifiers") or []),
                "aliases": as_jsonb(record.get("aliases") or []),
                "raw_record": as_jsonb(record.get("raw_record") or {}),
                "metadata": as_jsonb(
                    {
                        **(record.get("metadata") or {}),
                        "official_parser_name": record.get("parser_name"),
                        "schema_version": record.get("schema_version"),
                        "official_classification": record.get("official_classification"),
                    }
                ),
            },
        )
        row = cur.fetchone()
    return int(row[0])


def _entity_ids_by_normalized_name(conn, normalized_name: str) -> list[int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id
            FROM entity
            WHERE normalized_name = %s
            ORDER BY id
            """,
            (normalized_name,),
        )
        return [int(row[0]) for row in cur.fetchall()]


def _entity_ids_by_identifiers(conn, identifiers: list[dict[str, str]]) -> dict[int, list[str]]:
    if not identifiers:
        return {}
    matches: dict[int, list[str]] = {}
    with conn.cursor() as cur:
        for identifier in identifiers:
            cur.execute(
                """
                SELECT entity_id
                FROM entity_identifier
                WHERE identifier_type = %s
                  AND identifier_value = %s
                """,
                (identifier["identifier_type"], identifier["identifier_value"]),
            )
            for row in cur.fetchall():
                entity_id = int(row[0])
                matches.setdefault(entity_id, []).append(
                    f"{identifier['identifier_type']}:{identifier['identifier_value']}"
                )
    return matches


def _insert_match_candidate(
    conn,
    *,
    entity_id: int,
    observation_id: int,
    match_method: str,
    confidence: str,
    status: str,
    evidence_note: str,
    metadata: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_match_candidate (
                entity_id, observation_id, match_method, confidence, status,
                score, evidence_note, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (entity_id, observation_id, match_method) DO UPDATE SET
                confidence = EXCLUDED.confidence,
                status = EXCLUDED.status,
                score = EXCLUDED.score,
                evidence_note = EXCLUDED.evidence_note,
                metadata = EXCLUDED.metadata
            """,
            (
                entity_id,
                observation_id,
                match_method,
                confidence,
                status,
                Decimal("100.00") if match_method == "exact_normalized_name" else None,
                evidence_note,
                as_jsonb(metadata),
            ),
        )


def _insert_entity_identifier(
    conn,
    *,
    entity_id: int,
    identifier: dict[str, str],
    source_document_id: int | None,
    record: dict[str, Any],
) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_identifier (
                entity_id, identifier_type, identifier_value, source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (identifier_type, identifier_value) DO NOTHING
            """,
            (
                entity_id,
                identifier["identifier_type"],
                identifier["identifier_value"],
                source_document_id,
                as_jsonb(
                    {
                        "source_id": record["source_id"],
                        "source_record_type": record["source_record_type"],
                        "official_parser_name": record["parser_name"],
                        "stable_key": record["stable_key"],
                    }
                ),
            ),
        )
        return cur.rowcount == 1


def _insert_entity_aliases(
    conn,
    *,
    entity_id: int,
    aliases: list[str],
    source_document_id: int | None,
    record: dict[str, Any],
) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for alias in aliases:
            normalized_alias = normalize_name(alias)
            if not normalized_alias:
                continue
            cur.execute(
                """
                INSERT INTO entity_alias (
                    entity_id, alias, normalized_alias, source_document_id, metadata
                )
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (entity_id, normalized_alias) DO NOTHING
                """,
                (
                    entity_id,
                    alias,
                    normalized_alias,
                    source_document_id,
                    as_jsonb(
                        {
                            "source_id": record["source_id"],
                            "source_record_type": record["source_record_type"],
                            "official_parser_name": record["parser_name"],
                            "stable_key": record["stable_key"],
                        }
                    ),
                ),
            )
            if cur.rowcount == 1:
                inserted += 1
    return inserted


def _insert_official_classification(
    conn,
    *,
    entity_id: int,
    industry_code_id: int | None,
    source_document_id: int | None,
    record: dict[str, Any],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO entity_industry_classification (
                entity_id, industry_code_id, public_sector, method, confidence,
                evidence_note, source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                entity_id,
                industry_code_id,
                record["public_sector"],
                "official",
                record["confidence"],
                record.get("evidence_note") or record.get("official_classification"),
                source_document_id,
                as_jsonb(
                    {
                        "source_id": record["source_id"],
                        "source_record_type": record["source_record_type"],
                        "official_parser_name": record["parser_name"],
                        "stable_key": record["stable_key"],
                        "official_classification": record.get("official_classification"),
                    }
                ),
            ),
        )


def load_official_identifiers(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    try:
        paths = [jsonl_path] if jsonl_path is not None else latest_official_identifier_jsonl_paths()
    except FileNotFoundError:
        return {
            "official_identifier_observations": 0,
            "skipped_reason": "no_official_identifier_artifact",
        }

    records: list[dict[str, Any]] = []
    loaded_source_ids: set[str] = set()
    incremental_record_types = {"abn_web_service_entity"}
    snapshot_scope: set[tuple[str, str]] = set()
    incremental_stable_keys: set[str] = set()
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                record = json.loads(line)
                records.append(record)
                loaded_source_ids.add(record["source_id"])
                source_record_type = record["source_record_type"]
                if source_record_type in incremental_record_types:
                    incremental_stable_keys.add(record["stable_key"])
                else:
                    snapshot_scope.add((record["source_id"], source_record_type))

    load_anzsic_sections(conn)
    public_interest_code_ids = _public_interest_code_ids(conn)
    source_doc_cache: dict[str, int] = {}
    with conn.cursor() as cur:
        for source_id, source_record_type in sorted(snapshot_scope):
            cur.execute(
                """
                DELETE FROM entity_industry_classification
                WHERE method = 'official'
                  AND metadata->>'official_parser_name' = %s
                  AND metadata->>'source_id' = %s
                  AND metadata->>'source_record_type' = %s
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM entity_identifier
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'source_id' = %s
                  AND metadata->>'source_record_type' = %s
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM entity_alias
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'source_id' = %s
                  AND metadata->>'source_record_type' = %s
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM entity_match_candidate
                WHERE observation_id IN (
                    SELECT id
                    FROM official_identifier_observation
                    WHERE source_id = %s
                      AND source_record_type = %s
                )
                """,
                (source_id, source_record_type),
            )
            cur.execute(
                """
                DELETE FROM official_identifier_observation
                WHERE source_id = %s
                  AND source_record_type = %s
                """,
                (source_id, source_record_type),
            )
        if incremental_stable_keys:
            stable_keys = sorted(incremental_stable_keys)
            cur.execute(
                """
                DELETE FROM entity_industry_classification
                WHERE method = 'official'
                  AND metadata->>'official_parser_name' = %s
                  AND metadata->>'stable_key' = ANY(%s)
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, stable_keys),
            )
            cur.execute(
                """
                DELETE FROM entity_identifier
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'stable_key' = ANY(%s)
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, stable_keys),
            )
            cur.execute(
                """
                DELETE FROM entity_alias
                WHERE metadata->>'official_parser_name' = %s
                  AND metadata->>'stable_key' = ANY(%s)
                """,
                (OFFICIAL_IDENTIFIER_PARSER_NAME, stable_keys),
            )
            cur.execute(
                """
                DELETE FROM entity_match_candidate
                WHERE observation_id IN (
                    SELECT id
                    FROM official_identifier_observation
                    WHERE stable_key = ANY(%s)
                )
                """,
                (stable_keys,),
            )

    observed = 0
    auto_accepted = 0
    needs_review = 0
    observations_without_exact_entity_match = 0
    identifiers_inserted = 0
    aliases_inserted = 0
    official_classifications = 0
    skipped_person_matches = 0
    source_counts: Counter[str] = Counter()
    for record in records:
            metadata_path = record.get("source_metadata_path")
            source_document_id = None
            if metadata_path:
                if metadata_path not in source_doc_cache:
                    source_doc_cache[metadata_path] = upsert_source_document(
                        conn, Path(metadata_path)
                    )
                source_document_id = source_doc_cache[metadata_path]

            observation_id = _insert_official_identifier_observation(
                conn,
                record,
                source_document_id,
            )
            observed += 1
            source_counts[record["source_record_type"]] += 1

            if record.get("source_record_type") == "lobbyist_person":
                skipped_person_matches += 1
                continue

            identifiers = record.get("identifiers") or []
            identifier_entity_matches = _entity_ids_by_identifiers(conn, identifiers)
            if len(identifier_entity_matches) > 1:
                needs_review += len(identifier_entity_matches)
                for candidate_entity_id, matched_identifiers in identifier_entity_matches.items():
                    _insert_match_candidate(
                        conn,
                        entity_id=candidate_entity_id,
                        observation_id=observation_id,
                        match_method="exact_identifier_conflict",
                        confidence="unresolved",
                        status="needs_review",
                        evidence_note="Official identifiers on this record point to multiple entities.",
                        metadata={"matched_identifiers": matched_identifiers},
                    )
                continue

            if len(identifier_entity_matches) == 1:
                entity_id, matched_identifiers = next(iter(identifier_entity_matches.items()))
                _insert_match_candidate(
                    conn,
                    entity_id=entity_id,
                    observation_id=observation_id,
                    match_method="exact_identifier",
                    confidence="exact_identifier",
                    status="auto_accepted",
                    evidence_note="Official identifier already attached to this entity.",
                    metadata={"matched_identifiers": matched_identifiers},
                )
                auto_accepted += 1
                _update_entity_type_from_official(conn, entity_id, record.get("entity_type", ""))
                for identifier in identifiers:
                    if _insert_entity_identifier(
                        conn,
                        entity_id=entity_id,
                        identifier=identifier,
                        source_document_id=source_document_id,
                        record=record,
                    ):
                        identifiers_inserted += 1
                aliases_inserted += _insert_entity_aliases(
                    conn,
                    entity_id=entity_id,
                    aliases=record.get("aliases") or [],
                    source_document_id=source_document_id,
                    record=record,
                )
                if record.get("public_sector") and record["public_sector"] != "unknown":
                    _insert_official_classification(
                        conn,
                        entity_id=entity_id,
                        industry_code_id=public_interest_code_ids.get(record["public_sector"]),
                        source_document_id=source_document_id,
                        record={**record, "confidence": "exact_identifier"},
                    )
                    official_classifications += 1
                continue

            candidate_entity_ids = _entity_ids_by_normalized_name(conn, record["normalized_name"])
            if len(candidate_entity_ids) != 1:
                if candidate_entity_ids:
                    needs_review += len(candidate_entity_ids)
                else:
                    observations_without_exact_entity_match += 1
                for candidate_entity_id in candidate_entity_ids:
                    _insert_match_candidate(
                        conn,
                        entity_id=candidate_entity_id,
                        observation_id=observation_id,
                        match_method="exact_normalized_name",
                        confidence="exact_name_context",
                        status="needs_review",
                        evidence_note="Exact name match requires review due missing/ambiguous match.",
                        metadata={"candidate_count": len(candidate_entity_ids)},
                    )
                continue

            entity_id = candidate_entity_ids[0]
            needs_review += 1
            _insert_match_candidate(
                conn,
                entity_id=entity_id,
                observation_id=observation_id,
                match_method="exact_normalized_name",
                confidence="exact_name_context",
                status="needs_review",
                evidence_note="Exact name match only; manual review required before attaching identifiers.",
                metadata={"candidate_count": len(candidate_entity_ids)},
            )

    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*)
            FROM official_identifier_observation
            WHERE source_id = ANY(%s)
            """,
            (sorted(loaded_source_ids),),
        )
        unique_observations = int(cur.fetchone()[0])
        cur.execute(
            """
            SELECT entity_match_candidate.status, count(*)
            FROM entity_match_candidate
            JOIN official_identifier_observation
              ON official_identifier_observation.id = entity_match_candidate.observation_id
            WHERE official_identifier_observation.source_id = ANY(%s)
            GROUP BY entity_match_candidate.status
            """,
            (sorted(loaded_source_ids),),
        )
        match_candidate_status_counts = {row[0]: int(row[1]) for row in cur.fetchall()}
    return {
        "records_processed": observed,
        "official_identifier_observations": unique_observations,
        "auto_accepted_matches": match_candidate_status_counts.get("auto_accepted", 0),
        "needs_review_matches": match_candidate_status_counts.get("needs_review", 0),
        "match_candidate_status_counts": match_candidate_status_counts,
        "match_candidate_attempts": {
            "auto_accepted": auto_accepted,
            "needs_review": needs_review,
        },
        "observations_without_exact_entity_match": observations_without_exact_entity_match,
        "identifiers_inserted": identifiers_inserted,
        "aliases_inserted": aliases_inserted,
        "official_classifications": official_classifications,
        "skipped_person_matches": skipped_person_matches,
        "source_record_type_counts": dict(sorted(source_counts.items())),
        "jsonl_paths": [str(path) for path in paths],
    }


def _source_metadata_path_from_boundary_geojson(geojson: dict[str, Any]) -> Path:
    for feature in geojson.get("features", []):
        path = feature.get("properties", {}).get("source_metadata_path")
        if path:
            return Path(path)
    raise RuntimeError("AEC boundary GeoJSON is missing source_metadata_path.")


def _house_electorates_without_boundary(conn, boundary_set: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT electorate.name
            FROM office_term
            JOIN electorate ON electorate.id = office_term.electorate_id
            LEFT JOIN electorate_boundary boundary
              ON boundary.electorate_id = electorate.id
             AND boundary.boundary_set = %s
            WHERE office_term.chamber = 'house'
              AND office_term.term_end IS NULL
              AND boundary.id IS NULL
            ORDER BY electorate.name
            """,
            (boundary_set,),
        )
        return [row[0] for row in cur.fetchall()]


def _boundary_names_without_current_house_office(conn, boundary_set: str) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT electorate.name
            FROM electorate_boundary boundary
            JOIN electorate ON electorate.id = boundary.electorate_id
            LEFT JOIN office_term
              ON office_term.electorate_id = electorate.id
             AND office_term.chamber = 'house'
             AND office_term.term_end IS NULL
            WHERE boundary.boundary_set = %s
              AND office_term.id IS NULL
            ORDER BY electorate.name
            """,
            (boundary_set,),
        )
        return [row[0] for row in cur.fetchall()]


def _delete_stale_boundary_only_electorates(conn, *, jurisdiction_id: int, boundary_set: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM electorate
            WHERE jurisdiction_id = %s
              AND chamber = 'house'
              AND metadata->>'boundary_source' = %s
              AND NOT EXISTS (
                  SELECT 1 FROM office_term WHERE office_term.electorate_id = electorate.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM electorate_boundary
                  WHERE electorate_boundary.electorate_id = electorate.id
              )
            """,
            (jurisdiction_id, boundary_set),
        )
        return cur.rowcount


def _source_metadata_path_from_land_mask_geojson(geojson: dict[str, Any]) -> Path:
    for feature in geojson.get("features", []):
        metadata_path = feature.get("properties", {}).get("source_metadata_path")
        if metadata_path:
            return Path(metadata_path)
    raise RuntimeError("Land-mask GeoJSON is missing source_metadata_path in feature properties.")


def load_display_land_mask(
    conn,
    *,
    country_name: str = "Australia",
    geojson_path: Path | None = None,
) -> dict[str, Any]:
    if country_name.casefold() == "australia":
        return load_aims_display_land_mask(
            conn,
            country_name="Australia",
            geojson_path=geojson_path,
        )

    geojson_path = geojson_path or latest_country_land_mask_geojson(country_name=country_name)
    if geojson_path is None:
        extract_natural_earth_country_land_mask(country_name=country_name)
        geojson_path = latest_country_land_mask_geojson(country_name=country_name)
    if geojson_path is None:
        raise FileNotFoundError(f"No processed Natural Earth land mask found for {country_name}.")
    physical_geojson_path = latest_physical_land_mask_geojson(country_name=country_name)
    if physical_geojson_path is None:
        extract_natural_earth_physical_land_mask(country_name=country_name)
        physical_geojson_path = latest_physical_land_mask_geojson(country_name=country_name)
    if physical_geojson_path is None:
        raise FileNotFoundError(
            f"No processed Natural Earth physical land mask found for {country_name}."
        )

    admin_geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    physical_geojson = json.loads(physical_geojson_path.read_text(encoding="utf-8"))
    admin_source_metadata_path = _source_metadata_path_from_land_mask_geojson(admin_geojson)
    physical_source_metadata_path = _source_metadata_path_from_land_mask_geojson(physical_geojson)
    admin_source_document_id = upsert_source_document(conn, admin_source_metadata_path)
    physical_source_document_id = upsert_source_document(conn, physical_source_metadata_path)
    source_key = f"natural_earth_admin0_physical_land_10m:{normalize_name(country_name)}"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO display_land_mask (
                source_key, country_name, geometry_role, geom, source_document_id, metadata
            )
            WITH admin_features AS (
                SELECT value AS feature
                FROM jsonb_array_elements(%s::jsonb->'features')
            ),
            admin_geoms AS (
                SELECT ST_MakeValid(
                    ST_SetSRID(ST_GeomFromGeoJSON(feature->>'geometry'), 4326)
                ) AS geom
                FROM admin_features
            ),
            admin_unioned AS (
                SELECT ST_MakeValid(ST_UnaryUnion(ST_Collect(geom))) AS geom
                FROM admin_geoms
            ),
            physical_features AS (
                SELECT value AS feature
                FROM jsonb_array_elements(%s::jsonb->'features')
            ),
            physical_geoms AS (
                SELECT ST_MakeValid(
                    ST_SetSRID(ST_GeomFromGeoJSON(feature->>'geometry'), 4326)
                ) AS geom
                FROM physical_features
            ),
            physical_unioned AS (
                SELECT ST_MakeValid(ST_UnaryUnion(ST_Collect(geom))) AS geom
                FROM physical_geoms
            ),
            intersected AS (
                SELECT ST_Multi(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_Intersection(admin_unioned.geom, physical_unioned.geom)),
                        3
                    )
                ) AS geom
                FROM admin_unioned, physical_unioned
            )
            SELECT %s, %s, 'country_physical_land_display_mask', geom, %s, %s
            FROM intersected
            ON CONFLICT (source_key) DO UPDATE SET
                country_name = EXCLUDED.country_name,
                geometry_role = EXCLUDED.geometry_role,
                geom = EXCLUDED.geom,
                source_document_id = EXCLUDED.source_document_id,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (
                as_jsonb(admin_geojson),
                as_jsonb(physical_geojson),
                source_key,
                country_name,
                admin_source_document_id,
                as_jsonb(
                    {
                        "admin0_geojson_path": str(geojson_path.resolve()),
                        "physical_land_geojson_path": str(physical_geojson_path.resolve()),
                        "parser_name": LAND_MASK_PARSER_NAME,
                        "parser_version": LAND_MASK_PARSER_VERSION,
                        "admin0_source_metadata_path": str(admin_source_metadata_path.resolve()),
                        "physical_land_source_metadata_path": str(
                            physical_source_metadata_path.resolve()
                        ),
                        "physical_land_source_document_id": physical_source_document_id,
                        "mask_method": "postgis_intersection_admin0_with_physical_land",
                    }
                ),
            ),
        )
        land_mask_id = cur.fetchone()[0]
    conn.commit()
    return {
        "land_mask_id": land_mask_id,
        "source_key": source_key,
        "country_name": country_name,
        "geojson_path": str(geojson_path.resolve()),
        "physical_geojson_path": str(physical_geojson_path.resolve()),
        "source_document_id": admin_source_document_id,
        "physical_source_document_id": physical_source_document_id,
    }


def load_aims_display_land_mask(
    conn,
    *,
    country_name: str = "Australia",
    geojson_path: Path | None = None,
) -> dict[str, Any]:
    geojson_path = geojson_path or latest_aims_australian_coastline_land_mask_geojson(
        country_name=country_name
    )
    if geojson_path is None:
        extract_aims_australian_coastline_land_mask(country_name=country_name)
        geojson_path = latest_aims_australian_coastline_land_mask_geojson(
            country_name=country_name
        )
    if geojson_path is None:
        raise FileNotFoundError(f"No processed AIMS coastline land mask found for {country_name}.")

    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    summary_path = geojson_path.with_suffix(".summary.json")
    summary = {}
    if summary_path.exists():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    source_metadata_path = _source_metadata_path_from_land_mask_geojson(geojson)
    source_document_id = upsert_source_document(conn, source_metadata_path)
    source_key = f"{AIMS_COASTLINE_SOURCE_ID}:{normalize_name(country_name)}"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO display_land_mask (
                source_key, country_name, geometry_role, geom, source_document_id, metadata
            )
            WITH features AS (
                SELECT value AS feature
                FROM jsonb_array_elements(%s::jsonb->'features')
            ),
            geoms AS (
                SELECT ST_MakeValid(
                    ST_SetSRID(ST_GeomFromGeoJSON(feature->>'geometry'), 4326)
                ) AS geom
                FROM features
            ),
            unioned AS (
                SELECT ST_Multi(
                    ST_CollectionExtract(
                        ST_MakeValid(ST_UnaryUnion(ST_Collect(geom))),
                        3
                    )
                ) AS geom
                FROM geoms
            )
            SELECT %s, %s, 'country_high_resolution_land_display_mask', geom, %s, %s
            FROM unioned
            ON CONFLICT (source_key) DO UPDATE SET
                country_name = EXCLUDED.country_name,
                geometry_role = EXCLUDED.geometry_role,
                geom = EXCLUDED.geom,
                source_document_id = EXCLUDED.source_document_id,
                metadata = EXCLUDED.metadata
            RETURNING id
            """,
            (
                as_jsonb(geojson),
                source_key,
                country_name,
                source_document_id,
                as_jsonb(
                    {
                        "geojson_path": str(geojson_path.resolve()),
                        "summary_path": str(summary_path.resolve()) if summary_path.exists() else "",
                        "parser_name": AIMS_COASTLINE_PARSER_NAME,
                        "parser_version": AIMS_COASTLINE_PARSER_VERSION,
                        "source_metadata_path": str(source_metadata_path.resolve()),
                        "source_limitations": AIMS_COASTLINE_LIMITATIONS,
                        "licence_status": "not_specified_confirm_before_public_redistribution",
                        "extracted_component_sha256": summary.get(
                            "extracted_component_sha256"
                        ),
                        "mask_method": "postgis_union_aims_australian_coastline_50k_land_polygons",
                        "source_description": (
                            "AIMS/eAtlas/AODN Australian Coastline 50K 2024 simplified "
                            "land-area polygons from 2022-2024 Sentinel-2 imagery. "
                            "Display-only derivative; not used as a legal/electoral boundary."
                        ),
                    }
                ),
            ),
        )
        land_mask_id = cur.fetchone()[0]
    conn.commit()
    return {
        "land_mask_id": land_mask_id,
        "source_key": source_key,
        "country_name": country_name,
        "geojson_path": str(geojson_path.resolve()),
        "source_document_id": source_document_id,
    }


def load_electorate_boundary_display_geometries(
    conn,
    *,
    boundary_set: str = BOUNDARY_SET,
    country_name: str = "Australia",
    coastline_repair_buffer_meters: int = DEFAULT_COASTLINE_REPAIR_BUFFER_METERS,
) -> dict[str, Any]:
    if coastline_repair_buffer_meters < 0:
        raise ValueError("coastline_repair_buffer_meters must be non-negative.")
    if coastline_repair_buffer_meters > MAX_COASTLINE_REPAIR_BUFFER_METERS:
        raise ValueError(
            "coastline_repair_buffer_meters must be no greater than "
            f"{MAX_COASTLINE_REPAIR_BUFFER_METERS}."
        )
    land_summary = load_display_land_mask(conn, country_name=country_name)
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH target_boundaries AS (
                SELECT
                    boundary.id AS electorate_boundary_id,
                    boundary.geom AS source_geom
                FROM electorate_boundary boundary
                WHERE boundary.boundary_set = %s
            ),
            clipped AS (
                SELECT
                    target.electorate_boundary_id,
                    target.source_geom,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(ST_Intersection(target.source_geom, mask.geom)),
                            3
                        )
                    ) AS geom,
                    mask.source_document_id AS clip_source_document_id
                FROM target_boundaries target
                JOIN display_land_mask mask
                  ON mask.source_key = %s
            ),
            repaired AS (
                SELECT
                    electorate_boundary_id,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(
                                ST_Intersection(
                                    source_geom,
                                    ST_Transform(
                                        ST_Buffer(
                                            ST_Transform(geom, %s),
                                            %s,
                                            'quad_segs=2'
                                        ),
                                        4326
                                    )
                                )
                            ),
                            3
                        )
                    ) AS geom,
                    clip_source_document_id
                FROM clipped
                WHERE NOT ST_IsEmpty(geom)
            ),
            upserted AS (
                INSERT INTO electorate_boundary_display_geometry (
                    electorate_boundary_id,
                    geometry_role,
                    geom,
                    clip_source_document_id,
                    metadata
                )
                SELECT
                    electorate_boundary_id,
                    'land_clipped_display',
                    geom,
                    clip_source_document_id,
                    %s
                FROM repaired
                WHERE NOT ST_IsEmpty(geom)
                ON CONFLICT (electorate_boundary_id, geometry_role) DO UPDATE SET
                    geom = EXCLUDED.geom,
                    clip_source_document_id = EXCLUDED.clip_source_document_id,
                    metadata = EXCLUDED.metadata
                RETURNING electorate_boundary_id
            ),
            stale_deleted AS (
                DELETE FROM electorate_boundary_display_geometry display
                USING target_boundaries target
                WHERE display.electorate_boundary_id = target.electorate_boundary_id
                  AND display.geometry_role = 'land_clipped_display'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM upserted
                      WHERE upserted.electorate_boundary_id = display.electorate_boundary_id
                  )
                RETURNING display.id
            )
            SELECT
                (SELECT count(*) FROM upserted),
                (SELECT count(*) FROM stale_deleted)
            """,
            (
                boundary_set,
                land_summary["source_key"],
                DISPLAY_GEOMETRY_REPAIR_PROJECTION_SRID,
                coastline_repair_buffer_meters,
                as_jsonb(
                    {
                        "clip_method": "postgis_intersection_with_local_coastline_repair_buffer",
                        "geometry_role": "land_clipped_display",
                        "source_boundary_policy": "official_aec_geometry_preserved_in_electorate_boundary.geom",
                        "land_mask_source_key": land_summary["source_key"],
                        "land_mask_country_name": country_name,
                        "coastline_repair_buffer_meters": coastline_repair_buffer_meters,
                        "coastline_repair_projection_srid": (
                            DISPLAY_GEOMETRY_REPAIR_PROJECTION_SRID
                        ),
                    }
                ),
            ),
        )
        display_geometries_upserted, stale_display_geometries_deleted = cur.fetchone()
        cur.execute(
            """
            SELECT count(*)
            FROM electorate_boundary
            WHERE boundary_set = %s
            """,
            (boundary_set,),
        )
        source_boundary_count = cur.fetchone()[0]
    conn.commit()
    return {
        "boundary_set": boundary_set,
        "source_boundary_count": source_boundary_count,
        "display_geometries_upserted": display_geometries_upserted,
        "stale_display_geometries_deleted": stale_display_geometries_deleted,
        "land_mask": land_summary,
    }


def load_electorate_boundaries(conn, geojson_path: Path | None = None) -> dict[str, Any]:
    geojson_path = geojson_path or latest_aec_boundaries_geojson()
    if geojson_path is None:
        raise FileNotFoundError(
            "No processed AEC boundary GeoJSON found. Run `au-politics-money "
            "extract-aec-boundaries` first."
        )
    geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = geojson.get("features", [])
    if len(features) != 150:
        raise RuntimeError(
            f"Expected 150 current federal House boundary features; found {len(features)}."
        )

    source_metadata_path = _source_metadata_path_from_boundary_geojson(geojson)
    source_document_id = upsert_source_document(conn, source_metadata_path)
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "Cth")
    boundary_set = str(features[0]["properties"].get("boundary_set") or BOUNDARY_SET)

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE source_document
            SET parser_name = %s,
                parser_version = %s,
                parsed_at = now(),
                metadata = metadata || %s
            WHERE id = %s
            """,
            (
                BOUNDARY_PARSER_NAME,
                BOUNDARY_PARSER_VERSION,
                as_jsonb({"processed_geojson_path": str(geojson_path.resolve())}),
                source_document_id,
            ),
        )
        cur.execute("DELETE FROM electorate_boundary WHERE boundary_set = %s", (boundary_set,))

    inserted = 0
    division_names: list[str] = []
    for feature in features:
        properties = feature["properties"]
        division_name = str(properties["division_name"]).strip()
        if not division_name:
            raise RuntimeError(f"Boundary feature is missing division_name: {properties}")
        electorate_id = get_or_create_boundary_electorate(
            conn,
            name=division_name,
            jurisdiction_id=jurisdiction_id,
            source_document_id=source_document_id,
        )
        geometry_json = json.dumps(feature["geometry"], separators=(",", ":"), sort_keys=True)
        metadata = {
            **properties,
            "source_geojson_path": str(geojson_path.resolve()),
        }
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO electorate_boundary (
                    electorate_id, boundary_set, valid_from, valid_to,
                    geom, source_document_id, metadata
                )
                VALUES (
                    %s, %s, NULL, NULL,
                    ST_Multi(
                        ST_CollectionExtract(
                            ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)),
                            3
                        )
                    ),
                    %s, %s
                )
                """,
                (
                    electorate_id,
                    boundary_set,
                    geometry_json,
                    source_document_id,
                    as_jsonb(metadata),
                ),
            )
            inserted += cur.rowcount
        division_names.append(division_name)

    missing_boundaries = _house_electorates_without_boundary(conn, boundary_set)
    boundaries_without_current_office = _boundary_names_without_current_house_office(
        conn,
        boundary_set,
    )
    stale_electorates_deleted = _delete_stale_boundary_only_electorates(
        conn,
        jurisdiction_id=jurisdiction_id,
        boundary_set=boundary_set,
    )
    display_geometry_summary = load_electorate_boundary_display_geometries(
        conn,
        boundary_set=boundary_set,
    )
    conn.commit()
    return {
        "boundary_set": boundary_set,
        "boundaries_inserted": inserted,
        "division_count": len(division_names),
        "geojson_path": str(geojson_path.resolve()),
        "house_electorates_without_boundary": missing_boundaries,
        "boundaries_without_current_house_office": boundaries_without_current_office,
        "stale_boundary_only_electorates_deleted": stale_electorates_deleted,
        "source_document_id": source_document_id,
        "display_geometry": display_geometry_summary,
    }


def _vote_person_lookup(conn, *, chamber: str) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                person.id,
                person.display_name,
                person.canonical_name,
                person.metadata,
                office_term.party_id,
                electorate.name AS electorate_name,
                electorate.state_or_territory
            FROM person
            LEFT JOIN office_term
              ON office_term.person_id = person.id
             AND office_term.chamber = %s
             AND office_term.term_end IS NULL
            LEFT JOIN electorate ON electorate.id = office_term.electorate_id
            ORDER BY person.id
            """,
            (chamber,),
        )
        return [
            {
                "person_id": int(row[0]),
                "display_name": row[1],
                "canonical_name": row[2],
                "metadata": row[3] or {},
                "party_id": int(row[4]) if row[4] is not None else None,
                "electorate_name": row[5] or "",
                "state_or_territory": row[6] or "",
            }
            for row in cur.fetchall()
        ]


def _match_tvfy_vote_person(
    conn,
    *,
    vote: dict[str, Any],
    chamber: str,
    vote_person_lookup_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[int | None, int | None]:
    normalized_name = normalize_name(vote.get("person_name", ""))
    normalized_electorate = normalize_electorate_name(vote.get("electorate", ""))
    state = state_code(vote.get("state", ""))
    matches = []
    if vote_person_lookup_cache is None:
        candidates = _vote_person_lookup(conn, chamber=chamber)
    else:
        if chamber not in vote_person_lookup_cache:
            vote_person_lookup_cache[chamber] = _vote_person_lookup(conn, chamber=chamber)
        candidates = vote_person_lookup_cache[chamber]

    for candidate in candidates:
        if normalized_name not in {
            normalize_name(candidate["display_name"]),
            normalize_name(candidate["canonical_name"]),
        }:
            continue
        matches.append(candidate)

    if normalized_electorate:
        electorate_matches = [
            candidate
            for candidate in matches
            if normalize_electorate_name(candidate["electorate_name"]) == normalized_electorate
        ]
        if len(electorate_matches) == 1:
            candidate = electorate_matches[0]
            return candidate["person_id"], candidate["party_id"]

    if state:
        state_matches = [
            candidate
            for candidate in matches
            if state_code(candidate["state_or_territory"]) == state
        ]
        if len(state_matches) == 1:
            candidate = state_matches[0]
            return candidate["person_id"], candidate["party_id"]

    if len(matches) == 1:
        candidate = matches[0]
        return candidate["person_id"], candidate["party_id"]

    tvfy_person_id = vote.get("tvfy_person_id")
    if tvfy_person_id is not None:
        external_key = f"they_vote_for_you:person:{tvfy_person_id}"
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM person WHERE external_key = %s", (external_key,))
            row = cur.fetchone()
            if row is not None:
                return int(row[0]), None
            cur.execute(
                """
                SELECT id, metadata
                FROM person
                WHERE metadata->>'they_vote_for_you_person_id' = %s
                """,
                (str(tvfy_person_id),),
            )
            row = cur.fetchone()
            if row is not None:
                return int(row[0]), None

    return None, None


def _get_or_create_tvfy_vote_person(
    conn,
    *,
    vote: dict[str, Any],
    chamber: str,
    jurisdiction_id: int,
    source_document_id: int,
    vote_person_lookup_cache: dict[str, list[dict[str, Any]]] | None = None,
) -> tuple[int, int | None, bool]:
    matched_person_id, matched_party_id = _match_tvfy_vote_person(
        conn,
        vote=vote,
        chamber=chamber,
        vote_person_lookup_cache=vote_person_lookup_cache,
    )
    party_name = vote.get("party", "")
    party_id = get_or_create_party(conn, party_name, jurisdiction_id) if party_name else matched_party_id
    if matched_person_id is not None:
        if vote.get("tvfy_person_id") is not None:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE person
                    SET metadata = metadata || %s
                    WHERE id = %s
                    """,
                    (
                        as_jsonb({"they_vote_for_you_person_id": str(vote["tvfy_person_id"])}),
                        matched_person_id,
                    ),
                )
        return matched_person_id, party_id, False

    person_name = vote.get("person_name") or f"They Vote For You Person {vote.get('tvfy_person_id')}"
    tvfy_person_id = vote.get("tvfy_person_id")
    external_key = (
        f"they_vote_for_you:person:{tvfy_person_id}"
        if tvfy_person_id is not None
        else f"they_vote_for_you:person:{chamber}:{slugify(person_name, 'unknown')}"
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (external_key) DO UPDATE SET
                display_name = EXCLUDED.display_name,
                canonical_name = EXCLUDED.canonical_name,
                source_document_id = EXCLUDED.source_document_id,
                metadata = person.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                external_key,
                person_name,
                person_name,
                source_document_id,
                as_jsonb(
                    {
                        "source": "they_vote_for_you",
                        "source_evidence_class": "third_party_civic",
                        "they_vote_for_you_person_id": str(tvfy_person_id)
                        if tvfy_person_id is not None
                        else None,
                        "fallback_created_for_vote_ingestion": True,
                    }
                ),
            ),
        )
        person_id = int(cur.fetchone()[0])

    electorate_name = vote.get("electorate") or (
        f"Senate - {state_code(vote.get('state', ''))}"
        if chamber == "senate" and vote.get("state")
        else ""
    )
    electorate_id = None
    if electorate_name:
        electorate_id = get_or_create_electorate(
            conn,
            electorate_name,
            chamber,
            state_code(vote.get("state", "")),
            jurisdiction_id,
        )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id,
                source_document_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (external_key) DO UPDATE SET
                party_id = EXCLUDED.party_id,
                electorate_id = EXCLUDED.electorate_id,
                metadata = office_term.metadata || EXCLUDED.metadata
            """,
            (
                f"they_vote_for_you:office:{external_key}:{chamber}",
                person_id,
                chamber,
                electorate_id,
                party_id,
                source_document_id,
                as_jsonb(
                    {
                        "source": "they_vote_for_you",
                        "source_evidence_class": "third_party_civic",
                    }
                ),
            ),
        )
    return person_id, party_id, True


def _policy_slug(policy: dict[str, Any]) -> str:
    policy_id = policy.get("tvfy_policy_id")
    if policy_id is not None:
        return f"they_vote_for_you_policy_{policy_id}"
    return f"they_vote_for_you_policy_{slugify(policy.get('name', ''), 'unknown')}"


def _upsert_tvfy_policy_topic(conn, policy: dict[str, Any]) -> int | None:
    name = str(policy.get("name") or "").strip()
    if not name:
        return None
    slug = _policy_slug(policy)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO policy_topic (slug, label, description, metadata)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET
                label = EXCLUDED.label,
                description = EXCLUDED.description,
                metadata = policy_topic.metadata || EXCLUDED.metadata
            RETURNING id
            """,
            (
                slug,
                name,
                policy.get("description") or "",
                as_jsonb(
                    {
                        "source": "they_vote_for_you",
                        "source_evidence_class": "third_party_civic",
                        "they_vote_for_you_policy_id": policy.get("tvfy_policy_id"),
                        "provisional": policy.get("provisional"),
                        "last_edited_at": policy.get("last_edited_at"),
                    }
                ),
            ),
        )
        return int(cur.fetchone()[0])


def load_they_vote_for_you_divisions(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    jsonl_path = jsonl_path or latest_they_vote_for_you_divisions_jsonl()
    if jsonl_path is None:
        raise FileNotFoundError(
            "No processed They Vote For You divisions JSONL found. Run "
            "`au-politics-money fetch-they-vote-for-you-divisions` and "
            "`au-politics-money extract-they-vote-for-you-divisions` first."
        )

    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "Cth")
    divisions_seen = 0
    divisions_inserted_or_updated = 0
    votes_seen = 0
    votes_inserted_or_updated = 0
    fallback_people_created = 0
    policy_topics_seen = 0
    division_topics_inserted_or_updated = 0
    stale_tvfy_vote_rows_deleted = 0
    vote_person_lookup_cache: dict[str, list[dict[str, Any]]] = {}

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            divisions_seen += 1
            source_document_id = upsert_source_document(conn, Path(record["source_metadata_path"]))
            division_date = parse_date(str(record["division_date"]))
            if division_date is None:
                raise RuntimeError(f"Division is missing a parseable date: {record}")
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO vote_division (
                        external_id, chamber, division_date, division_number, title,
                        bill_name, motion_text, aye_count, no_count, possible_turnout,
                        source_document_id, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chamber, division_date, division_number) DO UPDATE SET
                        external_id = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN vote_division.external_id
                            ELSE EXCLUDED.external_id
                        END,
                        title = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.title, EXCLUDED.title)
                            ELSE EXCLUDED.title
                        END,
                        bill_name = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.bill_name, EXCLUDED.bill_name)
                            ELSE EXCLUDED.bill_name
                        END,
                        motion_text = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.motion_text, EXCLUDED.motion_text)
                            ELSE EXCLUDED.motion_text
                        END,
                        aye_count = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.aye_count, EXCLUDED.aye_count)
                            ELSE EXCLUDED.aye_count
                        END,
                        no_count = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.no_count, EXCLUDED.no_count)
                            ELSE EXCLUDED.no_count
                        END,
                        possible_turnout = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN COALESCE(vote_division.possible_turnout, EXCLUDED.possible_turnout)
                            ELSE EXCLUDED.possible_turnout
                        END,
                        source_document_id = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN vote_division.source_document_id
                            ELSE EXCLUDED.source_document_id
                        END,
                        metadata = CASE
                            WHEN vote_division.metadata ->> 'source' = 'aph_official_decision_record'
                            THEN vote_division.metadata || jsonb_build_object(
                                'they_vote_for_you',
                                COALESCE(vote_division.metadata -> 'they_vote_for_you', '{}'::jsonb)
                                || EXCLUDED.metadata
                            )
                            ELSE vote_division.metadata || EXCLUDED.metadata
                        END
                    RETURNING id
                    """,
                    (
                        record["external_id"],
                        record["chamber"],
                        division_date,
                        record["division_number"],
                        record["title"],
                        record.get("bill_name") or None,
                        record.get("motion_text") or None,
                        record.get("aye_count"),
                        record.get("no_count"),
                        record.get("possible_turnout"),
                        source_document_id,
                        as_jsonb(
                            {
                                **(record.get("metadata") or {}),
                                "source": "they_vote_for_you",
                                "source_evidence_class": "third_party_civic",
                                "they_vote_for_you_division_id": record.get("tvfy_division_id"),
                                "source_url": record.get("source_url"),
                                "clock_time": record.get("clock_time"),
                                "rebellions_count": record.get("rebellions_count"),
                                "edited": record.get("edited"),
                                "bills": record.get("bills") or [],
                                "raw_keys": record.get("raw_keys") or [],
                            }
                        ),
                    ),
                )
                division_id = int(cur.fetchone()[0])
                divisions_inserted_or_updated += 1
                cur.execute(
                    """
                    DELETE FROM person_vote
                    WHERE division_id = %s
                      AND metadata->>'source' = 'they_vote_for_you'
                    """,
                    (division_id,),
                )
                stale_tvfy_vote_rows_deleted += cur.rowcount

            for policy in record.get("policies") or []:
                topic_id = _upsert_tvfy_policy_topic(conn, policy)
                if topic_id is None:
                    continue
                policy_topics_seen += 1
                topic_confidence = Decimal("0.550") if policy.get("provisional") else Decimal("0.700")
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO division_topic (
                            division_id, topic_id, method, confidence, evidence_note
                        )
                        VALUES (%s, %s, 'third_party_civic', %s, %s)
                        ON CONFLICT (division_id, topic_id) DO UPDATE SET
                            method = EXCLUDED.method,
                            confidence = EXCLUDED.confidence,
                            evidence_note = EXCLUDED.evidence_note
                        """,
                        (
                            division_id,
                            topic_id,
                            topic_confidence,
                            (
                                "Policy linkage imported from They Vote For You; "
                                f"policy vote cue: {policy.get('vote') or 'not supplied'}."
                            ),
                        ),
                    )
                    division_topics_inserted_or_updated += cur.rowcount

            for vote in record.get("votes") or []:
                votes_seen += 1
                person_id, party_id, fallback_created = _get_or_create_tvfy_vote_person(
                    conn,
                    vote=vote,
                    chamber=record["chamber"],
                    jurisdiction_id=jurisdiction_id,
                    source_document_id=source_document_id,
                    vote_person_lookup_cache=vote_person_lookup_cache,
                )
                if fallback_created:
                    fallback_people_created += 1
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO person_vote (
                            division_id, person_id, vote, party_id,
                            rebelled_against_party, source_document_id, metadata
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (division_id, person_id) DO UPDATE SET
                            vote = CASE
                                WHEN person_vote.metadata ->> 'source' = 'aph_official_decision_record'
                                THEN person_vote.vote
                                ELSE EXCLUDED.vote
                            END,
                            party_id = CASE
                                WHEN person_vote.metadata ->> 'source' = 'aph_official_decision_record'
                                THEN COALESCE(person_vote.party_id, EXCLUDED.party_id)
                                ELSE EXCLUDED.party_id
                            END,
                            rebelled_against_party = COALESCE(
                                EXCLUDED.rebelled_against_party,
                                person_vote.rebelled_against_party
                            ),
                            source_document_id = CASE
                                WHEN person_vote.metadata ->> 'source' = 'aph_official_decision_record'
                                THEN person_vote.source_document_id
                                ELSE EXCLUDED.source_document_id
                            END,
                            metadata = CASE
                                WHEN person_vote.metadata ->> 'source' = 'aph_official_decision_record'
                                THEN person_vote.metadata || jsonb_build_object(
                                    'they_vote_for_you',
                                    COALESCE(person_vote.metadata -> 'they_vote_for_you', '{}'::jsonb)
                                    || EXCLUDED.metadata
                                )
                                ELSE person_vote.metadata || EXCLUDED.metadata
                            END
                        """,
                        (
                            division_id,
                            person_id,
                            vote["vote"],
                            party_id,
                            vote.get("rebelled_against_party"),
                            source_document_id,
                            as_jsonb(
                                {
                                    "source": "they_vote_for_you",
                                    "source_evidence_class": "third_party_civic",
                                    "tvfy_person_id": vote.get("tvfy_person_id"),
                                    "person_name": vote.get("person_name"),
                                    "electorate": vote.get("electorate"),
                                    "state": vote.get("state"),
                                    "party": vote.get("party"),
                                    "raw_vote": vote.get("raw_vote"),
                                    "source_index": vote.get("source_index"),
                                }
                            ),
                        ),
                    )
                    votes_inserted_or_updated += cur.rowcount

    conn.commit()
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH stale_people AS (
                SELECT person.id
                FROM person
                WHERE person.metadata->>'fallback_created_for_vote_ingestion' = 'true'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM person_vote
                      WHERE person_vote.person_id = person.id
                  )
            )
            DELETE FROM office_term
            USING stale_people
            WHERE office_term.person_id = stale_people.id
              AND office_term.metadata->>'source' = 'they_vote_for_you'
            """
        )
        stale_fallback_office_terms_deleted = cur.rowcount
        cur.execute(
            """
            DELETE FROM person
            WHERE person.metadata->>'fallback_created_for_vote_ingestion' = 'true'
              AND NOT EXISTS (
                  SELECT 1
                  FROM person_vote
                  WHERE person_vote.person_id = person.id
              )
              AND NOT EXISTS (
                  SELECT 1
                  FROM office_term
                  WHERE office_term.person_id = person.id
              )
            """
        )
        stale_fallback_people_deleted = cur.rowcount
    conn.commit()
    return {
        "jsonl_path": str(jsonl_path.resolve()),
        "divisions_seen": divisions_seen,
        "divisions_inserted_or_updated": divisions_inserted_or_updated,
        "votes_seen": votes_seen,
        "votes_inserted_or_updated": votes_inserted_or_updated,
        "fallback_people_created": fallback_people_created,
        "stale_tvfy_vote_rows_deleted": stale_tvfy_vote_rows_deleted,
        "stale_fallback_office_terms_deleted": stale_fallback_office_terms_deleted,
        "stale_fallback_people_deleted": stale_fallback_people_deleted,
        "policy_topics_seen": policy_topics_seen,
        "division_topics_inserted_or_updated": division_topics_inserted_or_updated,
    }


def _current_chamber_vote_person_index(conn, chamber: str) -> dict[str, list[tuple[int, int | None]]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT
                person.id, person.canonical_name, person.first_name, person.last_name,
                party.id
            FROM person
            JOIN office_term ON office_term.person_id = person.id
            LEFT JOIN party ON party.id = office_term.party_id
            WHERE office_term.chamber = %s
              AND office_term.term_end IS NULL
            """,
            (chamber,),
        )
        rows = cur.fetchall()

    surname_counts: Counter[str] = Counter(normalize_name(str(row[3] or "")) for row in rows)
    index: dict[str, list[tuple[int, int | None]]] = defaultdict(list)
    for person_id, canonical_name, first_name, last_name, party_id in rows:
        canonical = str(canonical_name or "")
        first = str(first_name or "")
        last = str(last_name or "")
        keys = {normalize_name(canonical), normalize_name(f"{last}, {first}")}
        if surname_counts[normalize_name(last)] == 1:
            keys.add(normalize_name(last))
        for key in keys:
            if key:
                index[key].append((int(person_id), int(party_id) if party_id is not None else None))
    return index


def _match_vote_person(
    vote_index: dict[str, list[tuple[int, int | None]]],
    vote: dict[str, Any],
) -> tuple[int, int | None] | None:
    keys = {
        normalize_name(str(vote.get("name_key") or "")),
        normalize_name(str(vote.get("raw_name") or "")),
        normalize_name(str(vote.get("matched_roster_canonical_name") or "")),
    }
    matches: list[tuple[int, int | None]] = []
    for key in keys:
        if key and key in vote_index:
            matches.extend(vote_index[key])
    unique_matches = sorted(set(matches))
    return unique_matches[0] if len(unique_matches) == 1 else None


def load_official_aph_divisions(conn, jsonl_path: Path | None = None) -> dict[str, Any]:
    jsonl_path = jsonl_path or latest_official_aph_divisions_jsonl()
    if jsonl_path is None:
        return {
            "divisions_seen": 0,
            "divisions_inserted_or_updated": 0,
            "votes_seen": 0,
            "votes_inserted_or_updated": 0,
            "skipped_reason": "no_official_aph_divisions_artifact",
        }

    vote_indexes: dict[str, dict[str, list[tuple[int, int | None]]]] = {}
    divisions_seen = 0
    divisions_inserted_or_updated = 0
    votes_seen = 0
    votes_inserted_or_updated = 0
    unmatched_votes = 0
    stale_official_vote_rows_deleted = 0
    chamber_counts: Counter[str] = Counter()

    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            divisions_seen += 1
            chamber = record["chamber"]
            chamber_counts[chamber] += 1
            if chamber not in vote_indexes:
                vote_indexes[chamber] = _current_chamber_vote_person_index(conn, chamber)
            source_document_id = upsert_source_document(conn, Path(record["source_metadata_path"]))
            division_date = parse_date(str(record["division_date"]))
            if division_date is None:
                raise RuntimeError(f"Official APH division is missing a parseable date: {record}")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO vote_division (
                        external_id, chamber, division_date, division_number, title,
                        bill_name, motion_text, aye_count, no_count, possible_turnout,
                        source_document_id, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (chamber, division_date, division_number) DO UPDATE SET
                        external_id = EXCLUDED.external_id,
                        title = EXCLUDED.title,
                        bill_name = EXCLUDED.bill_name,
                        motion_text = EXCLUDED.motion_text,
                        aye_count = EXCLUDED.aye_count,
                        no_count = EXCLUDED.no_count,
                        possible_turnout = EXCLUDED.possible_turnout,
                        source_document_id = EXCLUDED.source_document_id,
                        metadata = vote_division.metadata || EXCLUDED.metadata
                    RETURNING id
                    """,
                    (
                        record["external_id"],
                        chamber,
                        division_date,
                        record["division_number"],
                        record["title"],
                        record.get("bill_name") or None,
                        record.get("motion_text") or None,
                        record.get("aye_count"),
                        record.get("no_count"),
                        record.get("possible_turnout"),
                        source_document_id,
                        as_jsonb(
                            {
                                **(record.get("metadata") or {}),
                                "source": "aph_official_decision_record",
                                "source_evidence_class": "official_record_parsed",
                                "official_aph_external_id": record["external_id"],
                                "official_decision_record_external_key": record.get(
                                    "official_decision_record_external_key"
                                ),
                                "source_url": record.get("source_url"),
                                "representation_kind": record.get("representation_kind"),
                            }
                        ),
                    ),
                )
                division_id = int(cur.fetchone()[0])
                divisions_inserted_or_updated += 1
                cur.execute(
                    """
                    DELETE FROM person_vote
                    WHERE division_id = %s
                      AND metadata->>'source' = 'aph_official_decision_record'
                    """,
                    (division_id,),
                )
                stale_official_vote_rows_deleted += cur.rowcount

            for vote in record.get("votes") or []:
                votes_seen += 1
                match = _match_vote_person(vote_indexes[chamber], vote)
                if match is None:
                    unmatched_votes += 1
                    continue
                person_id, party_id = match
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO person_vote (
                            division_id, person_id, vote, party_id,
                            rebelled_against_party, source_document_id, metadata
                        )
                        VALUES (%s, %s, %s, %s, NULL, %s, %s)
                        ON CONFLICT (division_id, person_id) DO UPDATE SET
                            vote = EXCLUDED.vote,
                            party_id = EXCLUDED.party_id,
                            source_document_id = EXCLUDED.source_document_id,
                            metadata = person_vote.metadata || EXCLUDED.metadata
                        """,
                        (
                            division_id,
                            person_id,
                            vote["vote"],
                            party_id,
                            source_document_id,
                            as_jsonb(
                                {
                                    "source": "aph_official_decision_record",
                                    "source_evidence_class": "official_record_parsed",
                                    "raw_vote_name": vote.get("raw_name"),
                                    "name_key": vote.get("name_key"),
                                    "is_teller": vote.get("is_teller"),
                                    "source_line": vote.get("source_line"),
                                }
                            ),
                        ),
                    )
                    votes_inserted_or_updated += cur.rowcount

    conn.commit()
    return {
        "jsonl_path": str(jsonl_path.resolve()),
        "divisions_seen": divisions_seen,
        "divisions_inserted_or_updated": divisions_inserted_or_updated,
        "votes_seen": votes_seen,
        "votes_inserted_or_updated": votes_inserted_or_updated,
        "unmatched_votes": unmatched_votes,
        "stale_official_vote_rows_deleted": stale_official_vote_rows_deleted,
        "chamber_counts": dict(sorted(chamber_counts.items())),
    }


def load_official_parliamentary_decision_records(
    conn,
    jsonl_paths: list[Path] | None = None,
) -> dict[str, Any]:
    paths = jsonl_paths or latest_aph_decision_record_index_jsonl_paths()
    if not paths:
        return {
            "records_seen": 0,
            "records_inserted_or_updated": 0,
            "skipped_reason": "no_aph_decision_record_index_artifacts",
        }

    records_seen = 0
    records_inserted_or_updated = 0
    source_counts: Counter[str] = Counter()
    kind_counts: Counter[str] = Counter()
    source_doc_cache: dict[str, int | None] = {}

    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                record = json.loads(line)
                records_seen += 1
                source_counts[record["source_id"]] += 1
                kind_counts[record["record_kind"]] += 1

                source_metadata_path = record.get("source_metadata_path") or ""
                if source_metadata_path not in source_doc_cache:
                    metadata_path = Path(source_metadata_path) if source_metadata_path else None
                    source_doc_cache[source_metadata_path] = (
                        upsert_source_document(conn, metadata_path)
                        if metadata_path is not None and metadata_path.exists()
                        else None
                    )
                source_document_id = source_doc_cache[source_metadata_path]

                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO official_parliamentary_decision_record (
                            external_key, source_document_id, source_id, chamber,
                            record_type, record_kind, parliament_label, year_label,
                            month_label, day_label, record_date, title, link_text, url,
                            evidence_status, parser_name, parser_version, metadata
                        )
                        VALUES (
                            %(external_key)s, %(source_document_id)s, %(source_id)s,
                            %(chamber)s, %(record_type)s, %(record_kind)s,
                            %(parliament_label)s, %(year_label)s, %(month_label)s,
                            %(day_label)s, %(record_date)s, %(title)s, %(link_text)s,
                            %(url)s, %(evidence_status)s, %(parser_name)s,
                            %(parser_version)s, %(metadata)s
                        )
                        ON CONFLICT (external_key) DO UPDATE SET
                            source_document_id = COALESCE(
                                EXCLUDED.source_document_id,
                                official_parliamentary_decision_record.source_document_id
                            ),
                            source_id = EXCLUDED.source_id,
                            chamber = EXCLUDED.chamber,
                            record_type = EXCLUDED.record_type,
                            record_kind = EXCLUDED.record_kind,
                            parliament_label = EXCLUDED.parliament_label,
                            year_label = EXCLUDED.year_label,
                            month_label = EXCLUDED.month_label,
                            day_label = EXCLUDED.day_label,
                            record_date = EXCLUDED.record_date,
                            title = EXCLUDED.title,
                            link_text = EXCLUDED.link_text,
                            url = EXCLUDED.url,
                            evidence_status = EXCLUDED.evidence_status,
                            parser_name = EXCLUDED.parser_name,
                            parser_version = EXCLUDED.parser_version,
                            metadata = official_parliamentary_decision_record.metadata
                                || EXCLUDED.metadata
                        """,
                        {
                            "external_key": record["external_key"],
                            "source_document_id": source_document_id,
                            "source_id": record["source_id"],
                            "chamber": record["chamber"],
                            "record_type": record["record_type"],
                            "record_kind": record["record_kind"],
                            "parliament_label": record.get("parliament_label") or None,
                            "year_label": record.get("year") or None,
                            "month_label": record.get("month") or None,
                            "day_label": record.get("day_label") or None,
                            "record_date": parse_date(str(record.get("record_date") or "")),
                            "title": record["title"],
                            "link_text": record.get("link_text") or None,
                            "url": record["url"],
                            "evidence_status": record["evidence_status"],
                            "parser_name": record["parser_name"],
                            "parser_version": record["parser_version"],
                            "metadata": as_jsonb(
                                {
                                    "schema_version": record.get("schema_version"),
                                    "source_name": record.get("source_name"),
                                    "source_metadata_path": source_metadata_path,
                                    "decision_record_index_artifact_path": str(path),
                                    "source_record_metadata": record.get("metadata") or {},
                                }
                            ),
                        },
                    )
                    records_inserted_or_updated += cur.rowcount

    conn.commit()
    return {
        "jsonl_paths": [str(path.resolve()) for path in paths],
        "records_seen": records_seen,
        "records_inserted_or_updated": records_inserted_or_updated,
        "source_counts": dict(sorted(source_counts.items())),
        "record_kind_counts": dict(sorted(kind_counts.items())),
    }


def load_official_parliamentary_decision_record_documents(
    conn,
    summary_path: Path | None = None,
) -> dict[str, Any]:
    path = summary_path or latest_aph_decision_record_documents_summary()
    if path is None:
        return {
            "documents_seen": 0,
            "documents_linked": 0,
            "skipped_reason": "no_aph_decision_record_document_fetch_summary",
        }

    payload = json.loads(path.read_text(encoding="utf-8"))
    documents_seen = 0
    documents_linked = 0
    skipped_not_fetched = 0
    skipped_missing_metadata = 0
    skipped_missing_decision_record = 0
    representation_counts: Counter[str] = Counter()

    for document in payload.get("documents") or []:
        if document.get("status") not in {"fetched", "skipped_existing"}:
            skipped_not_fetched += 1
            continue
        documents_seen += 1
        metadata_path_raw = document.get("metadata_path") or ""
        if not metadata_path_raw or not Path(metadata_path_raw).exists():
            skipped_missing_metadata += 1
            continue

        metadata_path = Path(metadata_path_raw)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        decision_metadata = (
            document.get("official_decision_record")
            or metadata.get("official_decision_record")
            or {}
        )
        representation = (
            document.get("official_decision_record_representation")
            or metadata.get("official_decision_record_representation")
            or {}
        )
        decision_external_key = decision_metadata.get("external_key") or document.get(
            "decision_record_external_key"
        )
        representation_url = representation.get("url") or document.get("representation_url")
        representation_kind = representation.get("record_kind") or document.get("representation_kind")
        if not (decision_external_key and representation_url and representation_kind):
            skipped_missing_metadata += 1
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM official_parliamentary_decision_record
                WHERE external_key = %s
                """,
                (decision_external_key,),
            )
            row = cur.fetchone()
            if row is None:
                skipped_missing_decision_record += 1
                continue
            decision_record_id = int(row[0])
            source_document_id = upsert_source_document(conn, metadata_path)
            cur.execute(
                """
                INSERT INTO official_parliamentary_decision_record_document (
                    decision_record_id, source_document_id, representation_url,
                    representation_kind, fetched_at, sha256, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (
                    decision_record_id, representation_url, source_document_id
                ) DO UPDATE SET
                    representation_kind = EXCLUDED.representation_kind,
                    fetched_at = EXCLUDED.fetched_at,
                    sha256 = EXCLUDED.sha256,
                    metadata = official_parliamentary_decision_record_document.metadata
                        || EXCLUDED.metadata
                """,
                (
                    decision_record_id,
                    source_document_id,
                    representation_url,
                    representation_kind,
                    parse_datetime(metadata.get("fetched_at", "")),
                    metadata.get("sha256") or None,
                    as_jsonb(
                        {
                            "fetch_summary_path": str(path),
                            "document_source_id": document.get("source_id"),
                            "fetch_status": document.get("status"),
                            "decision_record": decision_metadata,
                            "representation": representation,
                            "validation": document.get("validation") or {},
                        }
                    ),
                ),
            )
            documents_linked += cur.rowcount
            representation_counts[representation_kind] += 1

    conn.commit()
    return {
        "summary_path": str(path.resolve()),
        "documents_seen": documents_seen,
        "documents_linked": documents_linked,
        "skipped_not_fetched": skipped_not_fetched,
        "skipped_missing_metadata": skipped_missing_metadata,
        "skipped_missing_decision_record": skipped_missing_decision_record,
        "representation_counts": dict(sorted(representation_counts.items())),
    }


def load_processed_artifacts(
    *,
    database_url: str | None = None,
    apply_schema_first: bool = False,
    include_roster: bool = True,
    include_money_flows: bool = True,
    include_house_interests: bool = True,
    include_senate_interests: bool = True,
    include_electorate_boundaries: bool = True,
    include_influence_events: bool = True,
    include_entity_classifications: bool = True,
    include_official_identifiers: bool = True,
    include_official_decision_records: bool = True,
    include_official_decision_record_documents: bool = True,
    include_official_aph_divisions: bool = True,
    include_vote_divisions: bool = False,
    include_postcode_crosswalk: bool = True,
    include_party_entity_links: bool = True,
    reapply_reviews: bool = True,
) -> dict[str, Any]:
    with connect(database_url) as conn:
        migration_summary: dict[str, int] | None = None
        if apply_schema_first:
            apply_schema(conn)
            migration_summary = apply_migrations(conn)

        summary: dict[str, Any] = {"schema_applied": apply_schema_first}
        if migration_summary is not None:
            summary["migrations"] = migration_summary
        if include_roster:
            summary["roster"] = load_roster(conn)
        if include_money_flows:
            summary["money_flows"] = load_aec_money_flows(conn)
            summary["election_money_flows"] = load_aec_election_money_flows(conn)
            summary["public_funding_money_flows"] = load_aec_public_funding_money_flows(conn)
            summary["qld_ecq_eds_money_flows"] = load_qld_ecq_eds_money_flows(conn)
            summary["qld_ecq_eds_participants"] = load_qld_ecq_eds_participants(conn)
            summary["qld_ecq_eds_contexts"] = load_qld_ecq_eds_contexts(conn)
        if include_house_interests:
            summary["house_interests"] = load_house_interest_records(conn)
        if include_senate_interests:
            summary["senate_interests"] = load_senate_interest_records(conn)
        if include_electorate_boundaries:
            summary["electorate_boundaries"] = load_electorate_boundaries(conn)
        if include_influence_events:
            summary["influence_events"] = load_influence_events(conn)
        if include_entity_classifications:
            summary["entity_classifications"] = load_entity_classifications(conn)
        if include_official_identifiers:
            summary["official_identifiers"] = load_official_identifiers(conn)
        if include_official_decision_records:
            summary["official_decision_records"] = load_official_parliamentary_decision_records(
                conn
            )
        if include_official_decision_record_documents:
            summary["official_decision_record_documents"] = (
                load_official_parliamentary_decision_record_documents(conn)
            )
        if include_official_aph_divisions:
            summary["official_aph_divisions"] = load_official_aph_divisions(conn)
        if include_vote_divisions:
            summary["vote_divisions"] = load_they_vote_for_you_divisions(conn)
        if include_postcode_crosswalk:
            summary["postcode_electorate_crosswalk"] = load_postcode_electorate_crosswalk(conn)
        if include_party_entity_links:
            from au_politics_money.db.party_entity_suggestions import (
                materialize_party_entity_link_candidates,
            )

            summary["party_entity_links"] = materialize_party_entity_link_candidates(conn)
        if reapply_reviews:
            from au_politics_money.db.review import reapply_review_decisions

            exclude_review_subject_types = set()
            if not include_vote_divisions:
                exclude_review_subject_types.add("sector_policy_topic_link")
            if not include_party_entity_links:
                exclude_review_subject_types.add("party_entity_link")
            summary["review_decisions_reapplied"] = reapply_review_decisions(
                conn,
                apply=True,
                exclude_subject_types=exclude_review_subject_types,
            )
        return summary
