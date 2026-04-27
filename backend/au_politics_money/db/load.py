from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from au_politics_money.config import PROCESSED_DIR, PROJECT_ROOT

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


def normalize_name(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


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


def senate_api_name_to_canonical(value: str) -> str:
    cleaned = " ".join((value or "").split())
    if "," not in cleaned:
        return cleaned
    surname, given_names = [part.strip() for part in cleaned.split(",", maxsplit=1)]
    return " ".join(part for part in [given_names, surname] if part)


def normalize_electorate_name(value: str) -> str:
    normalized = normalize_name(value)
    return re.sub(r"\bold$", "", normalized).strip()


def state_code(value: str) -> str:
    cleaned = " ".join((value or "").split())
    return STATE_CODES.get(cleaned, cleaned)


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
                fetched_at = EXCLUDED.fetched_at,
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
            INSERT INTO jurisdiction (name, level, code)
            VALUES (%s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET level = EXCLUDED.level, code = EXCLUDED.code
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


def get_or_create_entity(conn, raw_name: str, entity_type: str = "unknown") -> int:
    canonical_name = raw_name.strip() or "Unknown"
    normalized_name = normalize_name(canonical_name) or "unknown"
    with conn.cursor() as cur:
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


def load_roster(conn, roster_path: Path | None = None) -> dict[str, int]:
    path = roster_path or latest_file(PROCESSED_DIR / "rosters", "aph_current_parliament_*.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "CWLTH")
    source_doc_cache: dict[str, int] = {}

    people_count = 0
    office_count = 0
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

    conn.commit()
    return {"people": people_count, "office_terms": office_count}


def load_aec_money_flows(conn, jsonl_path: Path | None = None) -> dict[str, int]:
    path = jsonl_path or latest_file(PROCESSED_DIR / "aec_annual_money_flows", "*.jsonl")
    source_doc_cache: dict[str, int] = {}
    jurisdiction_id = get_or_create_jurisdiction(conn, "Commonwealth", "federal", "CWLTH")

    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            metadata_path = record["source_metadata_path"]
            if metadata_path not in source_doc_cache:
                source_doc_cache[metadata_path] = upsert_source_document(conn, Path(metadata_path))
            source_document_id = source_doc_cache[metadata_path]

            source_entity_id = get_or_create_entity(conn, record["source_raw_name"])
            recipient_entity_id = get_or_create_entity(conn, record["recipient_raw_name"])
            amount = Decimal(record["amount_aud"]) if record["amount_aud"] else None
            external_key = (
                f"aec_annual:{record['source_table']}:{record['source_row_number']}:"
                f"{record['financial_year']}:{normalize_name(record['source_raw_name'])}:"
                f"{normalize_name(record['recipient_raw_name'])}:{record['amount_aud']}"
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
                        recipient_entity_id = EXCLUDED.recipient_entity_id,
                        amount = EXCLUDED.amount,
                        date_received = EXCLUDED.date_received,
                        source_document_id = EXCLUDED.source_document_id,
                        metadata = EXCLUDED.metadata
                    """,
                    (
                        external_key,
                        source_entity_id,
                        record["source_raw_name"] or "Unknown",
                        recipient_entity_id,
                        record["recipient_raw_name"] or "Unknown",
                        amount,
                        record["financial_year"],
                        parse_date(record["date"]),
                        record["return_type"],
                        record["receipt_type"],
                        record["flow_kind"],
                        jurisdiction_id,
                        source_document_id,
                        f"{record['source_table']}:{record['source_row_number']}",
                        json.dumps(record["original"], sort_keys=True),
                        "unresolved",
                        as_jsonb(record),
                    ),
                )
            count += 1

    conn.commit()
    return {"money_flows": count}


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
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gift_interest (
                        external_key, person_id, source_entity_id, source_raw_name,
                        interest_category, description, parliament_number, chamber,
                        source_document_id, source_page_ref, original_text,
                        extraction_confidence, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_key) DO UPDATE SET
                        person_id = EXCLUDED.person_id,
                        source_entity_id = EXCLUDED.source_entity_id,
                        source_raw_name = EXCLUDED.source_raw_name,
                        interest_category = EXCLUDED.interest_category,
                        description = EXCLUDED.description,
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
            description = record.get("description") or json.dumps(record.get("original", {}), sort_keys=True)
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO gift_interest (
                        external_key, person_id, source_entity_id, source_raw_name,
                        interest_category, description, date_reported,
                        parliament_number, chamber, source_document_id, source_page_ref,
                        original_text, extraction_confidence, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (external_key) DO UPDATE SET
                        person_id = EXCLUDED.person_id,
                        source_entity_id = EXCLUDED.source_entity_id,
                        source_raw_name = EXCLUDED.source_raw_name,
                        interest_category = EXCLUDED.interest_category,
                        description = EXCLUDED.description,
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
                        parse_date(record.get("lodgement_date", "")),
                        "48",
                        "senate",
                        source_document_id,
                        f"cdap:{record['cdap_id']}:interest:{record['interest_id']}",
                        json.dumps(record.get("original", {}), sort_keys=True),
                        "official_api_structured",
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


def load_processed_artifacts(
    *,
    database_url: str | None = None,
    apply_schema_first: bool = False,
    include_roster: bool = True,
    include_money_flows: bool = True,
    include_house_interests: bool = True,
    include_senate_interests: bool = True,
) -> dict[str, Any]:
    with connect(database_url) as conn:
        if apply_schema_first:
            apply_schema(conn)

        summary: dict[str, Any] = {"schema_applied": apply_schema_first}
        if include_roster:
            summary["roster"] = load_roster(conn)
        if include_money_flows:
            summary["money_flows"] = load_aec_money_flows(conn)
        if include_house_interests:
            summary["house_interests"] = load_house_interest_records(conn)
        if include_senate_interests:
            summary["senate_interests"] = load_senate_interest_records(conn)
        return summary
