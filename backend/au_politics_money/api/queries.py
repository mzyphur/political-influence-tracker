from __future__ import annotations

import base64
import binascii
import json
import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from au_politics_money.config import API_MIN_FREE_TEXT_QUERY_LENGTH
from au_politics_money.db.load import connect
from au_politics_money.db.party_entity_suggestions import party_entity_name_patterns


SEARCH_TYPES = {
    "representative",
    "electorate",
    "party",
    "entity",
    "sector",
    "policy_topic",
    "postcode",
}

STATE_LOCAL_MONEY_SOURCE_DATASETS = (
    "act_elections_gift_returns",
    "qld_ecq_eds",
    "vic_vec_funding_register",
)
STATE_LOCAL_RECORD_FLOW_KINDS = {
    "act_gift_in_kind",
    "act_gift_of_money",
    "qld_electoral_expenditure",
    "qld_gift",
    "vic_administrative_funding_entitlement",
    "vic_policy_development_funding_payment",
    "vic_public_funding_payment",
}
STATE_LOCAL_GIFT_FLOW_KINDS = (
    "act_gift_in_kind",
    "act_gift_of_money",
    "qld_gift",
)
STATE_LOCAL_MONEY_GIFT_FLOW_KINDS = (
    "act_gift_of_money",
    "qld_gift",
)
STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS = (
    "vic_administrative_funding_entitlement",
    "vic_policy_development_funding_payment",
    "vic_public_funding_payment",
)

PARTY_PUBLIC_LABELS = {
    "AG": "Australian Greens",
    "ALP": "Australian Labor Party",
    "AV": "Australian Values Party",
    "CA": "Centre Alliance",
    "CLP": "Country Liberal Party",
    "IND": "Independent",
    "JLN": "Jacqui Lambie Network",
    "KAP": "Katter's Australian Party",
    "LNP": "Liberal National Party",
    "LP": "Liberal Party of Australia",
    "NATS": "The Nationals",
    "ON": "Pauline Hanson's One Nation",
    "UAP": "United Australia Party",
}

SEARCH_CAVEAT = (
    "Search results are discovery aids over normalized public-record data. "
    "They are not claims of wrongdoing, causation, or improper influence."
)

INFLUENCE_CONTEXT_CAVEAT = (
    "Rows show source-backed context only. They require an explicit sector-policy "
    "topic link and do not assert causation, quid pro quo, or corrupt conduct."
)

POSTCODE_CAVEAT = (
    "Australian postcodes can overlap multiple federal electorates. Postcode "
    "lookup will be enabled only after a source-backed postcode/locality to "
    "electorate crosswalk is ingested and caveated."
)

MAP_CAVEAT = (
    "Map features are derived from source-backed electorate boundary records and "
    "current office-term joins. Influence-event counts are non-rejected disclosed-record "
    "counts for current representatives, not electorate-level allegations or causal claims."
)

CONTACT_CAVEAT = (
    "Contact details are public APH roster/contact-list records. Email is returned only "
    "when present in an official APH contact-list PDF; otherwise the official APH "
    "profile/search link is the electronic contact path."
)

ENTITY_PROFILE_CAVEAT = (
    "Entity profiles show disclosed records where the entity appears as parsed source "
    "or parsed recipient. Access rows from lobbying registers are registry context only, "
    "not proof of a meeting or access granted. These are discovery/context records, not "
    "findings of improper conduct, and party/entity-level records must not be assigned "
    "to one representative without explicit source evidence."
)

PARTY_PROFILE_CAVEAT = (
    "Party profile totals aggregate disclosed money records for reviewed party-entity "
    "links only. Candidate entities are shown separately for review/discovery and are "
    "not claims about individual MPs or senators unless separately person-linked."
)

GRAPH_CAVEAT = (
    "Influence graph edges are source-backed disclosure relationships or reviewed "
    "party/entity links. Access edges from lobbying registers are registry context, not "
    "evidence of a meeting, access granted, or successful lobbying. Modelled "
    "party-to-representative exposure edges are analytical allocations, not disclosed "
    "personal receipts. Graphs are context for exploration, not claims of causation, "
    "quid pro quo, improper influence, or corruption."
)

REPRESENTATIVE_EVIDENCE_DIRECT_CAVEAT = (
    "Direct evidence pages include source-backed, non-rejected records linked to "
    "this person and exclude campaign-support rows. Counts are descriptive and do "
    "not imply wrongdoing, causation, or improper influence."
)

REPRESENTATIVE_EVIDENCE_CAMPAIGN_CAVEAT = (
    "Campaign-support evidence pages include source-backed election-return, public "
    "funding, party-channelled, advertising, or campaign-context rows linked to a "
    "candidate, Senate group, electorate, party branch, third party, or media "
    "advertiser. They are not personal receipts unless a source explicitly supports "
    "that narrower claim."
)

REPRESENTATIVE_EVIDENCE_GROUPS = {"direct", "campaign_support"}
_REPRESENTATIVE_EVIDENCE_MIN_DATE = date(1, 1, 1)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _contact_value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _representative_contact_from_metadata(
    metadata: dict[str, Any] | None,
    *,
    source_url: str | None = None,
) -> dict[str, Any]:
    metadata = metadata or {}
    email = _contact_value(metadata, "email")
    official_profile_url = _contact_value(metadata, "official_profile_search_url")
    return {
        "email": email,
        "email_source_metadata_path": None,
        "phones": {
            "electorate": _contact_value(metadata, "electorate_phone"),
            "parliament": _contact_value(metadata, "parliamentary_phone"),
            "tollfree": _contact_value(metadata, "electorate_tollfree"),
            "fax": _contact_value(metadata, "electorate_fax"),
        },
        "addresses": {
            "physical_office": _contact_value(metadata, "electorate_office_address"),
            "postal": _contact_value(metadata, "electorate_postal_address"),
            "parliament": _contact_value(metadata, "parliament_office_address"),
        },
        "web": {
            "official_profile": official_profile_url,
            "contact_form": None,
            "personal_website": None,
        },
        "source_url": source_url,
        "source_note": CONTACT_CAVEAT,
    }


def _clean_query(query: str) -> str:
    return " ".join(query.strip().split())


def _is_postcode_query(query: str) -> bool:
    return query.isdigit() and len(query) == 4


def _token_patterns(query: str) -> list[str]:
    return [f"%{token}%" for token in re.findall(r"[A-Za-z0-9]+", query) if len(token) >= 2][
        :6
    ]


def _state_code_sql(expression: str) -> str:
    return f"""
        CASE upper(trim({expression}))
            WHEN 'AUSTRALIAN CAPITAL TERRITORY' THEN 'ACT'
            WHEN 'NEW SOUTH WALES' THEN 'NSW'
            WHEN 'NORTHERN TERRITORY' THEN 'NT'
            WHEN 'QUEENSLAND' THEN 'QLD'
            WHEN 'SOUTH AUSTRALIA' THEN 'SA'
            WHEN 'TASMANIA' THEN 'TAS'
            WHEN 'VICTORIA' THEN 'VIC'
            WHEN 'WESTERN AUSTRALIA' THEN 'WA'
            ELSE NULLIF(upper(trim({expression})), '')
        END
    """


def _result(
    *,
    result_type: str,
    result_id: int | str,
    label: str,
    subtitle: str = "",
    rank: int = 100,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": result_type,
        "id": result_id,
        "label": label,
        "subtitle": subtitle,
        "rank": rank,
        "metadata": _jsonable(metadata or {}),
    }


def _fetch_dicts(conn, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def _representative_evidence_cursor(row: dict[str, Any]) -> str:
    payload = {
        "event_date": row["event_date"].isoformat() if row.get("event_date") else None,
        "date_reported": row["date_reported"].isoformat() if row.get("date_reported") else None,
        "id": int(row["id"]),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")


def _decode_representative_evidence_cursor(cursor: str) -> tuple[date, date, int]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (
        binascii.Error,
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid evidence cursor.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid evidence cursor.")
    event_id = payload.get("id")
    if not isinstance(event_id, int) or event_id <= 0:
        raise ValueError("Invalid evidence cursor.")
    return (
        _cursor_date(payload.get("event_date")),
        _cursor_date(payload.get("date_reported")),
        event_id,
    )


def _cursor_date(value: Any) -> date:
    if value is None:
        return _REPRESENTATIVE_EVIDENCE_MIN_DATE
    if not isinstance(value, str):
        raise ValueError("Invalid evidence cursor.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("Invalid evidence cursor.") from exc


def _with_representative_evidence_cursors(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        row["pagination_cursor"] = _representative_evidence_cursor(row)
    return rows


def _state_local_record_cursor(
    row: dict[str, Any],
    *,
    db_level: str | None,
    flow_kind: str | None,
) -> str:
    record_date = row.get("date_received") or row.get("date_reported")
    payload = {
        "db_level": db_level or "all",
        "flow_kind": flow_kind or "all",
        "record_date": record_date.isoformat() if record_date else None,
        "id": int(row["id"]),
    }
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(body).decode("ascii").rstrip("=")


def _decode_state_local_record_cursor(
    cursor: str,
    *,
    db_level: str | None,
    flow_kind: str | None,
) -> tuple[date, int]:
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (
        binascii.Error,
        UnicodeDecodeError,
        UnicodeEncodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("Invalid state/local record cursor.") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid state/local record cursor.")
    record_id = payload.get("id")
    if not isinstance(record_id, int) or record_id <= 0:
        raise ValueError("Invalid state/local record cursor.")
    if payload.get("db_level") != (db_level or "all") or payload.get("flow_kind") != (
        flow_kind or "all"
    ):
        raise ValueError("State/local record cursor does not match the requested filters.")
    return (_cursor_date(payload.get("record_date")), record_id)


def _with_state_local_record_cursors(
    rows: list[dict[str, Any]],
    *,
    db_level: str | None,
    flow_kind: str | None,
) -> list[dict[str, Any]]:
    for row in rows:
        row["pagination_cursor"] = _state_local_record_cursor(
            row,
            db_level=db_level,
            flow_kind=flow_kind,
        )
    return rows


def _table_exists(conn, table_name: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", (table_name,))
        return cur.fetchone()[0] is not None


def _geometry_from_geojson(value: str | dict | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _search_representatives(
    conn,
    pattern: str,
    token_patterns: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    state_expr = _state_code_sql(
        "COALESCE(NULLIF(electorate.state_or_territory, ''), NULLIF(office_term.metadata->>'state', ''))"
    )
    token_clause = ""
    params: list[Any] = [pattern, pattern]
    if token_patterns:
        token_parts = []
        for token_pattern in token_patterns:
            token_parts.append(
                "(person.display_name ILIKE %s OR person.canonical_name ILIKE %s)"
            )
            params.extend([token_pattern, token_pattern])
        token_clause = f" OR ({' AND '.join(token_parts)})"
    params.extend([pattern, limit])
    rows = _fetch_dicts(
        conn,
        f"""
        SELECT
            person.id,
            person.display_name,
            person.canonical_name,
            office_term.chamber,
            electorate.name AS electorate_name,
            {state_expr} AS state_or_territory,
            party.name AS party_name
        FROM person
        LEFT JOIN office_term
          ON office_term.person_id = person.id
         AND office_term.term_end IS NULL
        LEFT JOIN electorate ON electorate.id = office_term.electorate_id
        LEFT JOIN party ON party.id = office_term.party_id
        WHERE person.display_name ILIKE %s
           OR person.canonical_name ILIKE %s
           {token_clause}
        ORDER BY
            CASE WHEN person.display_name ILIKE %s THEN 0 ELSE 1 END,
            person.display_name
        LIMIT %s
        """,
        tuple(params),
    )
    return [
        _result(
            result_type="representative",
            result_id=row["id"],
            label=row["display_name"],
            subtitle=", ".join(
                item
                for item in (
                    row.get("party_name"),
                    row.get("electorate_name") or row.get("state_or_territory"),
                    row.get("chamber"),
                )
                if item
            ),
            rank=10,
            metadata=row,
        )
        for row in rows
    ]


def _search_electorates(
    conn,
    pattern: str,
    token_patterns: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    state_expr = _state_code_sql(
        "COALESCE(NULLIF(electorate.state_or_territory, ''), NULLIF(office_term.metadata->>'state', ''))"
    )
    token_clause = ""
    params: list[Any] = [pattern, pattern, pattern]
    if token_patterns:
        token_parts = []
        for token_pattern in token_patterns:
            token_parts.append(
                "("
                "electorate.name ILIKE %s "
                "OR electorate.state_or_territory ILIKE %s "
                "OR office_term.metadata->>'state' ILIKE %s"
                ")"
            )
            params.extend([token_pattern, token_pattern, token_pattern])
        token_clause = f" OR ({' AND '.join(token_parts)})"
    params.append(limit)
    rows = _fetch_dicts(
        conn,
        f"""
        WITH matches AS (
            SELECT DISTINCT ON (electorate.id)
                electorate.id,
                electorate.name,
                electorate.chamber,
                {state_expr} AS state_or_territory,
                person.id AS representative_id,
                person.display_name AS representative_name,
                party.name AS party_name,
                EXISTS (
                    SELECT 1
                    FROM electorate_boundary boundary
                    WHERE boundary.electorate_id = electorate.id
                ) AS has_boundary
            FROM electorate
            LEFT JOIN office_term
              ON office_term.electorate_id = electorate.id
             AND office_term.term_end IS NULL
            LEFT JOIN person ON person.id = office_term.person_id
            LEFT JOIN party ON party.id = office_term.party_id
            WHERE electorate.name ILIKE %s
               OR electorate.state_or_territory ILIKE %s
               OR office_term.metadata->>'state' ILIKE %s
               {token_clause}
            ORDER BY electorate.id, person.display_name NULLS LAST
        )
        SELECT *
        FROM matches
        ORDER BY name
        LIMIT %s
        """,
        tuple(params),
    )
    return [
        _result(
            result_type="electorate",
            result_id=row["id"],
            label=row["name"],
            subtitle=", ".join(
                item
                for item in (
                    row.get("state_or_territory"),
                    row.get("chamber"),
                    row.get("representative_name"),
                )
                if item
            ),
            rank=20,
            metadata=row,
        )
        for row in rows
    ]


def _party_search_terms(cleaned_query: str) -> tuple[list[str], set[str]]:
    lowered = cleaned_query.lower()
    name_patterns = [f"%{cleaned_query}%"]
    exact_short_names: set[str] = set()
    if any(trigger in lowered for trigger in ("labor", "labour", "alp")):
        exact_short_names.add("ALP")
    if "liberal national" in lowered or "lnp" in lowered:
        exact_short_names.add("LNP")
    elif "country liberal" in lowered or "clp" in lowered:
        exact_short_names.add("CLP")
    elif "liberal" in lowered:
        exact_short_names.update(("LP", "LNP", "CLP"))
    alias_terms = (
        (("national party", "nationals", "nats"), ("NATS",)),
        (("greens",), ("AG",)),
        (("one nation", "pauline hanson"), ("ON",)),
        (("united australia", "uap"), ("UAP",)),
        (("katter", "kap"), ("KAP",)),
        (("jacqui lambie", "lambie", "jln"), ("JLN",)),
        (("community alliance",), ("CA",)),
        (("independent",), ("IND",)),
    )
    for triggers, short_names in alias_terms:
        if any(trigger in lowered for trigger in triggers):
            exact_short_names.update(short_names)
    return name_patterns, exact_short_names


def _search_parties(conn, cleaned_query: str, limit: int) -> list[dict[str, Any]]:
    name_patterns, exact_short_names = _party_search_terms(cleaned_query)
    conditions = []
    params: list[Any] = []
    for pattern in name_patterns:
        conditions.append("(party.name ILIKE %s OR party.short_name ILIKE %s)")
        params.extend([pattern, pattern])
    if exact_short_names:
        placeholders = ", ".join(["%s"] * len(exact_short_names))
        conditions.append(f"party.short_name IN ({placeholders})")
        params.extend(sorted(exact_short_names))
    params.append(limit)
    rows = _fetch_dicts(
        conn,
        f"""
        SELECT
            party.id,
            party.name,
            party.short_name,
            count(DISTINCT office_term.person_id) FILTER (
                WHERE office_term.term_end IS NULL
            ) AS current_representative_count
        FROM party
        LEFT JOIN office_term ON office_term.party_id = party.id
        WHERE {" OR ".join(conditions)}
        GROUP BY party.id, party.name, party.short_name
        ORDER BY current_representative_count DESC, party.name
        LIMIT %s
        """,
        tuple(params),
    )
    return [
        _result(
            result_type="party",
            result_id=row["id"],
            label=_party_public_label(row.get("name"), row.get("short_name")),
            subtitle=f"{row['current_representative_count']} current representatives",
            rank=30,
            metadata=row,
        )
        for row in rows
    ]


def _party_public_label(name: str | None, short_name: str | None) -> str:
    cleaned_name = str(name or "").strip()
    cleaned_short = str(short_name or "").strip()
    mapped = PARTY_PUBLIC_LABELS.get(cleaned_short.upper())
    if mapped and cleaned_name.upper() == cleaned_short.upper():
        return f"{mapped} ({cleaned_short.upper()})"
    return cleaned_name or cleaned_short or "Unnamed party"


def _search_entities(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            entity.id,
            entity.canonical_name,
            entity.entity_type,
            count(DISTINCT influence_event.id) AS influence_event_count,
            sum(influence_event.amount) FILTER (
                WHERE influence_event.amount_status = 'reported'
                  AND influence_event.event_family <> 'campaign_support'
            ) AS reported_amount_total,
            count(DISTINCT influence_event.id) FILTER (
                WHERE influence_event.event_family = 'campaign_support'
            ) AS campaign_support_event_count,
            sum(influence_event.amount) FILTER (
                WHERE influence_event.amount_status = 'reported'
                  AND influence_event.event_family = 'campaign_support'
            ) AS campaign_support_reported_amount_total
        FROM entity
        LEFT JOIN influence_event
          ON (
                influence_event.source_entity_id = entity.id
                OR influence_event.recipient_entity_id = entity.id
             )
         AND influence_event.review_status <> 'rejected'
        WHERE entity.canonical_name ILIKE %s
        GROUP BY entity.id, entity.canonical_name, entity.entity_type
        ORDER BY influence_event_count DESC, entity.canonical_name
        LIMIT %s
        """,
        (pattern, limit),
    )
    return [
        _result(
            result_type="entity",
            result_id=row["id"],
            label=row["canonical_name"],
            subtitle=", ".join(
                item
                for item in (
                    row.get("entity_type"),
                    f"{row['influence_event_count']} influence events",
                )
                if item
            ),
            rank=40,
            metadata=row,
        )
        for row in rows
    ]


def _search_policy_topics(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            policy_topic.id,
            policy_topic.slug,
            policy_topic.label,
            count(division_topic.division_id) AS linked_division_count
        FROM policy_topic
        LEFT JOIN division_topic ON division_topic.topic_id = policy_topic.id
        WHERE policy_topic.label ILIKE %s
           OR policy_topic.slug ILIKE %s
        GROUP BY policy_topic.id, policy_topic.slug, policy_topic.label
        ORDER BY linked_division_count DESC, policy_topic.label
        LIMIT %s
        """,
        (pattern, pattern, limit),
    )
    return [
        _result(
            result_type="policy_topic",
            result_id=row["id"],
            label=row["label"],
            subtitle=f"{row['linked_division_count']} linked divisions",
            rank=50,
            metadata=row,
        )
        for row in rows
    ]


def _search_sectors(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            public_sector,
            count(DISTINCT entity_id) AS entity_count,
            count(*) AS classification_count
        FROM entity_industry_classification
        WHERE public_sector ILIKE %s
        GROUP BY public_sector
        ORDER BY entity_count DESC, public_sector
        LIMIT %s
        """,
        (pattern, limit),
    )
    return [
        _result(
            result_type="sector",
            result_id=row["public_sector"],
            label=row["public_sector"].replace("_", " ").title(),
            subtitle=f"{row['entity_count']} classified entities",
            rank=60,
            metadata=row,
        )
        for row in rows
    ]


def _append_unresolved_postcode_limitations(
    conn,
    *,
    query: str,
    limitations: list[dict[str, str]],
    has_resolved_rows: bool,
) -> bool:
    if not _table_exists(conn, "postcode_electorate_crosswalk_unresolved"):
        return False
    unresolved_rows = _fetch_dicts(
        conn,
        """
        SELECT
            postcode,
            electorate_name,
            state_or_territory,
            locality_count,
            source_boundary_context,
            current_member_context,
            metadata
        FROM postcode_electorate_crosswalk_unresolved
        WHERE postcode = %s
        ORDER BY confidence DESC, locality_count DESC, electorate_name
        LIMIT 10
        """,
        (query,),
    )
    if not unresolved_rows:
        return False
    candidate_names = ", ".join(
        str(row.get("electorate_name") or "unnamed electorate") for row in unresolved_rows
    )
    prefix = (
        "Some AEC postcode candidates are not yet linked to the local electorate table"
        if has_resolved_rows
        else "AEC postcode candidates were loaded but are not yet linked to the local electorate table"
    )
    limitations.append(
        {
            "feature": "postcode_search",
            "status": (
                "postcode_some_candidates_unresolved"
                if has_resolved_rows
                else "postcode_candidates_unresolved"
            ),
            "message": (
                f"{prefix} for postcode {query}: {candidate_names}. This can happen "
                "when the AEC finder reflects next-election boundaries or a new "
                "division name before the current map boundary table is refreshed."
            ),
        }
    )
    return True


def _search_postcodes(
    conn,
    query: str,
    limit: int,
    limitations: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not query.isdigit() or len(query) != 4:
        return []
    if not _table_exists(conn, "postcode_electorate_crosswalk"):
        limitations.append(
            {
                "feature": "postcode_search",
                "status": "not_loaded",
                "message": POSTCODE_CAVEAT,
            }
        )
        return []

    rows = _fetch_dicts(
        conn,
        """
        SELECT
            crosswalk.postcode,
            crosswalk.match_method,
            crosswalk.confidence,
            crosswalk.locality_count,
            crosswalk.localities,
            crosswalk.aec_division_ids,
            crosswalk.source_updated_text,
            crosswalk.source_boundary_context,
            crosswalk.current_member_context,
            crosswalk.metadata,
            source_document.source_id,
            source_document.url AS source_url,
            electorate.id AS electorate_id,
            electorate.name AS electorate_name,
            electorate.state_or_territory,
            electorate.chamber
        FROM postcode_electorate_crosswalk crosswalk
        JOIN electorate ON electorate.id = crosswalk.electorate_id
        LEFT JOIN source_document ON source_document.id = crosswalk.source_document_id
        WHERE crosswalk.postcode = %s
        ORDER BY crosswalk.confidence DESC, crosswalk.locality_count DESC, electorate.name
        LIMIT %s
        """,
        (query, limit),
    )
    has_unresolved_rows = _append_unresolved_postcode_limitations(
        conn,
        query=query,
        limitations=limitations,
        has_resolved_rows=bool(rows),
    )
    if not rows:
        limitations.append(
            {
                "feature": "postcode_search",
                "status": (
                    "postcode_no_map_linked_results"
                    if has_unresolved_rows
                    else "postcode_not_loaded"
                ),
                "message": (
                    (
                        "No AEC postcode candidates for this postcode are currently "
                        "linked to the map boundary table."
                    )
                    if has_unresolved_rows
                    else (
                        "No source-backed AEC electorate-finder crosswalk row is loaded "
                        f"for postcode {query}. The absence of a result is not evidence "
                        "that the postcode has no federal electorate."
                    )
                ),
            }
        )
        return []
    return [
        _result(
            result_type="postcode",
            result_id=f"{row['postcode']}:{row['electorate_id']}",
            label=f"{row['postcode']} -> {row['electorate_name']}",
            subtitle=(
                f"{row.get('state_or_territory') or ''} · "
                f"{row.get('locality_count') or 0} AEC localities"
            ).strip(" ·"),
            rank=5,
            metadata=row,
        )
        for row in rows
    ]


def search_database(
    query: str,
    *,
    result_types: set[str] | None = None,
    limit: int = 10,
    database_url: str | None = None,
) -> dict[str, Any]:
    cleaned = _clean_query(query)
    requested_types = result_types or set(SEARCH_TYPES)
    unknown_types = sorted(requested_types - SEARCH_TYPES)
    requested_types = requested_types & SEARCH_TYPES
    limit = max(1, min(limit, 50))
    limitations: list[dict[str, str]] = []
    if unknown_types:
        limitations.append(
            {
                "feature": "search_type_filter",
                "status": "ignored_unknown_types",
                "message": f"Ignored unsupported result types: {', '.join(unknown_types)}",
            }
        )
    if len(cleaned) < API_MIN_FREE_TEXT_QUERY_LENGTH and not _is_postcode_query(cleaned):
        limitations.append(
            {
                "feature": "free_text_search",
                "status": "query_too_short",
                "message": (
                    "Free-text search requires at least "
                    f"{API_MIN_FREE_TEXT_QUERY_LENGTH} characters."
                ),
            }
        )
        return {
            "query": query,
            "normalized_query": cleaned,
            "results": [],
            "result_count": 0,
            "limitations": limitations,
            "caveat": SEARCH_CAVEAT,
        }

    pattern = f"%{cleaned}%"
    token_patterns = _token_patterns(cleaned)
    results: list[dict[str, Any]] = []
    with connect(database_url) as conn:
        if "postcode" in requested_types:
            results.extend(_search_postcodes(conn, cleaned, limit, limitations))
        if "representative" in requested_types:
            results.extend(_search_representatives(conn, pattern, token_patterns, limit))
        if "electorate" in requested_types:
            results.extend(_search_electorates(conn, pattern, token_patterns, limit))
        if "party" in requested_types:
            results.extend(_search_parties(conn, cleaned, limit))
        if "entity" in requested_types:
            results.extend(_search_entities(conn, pattern, limit))
        if "policy_topic" in requested_types:
            results.extend(_search_policy_topics(conn, pattern, limit))
        if "sector" in requested_types:
            results.extend(_search_sectors(conn, pattern, limit))

    results = sorted(results, key=_search_result_sort_key)[:limit]
    return {
        "query": query,
        "normalized_query": cleaned,
        "results": results,
        "result_count": len(results),
        "limitations": limitations,
        "caveat": SEARCH_CAVEAT,
    }


def _search_result_sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    if item.get("type") == "postcode":
        return (
            item["rank"],
            -float(metadata.get("confidence") or 0),
            -int(metadata.get("locality_count") or 0),
            item["label"].lower(),
        )
    current_representatives = 0
    if item.get("type") == "party":
        current_representatives = int(metadata.get("current_representative_count") or 0)
    return (item["rank"], -current_representatives, item["label"].lower())


def get_electorate_map(
    *,
    chamber: str = "house",
    state: str | None = None,
    boundary_set: str | None = None,
    include_geometry: bool = True,
    simplify_tolerance: float = 0.0005,
    geometry_role: str = "display",
    database_url: str | None = None,
) -> dict[str, Any]:
    chamber = chamber.strip().lower()
    if chamber not in {"house", "senate"}:
        raise ValueError("chamber must be 'house' or 'senate'.")
    geometry_role = geometry_role.strip().lower()
    if geometry_role not in {"display", "source"}:
        raise ValueError("geometry_role must be 'display' or 'source'.")
    state = state.strip().upper() if state else None
    simplify_tolerance = max(0.0, min(float(simplify_tolerance), 0.25))
    if chamber == "senate":
        return _get_senate_map(
            state=state,
            boundary_set=boundary_set,
            include_geometry=include_geometry,
            simplify_tolerance=simplify_tolerance,
            geometry_role=geometry_role,
            database_url=database_url,
        )
    geometry_column = (
        "COALESCE(display_boundary.geom, boundary.geom)"
        if geometry_role == "display"
        else "boundary.geom"
    )
    display_join_filter = (
        "AND display_boundary.geometry_role = 'land_clipped_display'"
        if geometry_role == "display"
        else "AND FALSE"
    )
    geometry_expression = (
        """
        ST_AsGeoJSON(
            ST_Multi(ST_SimplifyPreserveTopology({geometry_column}, %s)),
            6
        ) AS geometry_geojson
        """.format(geometry_column=geometry_column)
        if include_geometry
        else "NULL::TEXT AS geometry_geojson"
    )
    params: list[Any] = [simplify_tolerance] if include_geometry else []
    state_expr = _state_code_sql(
        "COALESCE(NULLIF(electorate.state_or_territory, ''), reps.representative_state)"
    )
    boundary_filter = ""
    if boundary_set:
        boundary_filter = "AND boundary.boundary_set = %s"
        params.append(boundary_set)
    params.extend([boundary_set, boundary_set])
    params.append(chamber)
    state_filter = ""
    if state:
        state_filter = f"AND {state_expr} = %s"
        params.append(state)
    boundary_required_filter = "AND boundary.id IS NOT NULL" if boundary_set else ""

    with connect(database_url) as conn:
        rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                electorate.id AS electorate_id,
                electorate.name AS electorate_name,
                electorate.chamber,
                {state_expr} AS state_or_territory,
                boundary.boundary_set,
                boundary.valid_from AS boundary_valid_from,
                boundary.valid_to AS boundary_valid_to,
                boundary.id IS NOT NULL AS has_boundary,
                CASE
                    WHEN display_boundary.id IS NOT NULL THEN 'display'
                    ELSE 'source'
                END AS map_geometry_role,
                CASE
                    WHEN reps.current_representative_count = 1 THEN reps.representative_id
                    ELSE NULL
                END AS representative_id,
                CASE
                    WHEN reps.current_representative_count = 1 THEN reps.representative_name
                    ELSE NULL
                END AS representative_name,
                CASE
                    WHEN reps.current_representative_count = 1 THEN reps.party_id
                    ELSE NULL
                END AS party_id,
                CASE
                    WHEN reps.current_representative_count = 1 THEN reps.party_name
                    ELSE NULL
                END AS party_name,
                CASE
                    WHEN reps.current_representative_count = 1 THEN reps.party_short_name
                    ELSE NULL
                END AS party_short_name,
                reps.current_representative_count,
                reps.current_representatives,
                reps.party_breakdown,
                COALESCE(influence_summary.influence_event_count, 0)
                    AS current_representative_lifetime_influence_event_count,
                COALESCE(influence_summary.money_event_count, 0)
                    AS current_representative_lifetime_money_event_count,
                COALESCE(influence_summary.benefit_event_count, 0)
                    AS current_representative_lifetime_benefit_event_count,
                COALESCE(influence_summary.campaign_support_event_count, 0)
                    AS current_representative_lifetime_campaign_support_event_count,
                COALESCE(influence_summary.needs_review_event_count, 0)
                    AS current_representative_needs_review_event_count,
                COALESCE(influence_summary.official_record_event_count, 0)
                    AS current_representative_official_record_event_count,
                influence_summary.reported_amount_total
                    AS current_representative_lifetime_reported_amount_total,
                influence_summary.campaign_support_reported_amount_total
                    AS current_representative_campaign_support_reported_total,
                {geometry_expression}
            FROM electorate
            LEFT JOIN LATERAL (
                SELECT boundary_row.*
                FROM electorate_boundary boundary_row
                WHERE boundary_row.electorate_id = electorate.id
                {boundary_filter.replace("boundary.", "boundary_row.")}
                  AND (
                    %s::text IS NOT NULL
                    OR boundary_row.valid_from IS NULL
                    OR boundary_row.valid_from <= CURRENT_DATE
                  )
                  AND (
                    %s::text IS NOT NULL
                    OR boundary_row.valid_to IS NULL
                    OR boundary_row.valid_to >= CURRENT_DATE
                  )
                ORDER BY boundary_row.valid_from DESC NULLS LAST, boundary_row.id DESC
                LIMIT 1
            ) boundary ON TRUE
            LEFT JOIN electorate_boundary_display_geometry display_boundary
              ON display_boundary.electorate_boundary_id = boundary.id
             {display_join_filter}
            LEFT JOIN LATERAL (
                SELECT
                    (array_agg(person.id ORDER BY person.display_name))[1] AS representative_id,
                    (array_agg(person.display_name ORDER BY person.display_name))[1]
                        AS representative_name,
                    (array_agg(party.id ORDER BY person.display_name))[1] AS party_id,
                    (array_agg(party.name ORDER BY person.display_name))[1] AS party_name,
                    (array_agg(party.short_name ORDER BY person.display_name))[1]
                        AS party_short_name,
                    count(person.id) AS current_representative_count,
                    max({_state_code_sql("office_term.metadata->>'state'")})
                        AS representative_state,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'person_id', person.id,
                                'display_name', person.display_name,
                                'party_id', party.id,
                                'party_name', party.name,
                                'party_short_name', party.short_name,
                                'chamber', office_term.chamber,
                                'state_or_territory',
                                    {_state_code_sql("office_term.metadata->>'state'")},
                                'term_start', office_term.term_start
                            )
                            ORDER BY person.display_name
                        ) FILTER (WHERE person.id IS NOT NULL),
                        '[]'::jsonb
                    ) AS current_representatives,
                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                jsonb_build_object(
                                    'party_id', party_counts.party_id,
                                    'party_name', party_counts.party_name,
                                    'party_short_name', party_counts.party_short_name,
                                    'representative_count', party_counts.representative_count
                                )
                                ORDER BY party_counts.representative_count DESC,
                                    party_counts.party_name
                            )
                            FROM (
                                SELECT
                                    party.id AS party_id,
                                    party.name AS party_name,
                                    party.short_name AS party_short_name,
                                    count(DISTINCT person.id) AS representative_count
                                FROM office_term
                                JOIN person ON person.id = office_term.person_id
                                LEFT JOIN party ON party.id = office_term.party_id
                                WHERE office_term.electorate_id = electorate.id
                                  AND office_term.term_end IS NULL
                                GROUP BY party.id, party.name, party.short_name
                            ) party_counts
                        ),
                        '[]'::jsonb
                    ) AS party_breakdown
                FROM office_term
                JOIN person ON person.id = office_term.person_id
                LEFT JOIN party ON party.id = office_term.party_id
                WHERE office_term.electorate_id = electorate.id
                  AND office_term.term_end IS NULL
            ) reps ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    count(influence_event.id) AS influence_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'money'
                    ) AS money_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'benefit'
                    ) AS benefit_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'campaign_support'
                    ) AS campaign_support_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'needs_review'
                    ) AS needs_review_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.evidence_status IN (
                            'official_record',
                            'official_record_parsed'
                        )
                    ) AS official_record_event_count,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_total,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family = 'campaign_support'
                    ) AS campaign_support_reported_amount_total
                FROM (
                    SELECT DISTINCT office_term.person_id
                    FROM office_term
                    WHERE office_term.electorate_id = electorate.id
                      AND office_term.term_end IS NULL
                ) current_people
                JOIN influence_event
                  ON influence_event.recipient_person_id = current_people.person_id
                WHERE influence_event.review_status <> 'rejected'
            ) influence_summary ON TRUE
            WHERE electorate.chamber = %s
            {state_filter}
            {boundary_required_filter}
            ORDER BY
                {state_expr},
                electorate.name
            """,
            tuple(params),
        )

    features = []
    for row in rows:
        geometry = _geometry_from_geojson(row.pop("geometry_geojson"))
        electorate_id = row.pop("electorate_id")
        electorate_name = row.pop("electorate_name")
        features.append(
            {
                "type": "Feature",
                "id": electorate_id,
                "geometry": geometry,
                "properties": _jsonable(
                    {
                        "electorate_id": electorate_id,
                        "electorate_name": electorate_name,
                        **row,
                    }
                ),
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "feature_count": len(features),
        "filters": {
            "chamber": chamber,
            "state": state,
            "boundary_set": boundary_set,
            "include_geometry": include_geometry,
            "simplify_tolerance": simplify_tolerance,
            "geometry_role": geometry_role,
        },
        "caveat": MAP_CAVEAT,
    }


def get_data_coverage(*, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        source_rows = _fetch_dicts(
            conn,
            """
            SELECT
                source_id,
                source_name,
                source_type,
                jurisdiction,
                count(*) AS document_count,
                max(fetched_at) AS last_fetched_at
            FROM source_document
            GROUP BY source_id, source_name, source_type, jurisdiction
            ORDER BY jurisdiction, source_id
            """,
            (),
        )
        jurisdiction_rows = _fetch_dicts(
            conn,
            """
            SELECT level, count(*) AS jurisdiction_count
            FROM jurisdiction
            GROUP BY level
            ORDER BY level
            """,
            (),
        )
        representative_rows = _fetch_dicts(
            conn,
            """
            SELECT
                chamber,
                count(DISTINCT person_id) FILTER (WHERE term_end IS NULL)
                    AS current_representative_count,
                count(*) AS office_term_count
            FROM office_term
            GROUP BY chamber
            ORDER BY chamber
            """,
            (),
        )
        boundary_rows = _fetch_dicts(
            conn,
            """
            SELECT
                electorate.chamber,
                count(DISTINCT electorate.id) AS electorate_count,
                count(boundary.id) AS boundary_count,
                count(DISTINCT boundary.boundary_set) AS boundary_set_count
            FROM electorate
            LEFT JOIN electorate_boundary boundary
              ON boundary.electorate_id = electorate.id
            GROUP BY electorate.chamber
            ORDER BY electorate.chamber
            """,
            (),
        )
        display_land_mask_rows = (
            _fetch_dicts(
                conn,
                """
                SELECT
                    mask.source_key,
                    mask.country_name,
                    mask.geometry_role,
                    mask.source_document_id,
                    source_document.source_name,
                    source_document.source_type,
                    source_document.jurisdiction,
                    source_document.url AS source_url,
                    source_document.final_url AS source_final_url,
                    source_document.fetched_at AS source_fetched_at,
                    mask.metadata->>'licence_status' AS licence_status,
                    mask.metadata->>'mask_method' AS mask_method,
                    mask.metadata->>'source_limitations' AS source_limitations,
                    ST_IsValid(mask.geom) AS geometry_is_valid,
                    ST_NumGeometries(mask.geom) AS geometry_part_count
                FROM display_land_mask mask
                LEFT JOIN source_document
                  ON source_document.id = mask.source_document_id
                ORDER BY mask.country_name, mask.geometry_role, mask.source_key
                """,
                (),
            )
            if _table_exists(conn, "display_land_mask")
            else []
        )
        influence_family_rows = _fetch_dicts(
            conn,
            """
            SELECT
                event_family,
                count(*) AS event_count,
                count(*) FILTER (WHERE recipient_person_id IS NOT NULL)
                    AS person_linked_event_count,
                count(*) FILTER (WHERE recipient_party_id IS NOT NULL)
                    AS party_linked_event_count,
                count(*) FILTER (WHERE source_entity_id IS NOT NULL)
                    AS source_entity_linked_event_count,
                count(*) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_event_count,
                sum(amount) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE review_status <> 'rejected'
            GROUP BY event_family
            ORDER BY event_count DESC, event_family
            """,
            (),
        )
        influence_total_rows = _fetch_dicts(
            conn,
            """
            SELECT
                count(*) AS event_count,
                count(*) FILTER (WHERE recipient_person_id IS NOT NULL)
                    AS person_linked_event_count,
                count(*) FILTER (WHERE recipient_party_id IS NOT NULL)
                    AS party_linked_event_count,
                count(*) FILTER (WHERE source_entity_id IS NOT NULL)
                    AS source_entity_linked_event_count,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_total,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE review_status <> 'rejected'
            """,
            (),
        )
        state_local_money_rows = _fetch_dicts(
            conn,
            """
            SELECT
                jurisdiction.name AS jurisdiction_name,
                jurisdiction.level AS jurisdiction_level,
                jurisdiction.code AS jurisdiction_code,
                count(*) AS money_flow_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                ) AS gift_or_donation_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'act_gift_in_kind'
                ) AS gift_in_kind_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                ) AS electoral_expenditure_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                ) AS public_funding_count,
                count(*) FILTER (WHERE money_flow.amount IS NOT NULL)
                    AS reported_amount_event_count,
                sum(money_flow.amount) FILTER (WHERE money_flow.amount IS NOT NULL)
                    AS reported_amount_total,
                min(money_flow.date_received) AS first_event_date,
                max(money_flow.date_received) AS last_event_date
            FROM money_flow
            JOIN jurisdiction
              ON jurisdiction.id = money_flow.jurisdiction_id
            WHERE money_flow.metadata->>'source_dataset' = ANY(%s)
              AND money_flow.is_current IS TRUE
            GROUP BY jurisdiction.name, jurisdiction.level, jurisdiction.code
            ORDER BY jurisdiction.level, jurisdiction.name
            """,
            (
                list(STATE_LOCAL_GIFT_FLOW_KINDS),
                list(STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS),
                list(STATE_LOCAL_MONEY_SOURCE_DATASETS),
            ),
        )
        vote_rows = _fetch_dicts(
            conn,
            """
            SELECT
                chamber,
                count(*) AS division_count,
                min(division_date) AS first_division_date,
                max(division_date) AS last_division_date
            FROM vote_division
            WHERE is_current IS TRUE
            GROUP BY chamber
            ORDER BY chamber
            """,
            (),
        )

    totals = influence_total_rows[0] if influence_total_rows else {}
    state_money_rows = [
        row
        for row in state_local_money_rows
        if row.get("jurisdiction_level") == "state"
    ]
    local_money_rows = [
        row
        for row in state_local_money_rows
        if row.get("jurisdiction_level") == "local"
    ]

    def sum_rows(rows: list[dict[str, Any]], key: str) -> Any:
        values = [row.get(key) for row in rows if row.get(key) is not None]
        return sum(values) if values else 0

    def jurisdiction_codes(rows: list[dict[str, Any]]) -> str | None:
        codes = [str(row.get("jurisdiction_code")) for row in rows if row.get("jurisdiction_code")]
        return ", ".join(sorted(codes)) if codes else None

    federal_status = "active"
    state_status = "partial" if state_money_rows else "planned"
    council_status = "partial" if local_money_rows else "planned"
    layers = [
        {
            "id": "federal_representatives",
            "label": "Federal representatives and office terms",
            "level": "federal",
            "status": federal_status,
            "attribution": "person/electorate/chamber",
            "counts": {
                "current_representatives": sum(
                    row["current_representative_count"] or 0 for row in representative_rows
                ),
                "office_terms": sum(row["office_term_count"] or 0 for row in representative_rows),
            },
        },
        {
            "id": "federal_boundaries",
            "label": "Federal House electorate boundaries",
            "level": "federal",
            "status": federal_status,
            "attribution": "electorate geometry",
            "counts": {
                "electorates": sum(row["electorate_count"] or 0 for row in boundary_rows),
                "boundaries": sum(row["boundary_count"] or 0 for row in boundary_rows),
            },
        },
        {
            "id": "federal_display_land_mask",
            "label": "Display land mask for interactive boundary clipping",
            "level": "federal",
            "status": "active" if display_land_mask_rows else "not_loaded",
            "attribution": "display-only geometry source; legal/electoral boundaries remain preserved",
            "counts": {
                "masks": len(display_land_mask_rows),
                "valid_geometries": sum(
                    1 for row in display_land_mask_rows if row.get("geometry_is_valid")
                ),
                "geometry_parts": sum(row.get("geometry_part_count") or 0 for row in display_land_mask_rows),
            },
        },
        {
            "id": "federal_influence_events",
            "label": "Disclosed money, gifts, interests, roles, and access context",
            "level": "federal",
            "status": federal_status,
            "attribution": "mixed: person, party, source entity, return-level",
            "counts": {
                "events": totals.get("event_count") or 0,
                "person_linked_events": totals.get("person_linked_event_count") or 0,
                "party_linked_events": totals.get("party_linked_event_count") or 0,
                "reported_amount_events": totals.get("reported_amount_event_count") or 0,
                "reported_amount_total": totals.get("reported_amount_total"),
            },
        },
        {
            "id": "federal_vote_divisions",
            "label": "Federal parliamentary divisions",
            "level": "federal",
            "status": "active" if vote_rows else "partial",
            "attribution": "person/chamber/topic after review",
            "counts": {
                "divisions": sum(row["division_count"] or 0 for row in vote_rows),
            },
        },
        {
            "id": "state_territory_disclosures",
            "label": "State and territory money/gift/lobbying records",
            "level": "state",
            "status": state_status,
            "jurisdiction": jurisdiction_codes(state_money_rows),
            "attribution": (
                "State/territory disclosure adapters active for the listed jurisdictions. "
                "Gift-in-kind rows are reported non-cash values; expenditure rows are "
                "campaign support, not personal receipt."
                if state_money_rows
                else "adapter-ready, not yet ingested"
            ),
            "counts": {
                "money_flow_rows": sum_rows(state_money_rows, "money_flow_count"),
                "gift_or_donation_rows": sum_rows(state_money_rows, "gift_or_donation_count"),
                "gift_in_kind_rows": sum_rows(state_money_rows, "gift_in_kind_count"),
                "electoral_expenditure_rows": sum_rows(
                    state_money_rows,
                    "electoral_expenditure_count",
                ),
                "reported_amount_events": sum_rows(
                    state_money_rows,
                    "reported_amount_event_count",
                ),
                "reported_amount_total": sum_rows(state_money_rows, "reported_amount_total"),
            },
        },
        {
            "id": "local_council_disclosures",
            "label": "Council/local disclosures and meeting records",
            "level": "council",
            "status": council_status,
            "jurisdiction": jurisdiction_codes(local_money_rows),
            "attribution": (
                "Queensland ECQ EDS local-government disclosure rows active; "
                "meeting/register adapters planned."
                if local_money_rows
                else "adapter-ready, not yet ingested"
            ),
            "counts": {
                "money_flow_rows": sum_rows(local_money_rows, "money_flow_count"),
                "gift_or_donation_rows": sum_rows(local_money_rows, "gift_or_donation_count"),
                "gift_in_kind_rows": sum_rows(local_money_rows, "gift_in_kind_count"),
                "electoral_expenditure_rows": sum_rows(
                    local_money_rows,
                    "electoral_expenditure_count",
                ),
                "reported_amount_events": sum_rows(
                    local_money_rows,
                    "reported_amount_event_count",
                ),
                "reported_amount_total": sum_rows(local_money_rows, "reported_amount_total"),
            },
        },
    ]
    partial_levels = [
        level
        for level, status in (("state", state_status), ("council", council_status))
        if status == "partial"
    ]

    return _jsonable(
        {
            "status": "ok",
            "active_country": "AU",
            "active_levels": ["federal"],
            "partial_levels": partial_levels,
            "planned_levels": [
                level
                for level, status in (("state", state_status), ("council", council_status))
                if status == "planned"
            ],
            "coverage_layers": layers,
            "source_documents": source_rows,
            "display_land_masks": display_land_mask_rows,
            "jurisdictions": jurisdiction_rows,
            "representatives_by_chamber": representative_rows,
            "boundaries_by_chamber": boundary_rows,
            "influence_events_by_family": influence_family_rows,
            "influence_event_totals": totals,
            "vote_divisions_by_chamber": vote_rows,
            "portable_model": {
                "supported_levels": [
                    "national/federal",
                    "state/territory/province/devolved",
                    "local/council/municipal",
                ],
                "core_dimensions": [
                    "actors",
                    "offices",
                    "boundaries",
                    "money_flows",
                    "gifts_hospitality_travel",
                    "interests_assets_roles",
                    "lobbying_access",
                    "votes_and_proceedings",
                    "entity_identifiers",
                    "industry_classifications",
                ],
                "planned_country_adapters": ["NZ", "UK", "US"],
            },
            "caveat": (
                "Coverage is source-family coverage, not evidentiary completeness. "
                "Map-linked counts are narrower than whole-database counts because many "
                "financial disclosures are party/entity/return-level records that cannot "
                "honestly be assigned to one MP or electorate without an explicit method."
            ),
        }
    )


def _qld_summary_rows(
    conn,
    *,
    role: str,
    flow_kind: str | tuple[str, ...],
    db_level: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if role not in {"source", "recipient"}:
        raise ValueError("role must be source or recipient")
    entity_column = "source_entity_id" if role == "source" else "recipient_entity_id"
    raw_name_column = "source_raw_name" if role == "source" else "recipient_raw_name"
    level_filter = "AND jurisdiction.level = %s" if db_level else ""
    flow_kinds = (flow_kind,) if isinstance(flow_kind, str) else flow_kind
    params: tuple[Any, ...] = (
        (list(STATE_LOCAL_MONEY_SOURCE_DATASETS), list(flow_kinds), db_level, limit)
        if db_level
        else (list(STATE_LOCAL_MONEY_SOURCE_DATASETS), list(flow_kinds), limit)
    )
    return _fetch_dicts(
        conn,
        f"""
        SELECT
            entity.id AS entity_id,
            COALESCE(entity.canonical_name, money_flow.{raw_name_column}) AS name,
            count(*) AS event_count,
            sum(money_flow.amount) AS reported_amount_total,
            COALESCE(max(identifier_counts.identifier_count), 0) AS identifier_count,
            bool_or(COALESCE(identifier_counts.identifier_count, 0) > 0)
                AS identifier_backed
        FROM money_flow
        JOIN jurisdiction
          ON jurisdiction.id = money_flow.jurisdiction_id
        LEFT JOIN entity
          ON entity.id = money_flow.{entity_column}
        LEFT JOIN LATERAL (
            SELECT count(*) AS identifier_count
            FROM entity_identifier
            WHERE entity_identifier.entity_id = entity.id
        ) identifier_counts ON TRUE
        WHERE money_flow.metadata->>'source_dataset' = ANY(%s)
          AND money_flow.is_current IS TRUE
          AND money_flow.metadata->>'flow_kind' = ANY(%s)
          {level_filter}
        GROUP BY entity.id, COALESCE(entity.canonical_name, money_flow.{raw_name_column})
        ORDER BY sum(money_flow.amount) DESC NULLS LAST, count(*) DESC, name
        LIMIT %s
        """,
        params,
    )


def _qld_context_summary_rows(
    conn,
    *,
    context_key: str,
    db_level: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    if context_key not in {"event", "local_electorate"}:
        raise ValueError("context_key must be event or local_electorate")
    level_filter = "AND jurisdiction.level = %s" if db_level else ""
    params: tuple[Any, ...] = (db_level, limit) if db_level else (limit,)
    return _fetch_dicts(
        conn,
        f"""
        SELECT
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'external_id'
                AS external_id,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'name'
                AS name,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'level'
                AS level,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'code'
                AS code,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'event_type'
                AS event_type,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'polling_date'
                AS polling_date,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'start_date'
                AS start_date,
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'date_caveat'
                AS date_caveat,
            count(*) AS money_flow_count,
            count(*) FILTER (
                WHERE money_flow.metadata->>'flow_kind' = 'qld_gift'
            ) AS gift_or_donation_count,
            count(*) FILTER (
                WHERE money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
            ) AS electoral_expenditure_count,
            CASE
                WHEN count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'qld_gift'
                ) = 0 THEN 0
                ELSE sum(money_flow.amount) FILTER (
                    WHERE money_flow.amount IS NOT NULL
                      AND money_flow.metadata->>'flow_kind' = 'qld_gift'
                )
            END AS gift_or_donation_reported_amount_total,
            CASE
                WHEN count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                ) = 0 THEN 0
                ELSE sum(money_flow.amount) FILTER (
                    WHERE money_flow.amount IS NOT NULL
                      AND money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                )
            END AS electoral_expenditure_reported_amount_total
        FROM money_flow
        JOIN jurisdiction
          ON jurisdiction.id = money_flow.jurisdiction_id
        WHERE money_flow.metadata->>'source_dataset' = 'qld_ecq_eds'
          AND money_flow.is_current IS TRUE
          AND money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'status' = 'matched'
          {level_filter}
        GROUP BY
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'external_id',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'name',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'level',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'code',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'event_type',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'polling_date',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'start_date',
            money_flow.metadata->'qld_ecq_context'->'{context_key}'->>'date_caveat'
        ORDER BY
            count(*) DESC,
            COALESCE(sum(money_flow.amount), 0) DESC,
            name
        LIMIT %s
        """,
        params,
    )


def _qld_recent_money_flow_rows(
    conn,
    *,
    db_level: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    level_filter = "AND jurisdiction.level = %s" if db_level else ""
    params: tuple[Any, ...] = (
        (list(STATE_LOCAL_MONEY_SOURCE_DATASETS), db_level, limit)
        if db_level
        else (list(STATE_LOCAL_MONEY_SOURCE_DATASETS), limit)
    )
    rows = _fetch_dicts(
        conn,
        f"""
        SELECT
            money_flow.id,
            jurisdiction.name AS jurisdiction_name,
            jurisdiction.level AS jurisdiction_level,
            jurisdiction.code AS jurisdiction_code,
            money_flow.metadata->>'source_dataset' AS source_dataset,
            money_flow.metadata->>'flow_kind' AS flow_kind,
            money_flow.receipt_type,
            money_flow.disclosure_category,
            money_flow.source_entity_id,
            COALESCE(source_entity.canonical_name, money_flow.source_raw_name)
                AS source_name,
            money_flow.recipient_entity_id,
            COALESCE(recipient_entity.canonical_name, money_flow.recipient_raw_name)
                AS recipient_name,
            money_flow.amount,
            money_flow.currency,
            money_flow.financial_year,
            money_flow.date_received,
            money_flow.date_reported,
            money_flow.source_row_ref,
            money_flow.original_text,
            money_flow.confidence,
            money_flow.metadata->>'transaction_kind' AS transaction_kind,
            COALESCE(
                money_flow.metadata->>'description_of_goods_or_services',
                money_flow.metadata->>'description'
            )
                AS description_of_goods_or_services,
            money_flow.metadata->>'purpose_of_expenditure' AS purpose_of_expenditure,
            money_flow.metadata->>'public_amount_counting_role' AS public_amount_counting_role,
            money_flow.metadata->'campaign_support_attribution' AS campaign_support_attribution,
            EXISTS (
                SELECT 1
                FROM entity_identifier
                WHERE entity_identifier.entity_id = money_flow.source_entity_id
            ) AS source_identifier_backed,
            EXISTS (
                SELECT 1
                FROM entity_identifier
                WHERE entity_identifier.entity_id = money_flow.recipient_entity_id
            ) AS recipient_identifier_backed,
            money_flow.metadata->'qld_ecq_context'->'event'->>'external_id'
                AS event_external_id,
            money_flow.metadata->'qld_ecq_context'->'event'->>'name'
                AS event_name,
            money_flow.metadata->'qld_ecq_context'->'event'->>'polling_date'
                AS event_polling_date,
            money_flow.metadata->'qld_ecq_context'->'local_electorate'->>'external_id'
                AS local_electorate_external_id,
            money_flow.metadata->'qld_ecq_context'->'local_electorate'->>'name'
                AS local_electorate_name,
            money_flow.source_document_id,
            source_document.source_id,
            source_document.source_name AS source_document_name,
            source_document.url AS source_url,
            source_document.final_url AS source_final_url,
            source_document.sha256 AS source_document_sha256,
            source_document.fetched_at AS source_document_fetched_at
        FROM money_flow
        JOIN jurisdiction
          ON jurisdiction.id = money_flow.jurisdiction_id
        JOIN source_document
          ON source_document.id = money_flow.source_document_id
        LEFT JOIN entity source_entity
          ON source_entity.id = money_flow.source_entity_id
        LEFT JOIN entity recipient_entity
          ON recipient_entity.id = money_flow.recipient_entity_id
        WHERE money_flow.metadata->>'source_dataset' = ANY(%s)
          AND money_flow.is_current IS TRUE
          {level_filter}
        ORDER BY
            COALESCE(money_flow.date_received, money_flow.date_reported) DESC NULLS LAST,
            money_flow.id DESC
        LIMIT %s
        """,
        params,
    )
    return _with_state_local_record_cursors(rows, db_level=db_level, flow_kind=None)


def get_state_local_records(
    *,
    level: str | None = None,
    flow_kind: str | None = None,
    cursor: str | None = None,
    limit: int = 25,
    database_url: str | None = None,
) -> dict[str, Any]:
    level_map = {"state": "state", "council": "local", "local": "local"}
    db_level = level_map.get(level or "") if level else None
    if level and db_level is None:
        raise ValueError("level must be state, council, local, or omitted")
    if flow_kind is not None and flow_kind not in STATE_LOCAL_RECORD_FLOW_KINDS:
        raise ValueError(
            "flow_kind must be one of "
            f"{', '.join(sorted(STATE_LOCAL_RECORD_FLOW_KINDS))}, or omitted"
        )
    if limit < 1 or limit > 100:
        raise ValueError("State/local record page limit must be between 1 and 100.")

    cursor_values = (
        _decode_state_local_record_cursor(cursor, db_level=db_level, flow_kind=flow_kind)
        if cursor
        else None
    )
    with connect(database_url) as conn:
        where_clauses = [
            "money_flow.metadata->>'source_dataset' = ANY(%s)",
            "money_flow.is_current IS TRUE",
        ]
        params: list[Any] = [list(STATE_LOCAL_MONEY_SOURCE_DATASETS)]
        if db_level:
            where_clauses.append("jurisdiction.level = %s")
            params.append(db_level)
        if flow_kind:
            where_clauses.append("money_flow.metadata->>'flow_kind' = %s")
            params.append(flow_kind)
        where_sql = "\n          AND ".join(where_clauses)
        count_rows = _fetch_dicts(
            conn,
            f"""
            SELECT count(*) AS total_count
            FROM money_flow
            JOIN jurisdiction
              ON jurisdiction.id = money_flow.jurisdiction_id
            WHERE {where_sql}
            """,
            tuple(params),
        )
        page_params = list(params)
        cursor_sql = ""
        if cursor_values is not None:
            cursor_sql = """
          AND (
              COALESCE(money_flow.date_received, money_flow.date_reported, DATE '0001-01-01'),
              money_flow.id
          ) < (%s, %s)
            """
            page_params.extend(cursor_values)
        page_params.append(limit + 1)
        rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                money_flow.id,
                jurisdiction.name AS jurisdiction_name,
                jurisdiction.level AS jurisdiction_level,
                jurisdiction.code AS jurisdiction_code,
                money_flow.metadata->>'source_dataset' AS source_dataset,
                money_flow.metadata->>'flow_kind' AS flow_kind,
                money_flow.receipt_type,
                money_flow.disclosure_category,
                money_flow.source_entity_id,
                COALESCE(source_entity.canonical_name, money_flow.source_raw_name)
                    AS source_name,
                money_flow.recipient_entity_id,
                COALESCE(recipient_entity.canonical_name, money_flow.recipient_raw_name)
                    AS recipient_name,
                money_flow.amount,
                money_flow.currency,
                money_flow.financial_year,
                money_flow.date_received,
                money_flow.date_reported,
                money_flow.source_row_ref,
                money_flow.original_text,
                money_flow.confidence,
                money_flow.metadata->>'transaction_kind' AS transaction_kind,
                COALESCE(
                    money_flow.metadata->>'description_of_goods_or_services',
                    money_flow.metadata->>'description'
                )
                    AS description_of_goods_or_services,
                money_flow.metadata->>'purpose_of_expenditure' AS purpose_of_expenditure,
                money_flow.metadata->>'public_amount_counting_role'
                    AS public_amount_counting_role,
                money_flow.metadata->>'date_caveat' AS date_caveat,
                money_flow.metadata->>'caveat' AS record_caveat,
                money_flow.metadata->'campaign_support_attribution'
                    AS campaign_support_attribution,
                money_flow.metadata->'public_funding_context'
                    AS public_funding_context,
                EXISTS (
                    SELECT 1
                    FROM entity_identifier
                    WHERE entity_identifier.entity_id = money_flow.source_entity_id
                ) AS source_identifier_backed,
                EXISTS (
                    SELECT 1
                    FROM entity_identifier
                    WHERE entity_identifier.entity_id = money_flow.recipient_entity_id
                ) AS recipient_identifier_backed,
                money_flow.metadata->'qld_ecq_context'->'event'->>'external_id'
                    AS event_external_id,
                money_flow.metadata->'qld_ecq_context'->'event'->>'name'
                    AS event_name,
                money_flow.metadata->'qld_ecq_context'->'event'->>'polling_date'
                    AS event_polling_date,
                money_flow.metadata->'qld_ecq_context'->'local_electorate'->>'external_id'
                    AS local_electorate_external_id,
                money_flow.metadata->'qld_ecq_context'->'local_electorate'->>'name'
                    AS local_electorate_name,
                money_flow.source_document_id,
                source_document.source_id,
                source_document.source_name AS source_document_name,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url,
                source_document.sha256 AS source_document_sha256,
                source_document.fetched_at AS source_document_fetched_at
            FROM money_flow
            JOIN jurisdiction
              ON jurisdiction.id = money_flow.jurisdiction_id
            JOIN source_document
              ON source_document.id = money_flow.source_document_id
            LEFT JOIN entity source_entity
              ON source_entity.id = money_flow.source_entity_id
            LEFT JOIN entity recipient_entity
              ON recipient_entity.id = money_flow.recipient_entity_id
            WHERE {where_sql}
            {cursor_sql}
            ORDER BY
                COALESCE(money_flow.date_received, money_flow.date_reported, DATE '0001-01-01') DESC,
                money_flow.id DESC
            LIMIT %s
            """,
            tuple(page_params),
        )
    rows = _with_state_local_record_cursors(rows, db_level=db_level, flow_kind=flow_kind)
    has_more = len(rows) > limit
    records = rows[:limit]
    return _jsonable(
        {
            "status": "ok",
            "source_family": "state_local_disclosures",
            "jurisdiction": "Loaded state/local coverage",
            "requested_level": level or "all",
            "db_level": db_level or "all",
            "flow_kind": flow_kind,
            "records": records,
            "record_count": len(records),
            "total_count": count_rows[0]["total_count"] if count_rows else 0,
            "limit": limit,
            "has_more": has_more,
            "next_cursor": records[-1]["pagination_cursor"] if has_more and records else None,
            "caveat": (
                "State/local record pages expose current source rows only. Gift, "
                "gift-in-kind, expenditure, and public-funding rows are different "
                "evidence families. ACT gift-in-kind amounts are reported non-cash "
                "values; Queensland expenditure is campaign-support context, not "
                "personal receipt; VEC funding-register rows are public "
                "funding/admin/policy context, not private donations or personal "
                "income, and some VEC dates are election-day or calendar-period "
                "context dates rather than transaction dates. Context labels are "
                "disclosure metadata, not candidate/councillor attribution unless "
                "another source supports that link. Records are not claims of "
                "wrongdoing, causation, quid pro quo, or improper influence."
            ),
        }
    )


def get_state_local_summary(
    *,
    level: str | None = None,
    limit: int = 8,
    database_url: str | None = None,
) -> dict[str, Any]:
    level_map = {"state": "state", "council": "local", "local": "local"}
    db_level = level_map.get(level or "") if level else None
    if level and db_level is None:
        raise ValueError("level must be state, council, local, or omitted")

    with connect(database_url) as conn:
        level_filter = "AND jurisdiction.level = %s" if db_level else ""
        params: tuple[Any, ...] = (db_level,) if db_level else ()
        totals_rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                jurisdiction.name AS jurisdiction_name,
                jurisdiction.level AS jurisdiction_level,
                jurisdiction.code AS jurisdiction_code,
                count(*) AS money_flow_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                ) AS gift_or_donation_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'act_gift_in_kind'
                ) AS gift_in_kind_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                ) AS electoral_expenditure_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                ) AS public_funding_count,
                CASE
                    WHEN count(*) FILTER (
                        WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                    ) = 0 THEN 0
                    ELSE sum(money_flow.amount) FILTER (
                        WHERE money_flow.amount IS NOT NULL
                          AND money_flow.metadata->>'flow_kind' = ANY(%s)
                    )
                END AS gift_or_donation_reported_amount_total,
                CASE
                    WHEN count(*) FILTER (
                        WHERE money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                    ) = 0 THEN 0
                    ELSE sum(money_flow.amount) FILTER (
                        WHERE money_flow.amount IS NOT NULL
                          AND money_flow.metadata->>'flow_kind' = 'qld_electoral_expenditure'
                    )
                END AS electoral_expenditure_reported_amount_total,
                CASE
                    WHEN count(*) FILTER (
                        WHERE money_flow.metadata->>'flow_kind' = ANY(%s)
                    ) = 0 THEN 0
                    ELSE sum(money_flow.amount) FILTER (
                        WHERE money_flow.amount IS NOT NULL
                          AND money_flow.metadata->>'flow_kind' = ANY(%s)
                    )
                END AS public_funding_reported_amount_total,
                count(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM entity_identifier
                        WHERE entity_identifier.entity_id = money_flow.source_entity_id
                    )
                ) AS source_identifier_backed_count,
                count(*) FILTER (
                    WHERE EXISTS (
                        SELECT 1
                        FROM entity_identifier
                        WHERE entity_identifier.entity_id = money_flow.recipient_entity_id
                    )
                ) AS recipient_identifier_backed_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->'qld_ecq_context'->'event'->>'status' = 'matched'
                ) AS event_context_backed_count,
                count(*) FILTER (
                    WHERE money_flow.metadata->'qld_ecq_context'->'local_electorate'->>'status'
                        = 'matched'
                ) AS local_electorate_context_backed_count
            FROM money_flow
            JOIN jurisdiction
              ON jurisdiction.id = money_flow.jurisdiction_id
            WHERE money_flow.metadata->>'source_dataset' = ANY(%s)
              AND money_flow.is_current IS TRUE
              {level_filter}
            GROUP BY jurisdiction.name, jurisdiction.level, jurisdiction.code
            ORDER BY jurisdiction.level, jurisdiction.name
            """,
            (
                list(STATE_LOCAL_GIFT_FLOW_KINDS),
                list(STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS),
                list(STATE_LOCAL_GIFT_FLOW_KINDS),
                list(STATE_LOCAL_GIFT_FLOW_KINDS),
                list(STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS),
                list(STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS),
                list(STATE_LOCAL_MONEY_SOURCE_DATASETS),
                *params,
            ),
        )
        freshness_rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                count(DISTINCT source_document.id) AS source_document_count,
                max(source_document.fetched_at) AS latest_source_fetched_at
            FROM money_flow
            JOIN jurisdiction
              ON jurisdiction.id = money_flow.jurisdiction_id
            JOIN source_document
              ON source_document.id = money_flow.source_document_id
            WHERE money_flow.metadata->>'source_dataset' = ANY(%s)
              AND money_flow.is_current IS TRUE
              {level_filter}
            """,
            (list(STATE_LOCAL_MONEY_SOURCE_DATASETS), *params),
        )
        top_gift_donors = _qld_summary_rows(
            conn,
            role="source",
            flow_kind=STATE_LOCAL_GIFT_FLOW_KINDS,
            db_level=db_level,
            limit=limit,
        )
        top_gift_recipients = _qld_summary_rows(
            conn,
            role="recipient",
            flow_kind=STATE_LOCAL_GIFT_FLOW_KINDS,
            db_level=db_level,
            limit=limit,
        )
        top_expenditure_actors = _qld_summary_rows(
            conn,
            role="source",
            flow_kind="qld_electoral_expenditure",
            db_level=db_level,
            limit=limit,
        )
        top_public_funding_recipients = _qld_summary_rows(
            conn,
            role="recipient",
            flow_kind=STATE_LOCAL_PUBLIC_FUNDING_FLOW_KINDS,
            db_level=db_level,
            limit=limit,
        )
        top_events = _qld_context_summary_rows(
            conn,
            context_key="event",
            db_level=db_level,
            limit=limit,
        )
        top_local_electorates = _qld_context_summary_rows(
            conn,
            context_key="local_electorate",
            db_level=db_level,
            limit=limit,
        )
        recent_records = _qld_recent_money_flow_rows(
            conn,
            db_level=db_level,
            limit=limit,
        )
        aggregate_context_totals: list[dict[str, Any]] = []
        top_aggregate_donor_locations: list[dict[str, Any]] = []
        if _table_exists(conn, "aggregate_context_observation"):
            aggregate_context_totals = _fetch_dicts(
                conn,
                f"""
                SELECT
                    jurisdiction.name AS jurisdiction_name,
                    jurisdiction.level AS jurisdiction_level,
                    jurisdiction.code AS jurisdiction_code,
                    aggregate_context_observation.source_dataset,
                    aggregate_context_observation.context_type,
                    count(*) AS aggregate_context_count,
                    sum(aggregate_context_observation.record_count) AS source_record_count,
                    sum(aggregate_context_observation.amount) FILTER (
                        WHERE aggregate_context_observation.amount_status = 'reported'
                    ) AS reported_amount_total,
                    min(aggregate_context_observation.reporting_period_start)
                        AS reporting_period_start,
                    max(aggregate_context_observation.reporting_period_end)
                        AS reporting_period_end,
                    count(DISTINCT aggregate_context_observation.source_document_id)
                        AS source_document_count,
                    max(source_document.fetched_at) AS latest_source_fetched_at
                FROM aggregate_context_observation
                JOIN jurisdiction
                  ON jurisdiction.id = aggregate_context_observation.jurisdiction_id
                LEFT JOIN source_document
                  ON source_document.id = aggregate_context_observation.source_document_id
                WHERE aggregate_context_observation.source_dataset = 'nsw_electoral_disclosures'
                  AND aggregate_context_observation.is_current IS TRUE
                  {level_filter}
                GROUP BY
                    jurisdiction.name,
                    jurisdiction.level,
                    jurisdiction.code,
                    aggregate_context_observation.source_dataset,
                    aggregate_context_observation.context_type
                ORDER BY jurisdiction.name, aggregate_context_observation.context_type
                """,
                params,
            )
            top_aggregate_donor_locations = _fetch_dicts(
                conn,
                f"""
                SELECT
                    aggregate_context_observation.id,
                    jurisdiction.name AS jurisdiction_name,
                    jurisdiction.level AS jurisdiction_level,
                    jurisdiction.code AS jurisdiction_code,
                    aggregate_context_observation.source_dataset,
                    aggregate_context_observation.context_type,
                    aggregate_context_observation.geography_type,
                    aggregate_context_observation.geography_name,
                    aggregate_context_observation.amount AS reported_amount_total,
                    aggregate_context_observation.record_count AS source_record_count,
                    aggregate_context_observation.reporting_period_start,
                    aggregate_context_observation.reporting_period_end,
                    aggregate_context_observation.attribution_scope,
                    aggregate_context_observation.caveat,
                    source_document.id AS source_document_id,
                    source_document.source_name AS source_document_name,
                    source_document.url AS source_url,
                    source_document.final_url AS source_final_url,
                    source_document.sha256 AS source_document_sha256,
                    source_document.fetched_at AS source_document_fetched_at
                FROM aggregate_context_observation
                JOIN jurisdiction
                  ON jurisdiction.id = aggregate_context_observation.jurisdiction_id
                LEFT JOIN source_document
                  ON source_document.id = aggregate_context_observation.source_document_id
                WHERE aggregate_context_observation.source_dataset = 'nsw_electoral_disclosures'
                  AND aggregate_context_observation.is_current IS TRUE
                  {level_filter}
                ORDER BY aggregate_context_observation.amount DESC NULLS LAST,
                    aggregate_context_observation.record_count DESC NULLS LAST,
                    aggregate_context_observation.geography_name
                LIMIT %s
                """,
                (*params, limit),
            )

    return _jsonable(
        {
            "status": "ok",
            "source_family": "state_local_disclosures",
            "jurisdiction": "Loaded state/local coverage",
            "requested_level": level or "all",
            "db_level": db_level or "all",
            "totals_by_level": totals_rows,
            "source_document_count": (
                freshness_rows[0]["source_document_count"] if freshness_rows else 0
            ),
            "latest_source_fetched_at": (
                freshness_rows[0]["latest_source_fetched_at"] if freshness_rows else None
            ),
            "top_gift_donors": top_gift_donors,
            "top_gift_recipients": top_gift_recipients,
            "top_expenditure_actors": top_expenditure_actors,
            "top_public_funding_recipients": top_public_funding_recipients,
            "top_events": top_events,
            "top_local_electorates": top_local_electorates,
            "recent_records": recent_records,
            "aggregate_context_totals": aggregate_context_totals,
            "top_aggregate_donor_locations": top_aggregate_donor_locations,
            "aggregate_context_caveat": (
                "NSW aggregate context rows are official donor-location totals from a "
                "static NSW Electoral Commission heatmap. They are not donor-recipient "
                "money-flow rows and must not be attributed to a representative, "
                "candidate, councillor, or party unless another source supports that link. "
                "The source caveat says the map does not show recipient locations and "
                "may exclude donor locations that cannot be mapped. NSWEC material is "
                "used under CC BY 4.0 unless otherwise noted; no endorsement is implied."
            ),
            "caveat": (
                "State/local rows are disclosure records from implemented jurisdiction "
                "adapters. Queensland gift/donation rows and ACT gift-of-money rows are "
                "source-backed money records; ACT gift-in-kind rows are reported non-cash "
                "values; Queensland electoral expenditure rows are campaign-support "
                "context and not personal receipt; VEC funding-register rows are public "
                "funding/admin/policy-funding context, not private donations or personal "
                "income, and VEC says affected material is under review after Hopper & "
                "Anor v State of Victoria [2026] HCA 11. Event, local-electorate, "
                "candidate, or party labels are disclosure metadata and do not attribute "
                "money or campaign expenditure to a candidate, councillor, or MP unless "
                "a separate source supports that link."
            ),
        }
    )


def _get_senate_map(
    *,
    state: str | None = None,
    boundary_set: str | None = None,
    include_geometry: bool = True,
    simplify_tolerance: float = 0.01,
    geometry_role: str = "display",
    database_url: str | None = None,
) -> dict[str, Any]:
    geometry_expression = (
        """
        ST_AsGeoJSON(
            ST_Multi(state_boundary.geom),
            6
        ) AS geometry_geojson
        """
        if include_geometry
        else "NULL::TEXT AS geometry_geojson"
    )
    geometry_column = (
        "COALESCE(display_boundary.geom, boundary.geom)"
        if geometry_role == "display"
        else "boundary.geom"
    )
    display_join_filter = (
        "AND display_boundary.geometry_role = 'land_clipped_display'"
        if geometry_role == "display"
        else "AND FALSE"
    )
    state_geometry_aggregate = (
        """
        ST_Multi(
            ST_CollectionExtract(
                ST_Collect(ST_SimplifyPreserveTopology(geom, %s)),
                3
            )
        ) AS geom
        """
        if include_geometry
        else "NULL::geometry AS geom"
    )
    params: list[Any] = []
    boundary_filter = ""
    if boundary_set:
        boundary_filter = "AND boundary.boundary_set = %s"
        params.append(boundary_set)
    params.extend([boundary_set, boundary_set])
    if include_geometry:
        params.append(simplify_tolerance)
    state_filter = ""
    if state:
        state_filter = "AND upper(electorate.state_or_territory) = %s"
        params.append(state)
    boundary_required_filter = (
        "AND COALESCE(state_boundary.boundary_count, 0) > 0" if boundary_set else ""
    )

    with connect(database_url) as conn:
        rows = _fetch_dicts(
            conn,
            f"""
            WITH boundary_rows AS (
                SELECT
                    boundary.id,
                    {_state_code_sql(
                        "COALESCE(NULLIF(house_electorate.state_or_territory, ''), NULLIF(house_term.metadata->>'state', ''))"
                    )} AS state_code,
                    boundary.boundary_set,
                    boundary.valid_from,
                    boundary.valid_to,
                    {geometry_column} AS geom,
                    display_boundary.id IS NOT NULL AS has_display_geometry
                FROM electorate_boundary boundary
                JOIN electorate house_electorate
                  ON house_electorate.id = boundary.electorate_id
                 AND house_electorate.chamber = 'house'
                LEFT JOIN electorate_boundary_display_geometry display_boundary
                  ON display_boundary.electorate_boundary_id = boundary.id
                 {display_join_filter}
                LEFT JOIN office_term house_term
                  ON house_term.electorate_id = house_electorate.id
                 AND house_term.term_end IS NULL
                WHERE TRUE
                {boundary_filter}
                  AND (
                    %s::text IS NOT NULL
                    OR boundary.valid_from IS NULL
                    OR boundary.valid_from <= CURRENT_DATE
                  )
                  AND (
                    %s::text IS NOT NULL
                    OR boundary.valid_to IS NULL
                    OR boundary.valid_to >= CURRENT_DATE
                  )
            ),
            state_boundaries AS (
                SELECT
                    state_code,
                    boundary_set,
                    min(valid_from) AS valid_from,
                    max(valid_to) AS valid_to,
                    count(*) AS boundary_count,
                    bool_or(has_display_geometry) AS has_display_geometry,
                    {state_geometry_aggregate}
                FROM boundary_rows
                WHERE state_code IS NOT NULL
                GROUP BY state_code, boundary_set
            ),
            selected_state_boundaries AS (
                SELECT DISTINCT ON (state_code)
                    state_code,
                    boundary_set,
                    valid_from,
                    valid_to,
                    boundary_count,
                    has_display_geometry,
                    geom
                FROM state_boundaries
                ORDER BY state_code, valid_from DESC NULLS LAST, boundary_set
            )
            SELECT
                electorate.id AS electorate_id,
                electorate.name AS electorate_name,
                electorate.chamber,
                electorate.state_or_territory,
                state_boundary.boundary_set,
                state_boundary.valid_from AS boundary_valid_from,
                state_boundary.valid_to AS boundary_valid_to,
                COALESCE(state_boundary.boundary_count, 0) > 0 AS has_boundary,
                CASE
                    WHEN COALESCE(state_boundary.has_display_geometry, FALSE) THEN 'display'
                    ELSE 'source'
                END AS map_geometry_role,
                NULL::BIGINT AS representative_id,
                NULL::TEXT AS representative_name,
                NULL::BIGINT AS party_id,
                NULL::TEXT AS party_name,
                NULL::TEXT AS party_short_name,
                reps.current_representative_count,
                reps.current_representatives,
                reps.party_breakdown,
                'state_territory_composite_from_house_boundaries'::TEXT AS map_geometry_scope,
                COALESCE(influence_summary.influence_event_count, 0)
                    AS current_representative_lifetime_influence_event_count,
                COALESCE(influence_summary.money_event_count, 0)
                    AS current_representative_lifetime_money_event_count,
                COALESCE(influence_summary.benefit_event_count, 0)
                    AS current_representative_lifetime_benefit_event_count,
                COALESCE(influence_summary.campaign_support_event_count, 0)
                    AS current_representative_lifetime_campaign_support_event_count,
                COALESCE(influence_summary.needs_review_event_count, 0)
                    AS current_representative_needs_review_event_count,
                COALESCE(influence_summary.official_record_event_count, 0)
                    AS current_representative_official_record_event_count,
                influence_summary.reported_amount_total
                    AS current_representative_lifetime_reported_amount_total,
                influence_summary.campaign_support_reported_amount_total
                    AS current_representative_campaign_support_reported_total,
                {geometry_expression}
            FROM electorate
            JOIN LATERAL (
                SELECT
                    count(person.id) AS current_representative_count,
                    COALESCE(
                        jsonb_agg(
                            jsonb_build_object(
                                'person_id', person.id,
                                'display_name', person.display_name,
                                'party_id', party.id,
                                'party_name', party.name,
                                'party_short_name', party.short_name,
                                'chamber', office_term.chamber,
                                'term_start', office_term.term_start
                            )
                            ORDER BY person.display_name
                        ) FILTER (WHERE person.id IS NOT NULL),
                        '[]'::jsonb
                    ) AS current_representatives,
                    COALESCE(
                        (
                            SELECT jsonb_agg(
                                jsonb_build_object(
                                    'party_id', party_counts.party_id,
                                    'party_name', party_counts.party_name,
                                    'party_short_name', party_counts.party_short_name,
                                    'representative_count', party_counts.representative_count
                                )
                                ORDER BY party_counts.representative_count DESC,
                                    party_counts.party_name
                            )
                            FROM (
                                SELECT
                                    party.id AS party_id,
                                    party.name AS party_name,
                                    party.short_name AS party_short_name,
                                    count(DISTINCT person.id) AS representative_count
                                FROM office_term
                                JOIN person ON person.id = office_term.person_id
                                LEFT JOIN party ON party.id = office_term.party_id
                                WHERE office_term.electorate_id = electorate.id
                                  AND office_term.term_end IS NULL
                                GROUP BY party.id, party.name, party.short_name
                            ) party_counts
                        ),
                        '[]'::jsonb
                    ) AS party_breakdown
                FROM office_term
                JOIN person ON person.id = office_term.person_id
                LEFT JOIN party ON party.id = office_term.party_id
                WHERE office_term.electorate_id = electorate.id
                  AND office_term.term_end IS NULL
            ) reps ON reps.current_representative_count > 0
            LEFT JOIN selected_state_boundaries state_boundary
              ON state_boundary.state_code = electorate.state_or_territory
            LEFT JOIN LATERAL (
                SELECT
                    count(influence_event.id) AS influence_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'money'
                    ) AS money_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'benefit'
                    ) AS benefit_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.event_family = 'campaign_support'
                    ) AS campaign_support_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'needs_review'
                    ) AS needs_review_event_count,
                    count(influence_event.id) FILTER (
                        WHERE influence_event.evidence_status IN (
                            'official_record',
                            'official_record_parsed'
                        )
                    ) AS official_record_event_count,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_total,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family = 'campaign_support'
                    ) AS campaign_support_reported_amount_total
                FROM (
                    SELECT DISTINCT office_term.person_id
                    FROM office_term
                    WHERE office_term.electorate_id = electorate.id
                      AND office_term.term_end IS NULL
                ) current_people
                JOIN influence_event
                  ON influence_event.recipient_person_id = current_people.person_id
                WHERE influence_event.review_status <> 'rejected'
            ) influence_summary ON TRUE
            WHERE electorate.chamber = 'senate'
              AND NULLIF(electorate.state_or_territory, '') IS NOT NULL
              {state_filter}
              {boundary_required_filter}
            ORDER BY electorate.state_or_territory, electorate.name
            """,
            tuple(params),
        )

    features = []
    for row in rows:
        geometry = _geometry_from_geojson(row.pop("geometry_geojson"))
        electorate_id = row.pop("electorate_id")
        electorate_name = row.pop("electorate_name")
        features.append(
            {
                "type": "Feature",
                "id": electorate_id,
                "geometry": geometry,
                "properties": _jsonable(
                    {
                        "electorate_id": electorate_id,
                        "electorate_name": electorate_name,
                        **row,
                    }
                ),
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
        "feature_count": len(features),
        "filters": {
            "chamber": "senate",
            "state": state,
            "boundary_set": boundary_set,
            "include_geometry": include_geometry,
            "simplify_tolerance": simplify_tolerance,
            "geometry_role": geometry_role,
            "map_geometry_scope": "state_territory_composite_from_house_boundaries",
        },
        "caveat": (
            f"{MAP_CAVEAT} Senate map geometries are state/territory features "
            "derived from source-backed federal House electorate boundaries; "
            "senator lists and counts come from Senate office records."
        ),
    }


def get_representative_evidence_events(
    person_id: int,
    *,
    group: str = "direct",
    event_family: str | None = None,
    cursor: str | None = None,
    limit: int = 25,
    database_url: str | None = None,
) -> dict[str, Any]:
    if group not in REPRESENTATIVE_EVIDENCE_GROUPS:
        raise ValueError("Evidence group must be direct or campaign_support.")
    if limit < 1 or limit > 100:
        raise ValueError("Evidence page limit must be between 1 and 100.")
    if group == "campaign_support" and event_family is not None:
        raise ValueError("event_family filtering is available only for direct evidence pages.")
    if group == "direct" and event_family == "campaign_support":
        raise ValueError("Use group=campaign_support for campaign-support records.")

    cursor_values = _decode_representative_evidence_cursor(cursor) if cursor else None
    with connect(database_url) as conn:
        person_rows = _fetch_dicts(conn, "SELECT id FROM person WHERE id = %s", (person_id,))
        if not person_rows:
            return {}

        where_clauses = [
            "influence_event.recipient_person_id = %s",
            "influence_event.review_status <> 'rejected'",
        ]
        params: list[Any] = [person_id]
        if group == "campaign_support":
            where_clauses.append("influence_event.event_family = 'campaign_support'")
        else:
            where_clauses.append("influence_event.event_family <> 'campaign_support'")
        if event_family is not None:
            where_clauses.append("influence_event.event_family = %s")
            params.append(event_family)

        where_sql = "\n              AND ".join(where_clauses)
        count_rows = _fetch_dicts(
            conn,
            f"""
            SELECT count(*) AS total_count
            FROM influence_event
            WHERE {where_sql}
            """,
            tuple(params),
        )
        page_params = list(params)
        cursor_sql = ""
        if cursor_values is not None:
            cursor_sql = """
              AND (
                  COALESCE(influence_event.event_date, DATE '0001-01-01'),
                  COALESCE(influence_event.date_reported, DATE '0001-01-01'),
                  influence_event.id
              ) < (%s, %s, %s)
            """
            page_params.extend(cursor_values)
        page_params.append(limit + 1)
        rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                influence_event.id,
                influence_event.event_family,
                influence_event.event_type,
                influence_event.event_subtype,
                influence_event.source_raw_name,
                source_entity.canonical_name AS source_entity_name,
                influence_event.amount,
                influence_event.currency,
                influence_event.amount_status,
                influence_event.event_date,
                influence_event.reporting_period,
                influence_event.date_reported,
                influence_event.description,
                influence_event.disclosure_system,
                influence_event.disclosure_threshold,
                influence_event.evidence_status,
                influence_event.extraction_method,
                influence_event.review_status,
                influence_event.missing_data_flags,
                influence_event.source_ref,
                source_document.source_id,
                source_document.source_name,
                source_document.source_type,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            JOIN source_document
              ON source_document.id = influence_event.source_document_id
            WHERE {where_sql}
            {cursor_sql}
            ORDER BY
                COALESCE(influence_event.event_date, DATE '0001-01-01') DESC,
                COALESCE(influence_event.date_reported, DATE '0001-01-01') DESC,
                influence_event.id DESC
            LIMIT %s
            """,
            tuple(page_params),
        )

    rows = _with_representative_evidence_cursors(rows)
    has_more = len(rows) > limit
    events = rows[:limit]
    return _jsonable(
        {
            "person_id": person_id,
            "group": group,
            "event_family": event_family,
            "events": events,
            "event_count": len(events),
            "total_count": count_rows[0]["total_count"] if count_rows else 0,
            "limit": limit,
            "has_more": has_more,
            "next_cursor": events[-1]["pagination_cursor"] if has_more and events else None,
            "caveat": (
                REPRESENTATIVE_EVIDENCE_CAMPAIGN_CAVEAT
                if group == "campaign_support"
                else REPRESENTATIVE_EVIDENCE_DIRECT_CAVEAT
            ),
        }
    )


def get_representative_profile(person_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        person_rows = _fetch_dicts(
            conn,
            """
            SELECT
                person.id,
                person.external_key,
                person.display_name,
                person.canonical_name,
                person.metadata,
                source_document.final_url AS source_final_url,
                source_document.url AS source_url
            FROM person
            LEFT JOIN source_document
              ON source_document.id = person.source_document_id
            WHERE person.id = %s
            """,
            (person_id,),
        )
        if not person_rows:
            return {}
        terms = _fetch_dicts(
            conn,
            f"""
            SELECT
                office_term.chamber,
                office_term.term_start,
                office_term.term_end,
                electorate.id AS electorate_id,
                electorate.name AS electorate_name,
                {_state_code_sql(
                    "COALESCE(NULLIF(electorate.state_or_territory, ''), NULLIF(office_term.metadata->>'state', ''))"
                )} AS state_or_territory,
                party.id AS party_id,
                party.name AS party_name
            FROM office_term
            LEFT JOIN electorate ON electorate.id = office_term.electorate_id
            LEFT JOIN party ON party.id = office_term.party_id
            WHERE office_term.person_id = %s
            ORDER BY office_term.term_end NULLS FIRST, office_term.term_start DESC NULLS LAST
            """,
            (person_id,),
        )
        event_summary = _fetch_dicts(
            conn,
            """
            SELECT
                event_family,
                count(*) AS event_count,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_total,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE recipient_person_id = %s
              AND review_status <> 'rejected'
              AND event_family <> 'campaign_support'
            GROUP BY event_family
            ORDER BY event_count DESC, event_family
            """,
            (person_id,),
        )
        recent_events = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.id,
                influence_event.event_family,
                influence_event.event_type,
                influence_event.event_subtype,
                influence_event.source_raw_name,
                source_entity.canonical_name AS source_entity_name,
                influence_event.amount,
                influence_event.currency,
                influence_event.amount_status,
                influence_event.event_date,
                influence_event.reporting_period,
                influence_event.date_reported,
                influence_event.description,
                influence_event.disclosure_system,
                influence_event.disclosure_threshold,
                influence_event.evidence_status,
                influence_event.extraction_method,
                influence_event.review_status,
                influence_event.missing_data_flags,
                influence_event.source_ref,
                source_document.source_id,
                source_document.source_name,
                source_document.source_type,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            JOIN source_document
              ON source_document.id = influence_event.source_document_id
            WHERE influence_event.recipient_person_id = %s
              AND influence_event.review_status <> 'rejected'
              AND influence_event.event_family <> 'campaign_support'
            ORDER BY
                influence_event.event_date DESC NULLS LAST,
                influence_event.date_reported DESC NULLS LAST,
                influence_event.id DESC
            LIMIT 200
            """,
            (person_id,),
        )
        campaign_support_summary = _fetch_dicts(
            conn,
            """
            SELECT
                event_type,
                COALESCE(
                    metadata->'campaign_support_attribution'->>'tier',
                    metadata->'base_metadata'->>'attribution_tier',
                    'source_backed_campaign_support_record'
                ) AS attribution_tier,
                count(*) AS event_count,
                count(*) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_event_count,
                sum(amount) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE recipient_person_id = %s
              AND review_status <> 'rejected'
              AND event_family = 'campaign_support'
            GROUP BY 1, 2
            ORDER BY event_count DESC, event_type, attribution_tier
            """,
            (person_id,),
        )
        campaign_support_recent_events = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.id,
                influence_event.event_family,
                influence_event.event_type,
                influence_event.event_subtype,
                influence_event.source_raw_name,
                source_entity.canonical_name AS source_entity_name,
                influence_event.amount,
                influence_event.currency,
                influence_event.amount_status,
                influence_event.event_date,
                influence_event.reporting_period,
                influence_event.date_reported,
                influence_event.description,
                influence_event.disclosure_system,
                influence_event.disclosure_threshold,
                influence_event.evidence_status,
                influence_event.extraction_method,
                influence_event.review_status,
                influence_event.missing_data_flags,
                influence_event.source_ref,
                source_document.source_id,
                source_document.source_name,
                source_document.source_type,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            JOIN source_document
              ON source_document.id = influence_event.source_document_id
            WHERE influence_event.recipient_person_id = %s
              AND influence_event.review_status <> 'rejected'
              AND influence_event.event_family = 'campaign_support'
            ORDER BY
                influence_event.event_date DESC NULLS LAST,
                influence_event.date_reported DESC NULLS LAST,
                influence_event.id DESC
            LIMIT 100
            """,
            (person_id,),
        )
        influence = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM person_influence_sector_summary
            WHERE person_id = %s
            ORDER BY influence_event_count DESC, public_sector
            LIMIT 25
            """,
            (person_id,),
        )
        votes = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM person_policy_vote_summary
            WHERE person_id = %s
            ORDER BY division_vote_count DESC, topic_label
            LIMIT 25
            """,
            (person_id,),
        )
        context = _fetch_dicts(
            conn,
            """
            SELECT *
            FROM person_policy_influence_context
            WHERE person_id = %s
            ORDER BY lifetime_influence_event_count DESC, topic_label, public_sector
            LIMIT 25
            """,
            (person_id,),
        )
    return _jsonable(
        {
            "person": {
                "id": person_rows[0]["id"],
                "external_key": person_rows[0]["external_key"],
                "display_name": person_rows[0]["display_name"],
                "canonical_name": person_rows[0]["canonical_name"],
            },
            "contact": _representative_contact_from_metadata(
                person_rows[0].get("metadata"),
                source_url=person_rows[0].get("source_final_url") or person_rows[0].get("source_url"),
            ),
            "office_terms": terms,
            "event_summary": event_summary,
            "recent_events": _with_representative_evidence_cursors(recent_events),
            "campaign_support_summary": campaign_support_summary,
            "campaign_support_recent_events": _with_representative_evidence_cursors(
                campaign_support_recent_events
            ),
            "campaign_support_caveat": (
                "Campaign support rows are source-backed election-return or advertising records "
                "connected to a candidate, Senate group, party branch, third party, or media "
                "advertiser. They are not treated as money personally received by the "
                "representative unless a source explicitly supports that narrower claim."
            ),
            "influence_by_sector": influence,
            "vote_topics": votes,
            "source_effect_context": context,
            "caveat": INFLUENCE_CONTEXT_CAVEAT,
        }
    )


def get_entity_profile(entity_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        entity_rows = _fetch_dicts(
            conn,
            """
            SELECT
                id,
                canonical_name,
                normalized_name,
                entity_type,
                country,
                state_or_territory,
                website
            FROM entity
            WHERE id = %s
            """,
            (entity_id,),
        )
        if not entity_rows:
            return {}

        classifications = _fetch_dicts(
            conn,
            """
            SELECT
                public_sector,
                method,
                confidence,
                evidence_note,
                reviewed_at
            FROM entity_industry_classification
            WHERE entity_id = %s
            ORDER BY
                CASE method
                    WHEN 'official' THEN 1
                    WHEN 'manual' THEN 2
                    WHEN 'rule_based' THEN 3
                    WHEN 'model_assisted' THEN 4
                    ELSE 5
                END,
                CASE confidence
                    WHEN 'exact_identifier' THEN 1
                    WHEN 'manual_reviewed' THEN 2
                    WHEN 'exact_name_context' THEN 3
                    WHEN 'fuzzy_high' THEN 4
                    WHEN 'fuzzy_low' THEN 5
                    ELSE 6
                END,
                public_sector
            LIMIT 10
            """,
            (entity_id,),
        )

        identifiers = _fetch_dicts(
            conn,
            """
            SELECT
                identifier_type,
                identifier_value,
                source_document.source_id,
                source_document.source_name,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM entity_identifier
            LEFT JOIN source_document
              ON source_document.id = entity_identifier.source_document_id
            WHERE entity_identifier.entity_id = %s
            ORDER BY identifier_type, identifier_value
            LIMIT 20
            """,
            (entity_id,),
        )

        as_source_summary = _fetch_dicts(
            conn,
            """
            SELECT
                event_family,
                event_type,
                count(*) AS event_count,
                count(*) FILTER (WHERE recipient_person_id IS NOT NULL)
                    AS person_linked_event_count,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_total,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE source_entity_id = %s
              AND review_status <> 'rejected'
            GROUP BY event_family, event_type
            ORDER BY event_count DESC, event_family, event_type
            """,
            (entity_id,),
        )

        as_recipient_summary = _fetch_dicts(
            conn,
            """
            SELECT
                event_family,
                event_type,
                count(*) AS event_count,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                )
                    AS reported_amount_total,
                count(*) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family = 'campaign_support'
                )
                    AS campaign_support_reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE recipient_entity_id = %s
              AND review_status <> 'rejected'
            GROUP BY event_family, event_type
            ORDER BY event_count DESC, event_family, event_type
            """,
            (entity_id,),
        )

        top_recipients = _fetch_dicts(
            conn,
            """
            SELECT
                COALESCE(person.id, recipient_entity.id) AS recipient_id,
                CASE
                    WHEN person.id IS NOT NULL THEN 'representative'
                    WHEN recipient_entity.id IS NOT NULL THEN 'entity'
                    ELSE 'raw_name'
                END AS recipient_type,
                COALESCE(
                    person.display_name,
                    recipient_entity.canonical_name,
                    influence_event.recipient_raw_name,
                    'Unknown recipient'
                ) AS recipient_label,
                count(*) AS event_count,
                count(*) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                      AND influence_event.event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                      AND influence_event.event_family <> 'campaign_support'
                ) AS reported_amount_total
            FROM influence_event
            LEFT JOIN person ON person.id = influence_event.recipient_person_id
            LEFT JOIN entity recipient_entity
              ON recipient_entity.id = influence_event.recipient_entity_id
            WHERE influence_event.source_entity_id = %s
              AND influence_event.review_status <> 'rejected'
            GROUP BY
                recipient_id,
                recipient_type,
                recipient_label
            ORDER BY
                reported_amount_total DESC NULLS LAST,
                event_count DESC,
                recipient_label
            LIMIT 25
            """,
            (entity_id,),
        )

        top_sources = _fetch_dicts(
            conn,
            """
            SELECT
                COALESCE(source_entity.id::text, influence_event.source_raw_name) AS source_id,
                CASE WHEN source_entity.id IS NOT NULL THEN 'entity' ELSE 'raw_name' END
                    AS source_type,
                COALESCE(
                    source_entity.canonical_name,
                    influence_event.source_raw_name,
                    'Unknown source'
                ) AS source_label,
                count(*) AS event_count,
                count(*) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                      AND influence_event.event_family <> 'campaign_support'
                )
                    AS reported_amount_event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                      AND influence_event.event_family <> 'campaign_support'
                ) AS reported_amount_total
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            WHERE influence_event.recipient_entity_id = %s
              AND influence_event.review_status <> 'rejected'
            GROUP BY
                source_id,
                source_type,
                source_label
            ORDER BY
                reported_amount_total DESC NULLS LAST,
                event_count DESC,
                source_label
            LIMIT 25
            """,
            (entity_id,),
        )

        recent_events = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.id,
                CASE
                    WHEN influence_event.source_entity_id = %s THEN 'as_source'
                    ELSE 'as_recipient'
                END AS entity_role,
                influence_event.event_family,
                influence_event.event_type,
                influence_event.event_subtype,
                influence_event.source_raw_name,
                source_entity.canonical_name AS source_entity_name,
                influence_event.recipient_raw_name,
                recipient_person.display_name AS recipient_person_name,
                recipient_entity.canonical_name AS recipient_entity_name,
                influence_event.amount,
                influence_event.currency,
                influence_event.amount_status,
                influence_event.event_date,
                influence_event.reporting_period,
                influence_event.date_reported,
                influence_event.description,
                influence_event.evidence_status,
                influence_event.review_status,
                influence_event.missing_data_flags,
                influence_event.source_ref,
                source_document.source_id,
                source_document.source_name,
                source_document.source_type,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            LEFT JOIN person recipient_person
              ON recipient_person.id = influence_event.recipient_person_id
            LEFT JOIN entity recipient_entity
              ON recipient_entity.id = influence_event.recipient_entity_id
            JOIN source_document
              ON source_document.id = influence_event.source_document_id
            WHERE (
                influence_event.source_entity_id = %s
                OR influence_event.recipient_entity_id = %s
            )
              AND influence_event.review_status <> 'rejected'
            ORDER BY
                influence_event.event_date DESC NULLS LAST,
                influence_event.date_reported DESC NULLS LAST,
                influence_event.id DESC
            LIMIT 50
            """,
            (entity_id, entity_id, entity_id),
        )

    return _jsonable(
        {
            "entity": entity_rows[0],
            "classifications": classifications,
            "identifiers": identifiers,
            "as_source_summary": as_source_summary,
            "as_recipient_summary": as_recipient_summary,
            "top_recipients": top_recipients,
            "top_sources": top_sources,
            "recent_events": recent_events,
            "caveat": ENTITY_PROFILE_CAVEAT,
        }
    )


def _party_entity_name_patterns(party: dict[str, Any]) -> list[str]:
    return party_entity_name_patterns(party)


def _party_linked_entity_ids(
    conn,
    party: dict[str, Any],
) -> tuple[list[int], list[dict[str, Any]], list[dict[str, Any]]]:
    materialized_links: list[dict[str, Any]] = []
    if _table_exists(conn, "party_entity_link"):
        materialized_links = _fetch_dicts(
            conn,
            """
            SELECT
                entity.id AS entity_id,
                entity.canonical_name,
                entity.entity_type,
                party_entity_link.link_type,
                party_entity_link.method,
                party_entity_link.confidence,
                party_entity_link.review_status,
                party_entity_link.evidence_note,
                NULLIF(party_entity_link.metadata->>'influence_event_count', '')::bigint
                    AS influence_event_count,
                NULLIF(party_entity_link.metadata->>'reported_amount_total', '')::numeric
                    AS reported_amount_total
            FROM party_entity_link
            JOIN entity ON entity.id = party_entity_link.entity_id
            WHERE party_entity_link.party_id = %s
              AND party_entity_link.review_status IN ('reviewed', 'needs_review')
            ORDER BY party_entity_link.link_type, entity.canonical_name
            """,
            (party["id"],),
        )

    patterns = _party_entity_name_patterns(party)
    candidate_rows: list[dict[str, Any]] = []
    if patterns:
        pattern_clause = " OR ".join(["entity.canonical_name ILIKE %s" for _ in patterns])
        candidate_rows = _fetch_dicts(
            conn,
            f"""
            SELECT
                entity.id AS entity_id,
                entity.canonical_name,
                entity.entity_type,
                'name_family_candidate'::TEXT AS link_type,
                'rule_based'::TEXT AS method,
                'unreviewed_candidate'::TEXT AS confidence,
                'needs_review'::TEXT AS review_status,
                'Candidate generated from party-name family patterns; requires review before strong claims.'::TEXT
                    AS evidence_note,
                count(DISTINCT influence_event.id) AS influence_event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM entity
            LEFT JOIN influence_event
              ON (
                    influence_event.source_entity_id = entity.id
                    OR influence_event.recipient_entity_id = entity.id
                 )
             AND influence_event.review_status <> 'rejected'
            WHERE {pattern_clause}
              AND NOT EXISTS (
                  SELECT 1
                  FROM party_entity_link existing
                  WHERE existing.party_id = %s
                    AND existing.entity_id = entity.id
              )
            GROUP BY entity.id, entity.canonical_name, entity.entity_type
            ORDER BY
                reported_amount_total DESC NULLS LAST,
                influence_event_count DESC,
                entity.canonical_name
            LIMIT 100
            """,
            (*patterns, party["id"]),
        )

    reviewed_by_id: dict[int, dict[str, Any]] = {}
    candidate_by_id: dict[int, dict[str, Any]] = {}
    for row in candidate_rows:
        candidate_by_id[int(row["entity_id"])] = row
    for row in materialized_links:
        entity_id = int(row["entity_id"])
        if row["review_status"] == "reviewed":
            reviewed_by_id[entity_id] = row
            candidate_by_id.pop(entity_id, None)
        else:
            candidate_by_id[entity_id] = row
    return sorted(reviewed_by_id), list(reviewed_by_id.values()), list(candidate_by_id.values())


def get_party_profile(party_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        party_rows = _fetch_dicts(
            conn,
            """
            SELECT
                party.id,
                party.name,
                party.short_name,
                party.party_group,
                jurisdiction.name AS jurisdiction_name,
                jurisdiction.level AS jurisdiction_level
            FROM party
            LEFT JOIN jurisdiction ON jurisdiction.id = party.jurisdiction_id
            WHERE party.id = %s
            """,
            (party_id,),
        )
        if not party_rows:
            return {}

        party = party_rows[0]
        party["display_name"] = _party_public_label(party.get("name"), party.get("short_name"))
        linked_entity_ids, linked_entities, candidate_entities = _party_linked_entity_ids(conn, party)

        office_summary = _fetch_dicts(
            conn,
            """
            SELECT
                office_term.chamber,
                count(DISTINCT office_term.person_id) FILTER (
                    WHERE office_term.term_end IS NULL
                ) AS current_representative_count
            FROM office_term
            WHERE office_term.party_id = %s
            GROUP BY office_term.chamber
            ORDER BY office_term.chamber
            """,
            (party_id,),
        )

        if not linked_entity_ids:
            return _jsonable(
                {
                    "party": party,
                    "office_summary": office_summary,
                    "linked_entities": [],
                    "candidate_entities": candidate_entities,
                    "money_summary": [],
                    "by_financial_year": [],
                    "by_return_type": [],
                    "top_sources": [],
                    "top_recipients": [],
                    "associated_entity_returns": [],
                    "recent_events": [],
                    "caveat": PARTY_PROFILE_CAVEAT,
                }
            )

        entity_array = linked_entity_ids
        money_summary = _fetch_dicts(
            conn,
            """
            WITH events AS (
                SELECT DISTINCT
                    influence_event.id,
                    CASE
                        WHEN influence_event.source_entity_id = ANY(%s::bigint[])
                         AND influence_event.recipient_entity_id = ANY(%s::bigint[])
                        THEN 'internal_party_entity_flow'
                        WHEN influence_event.recipient_entity_id = ANY(%s::bigint[])
                        THEN 'as_recipient'
                        ELSE 'as_source'
                    END AS entity_role,
                    influence_event.event_type,
                    influence_event.amount,
                    influence_event.amount_status,
                    influence_event.event_date
                FROM influence_event
                WHERE influence_event.event_family = 'money'
                  AND influence_event.review_status <> 'rejected'
                  AND (
                        influence_event.source_entity_id = ANY(%s::bigint[])
                        OR influence_event.recipient_entity_id = ANY(%s::bigint[])
                  )
            )
            SELECT
                entity_role,
                event_type,
                count(*) AS event_count,
                count(*) FILTER (WHERE amount_status = 'reported') AS reported_amount_event_count,
                sum(amount) FILTER (WHERE amount_status = 'reported') AS reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM events
            GROUP BY entity_role, event_type
            ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
            """,
            (entity_array, entity_array, entity_array, entity_array, entity_array),
        )

        by_financial_year = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.reporting_period AS financial_year,
                count(DISTINCT influence_event.id) AS event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM influence_event
            WHERE influence_event.event_family = 'money'
              AND influence_event.review_status <> 'rejected'
              AND (
                    influence_event.source_entity_id = ANY(%s::bigint[])
                    OR influence_event.recipient_entity_id = ANY(%s::bigint[])
              )
            GROUP BY influence_event.reporting_period
            ORDER BY influence_event.reporting_period DESC NULLS LAST
            LIMIT 25
            """,
            (entity_array, entity_array),
        )

        by_return_type = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.metadata->>'return_type' AS return_type,
                count(DISTINCT influence_event.id) AS event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM influence_event
            WHERE influence_event.event_family = 'money'
              AND influence_event.review_status <> 'rejected'
              AND (
                    influence_event.source_entity_id = ANY(%s::bigint[])
                    OR influence_event.recipient_entity_id = ANY(%s::bigint[])
              )
            GROUP BY influence_event.metadata->>'return_type'
            ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
            LIMIT 25
            """,
            (entity_array, entity_array),
        )

        top_sources = _fetch_dicts(
            conn,
            """
            SELECT
                COALESCE(source_entity.id::TEXT, influence_event.source_raw_name) AS source_id,
                COALESCE(source_entity.canonical_name, influence_event.source_raw_name, 'Unknown source')
                    AS source_label,
                count(DISTINCT influence_event.id) AS event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM influence_event
            LEFT JOIN entity source_entity ON source_entity.id = influence_event.source_entity_id
            WHERE influence_event.event_family = 'money'
              AND influence_event.review_status <> 'rejected'
              AND influence_event.recipient_entity_id = ANY(%s::bigint[])
              AND (
                    influence_event.source_entity_id IS NULL
                    OR NOT influence_event.source_entity_id = ANY(%s::bigint[])
              )
            GROUP BY source_id, source_label
            ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC, source_label
            LIMIT 25
            """,
            (entity_array, entity_array),
        )

        top_recipients = _fetch_dicts(
            conn,
            """
            SELECT
                COALESCE(recipient_entity.id::TEXT, influence_event.recipient_raw_name)
                    AS recipient_id,
                COALESCE(
                    recipient_entity.canonical_name,
                    influence_event.recipient_raw_name,
                    'Unknown recipient'
                ) AS recipient_label,
                count(DISTINCT influence_event.id) AS event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM influence_event
            LEFT JOIN entity recipient_entity
              ON recipient_entity.id = influence_event.recipient_entity_id
            WHERE influence_event.event_family = 'money'
              AND influence_event.review_status <> 'rejected'
              AND influence_event.source_entity_id = ANY(%s::bigint[])
              AND (
                    influence_event.recipient_entity_id IS NULL
                    OR NOT influence_event.recipient_entity_id = ANY(%s::bigint[])
              )
            GROUP BY recipient_id, recipient_label
            ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC, recipient_label
            LIMIT 25
            """,
            (entity_array, entity_array),
        )

        associated_entity_returns = _fetch_dicts(
            conn,
            """
            SELECT
                linked.entity_id,
                linked.canonical_name,
                count(DISTINCT influence_event.id) AS event_count,
                sum(influence_event.amount) FILTER (
                    WHERE influence_event.amount_status = 'reported'
                ) AS reported_amount_total
            FROM (
                SELECT entity.id AS entity_id, entity.canonical_name
                FROM entity
                WHERE entity.id = ANY(%s::bigint[])
            ) linked
            JOIN influence_event
              ON (
                    influence_event.source_entity_id = linked.entity_id
                    OR influence_event.recipient_entity_id = linked.entity_id
                 )
             AND influence_event.event_family = 'money'
             AND influence_event.review_status <> 'rejected'
             AND influence_event.metadata->>'return_type' = 'Associated Entity Return'
            GROUP BY linked.entity_id, linked.canonical_name
            ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC, linked.canonical_name
            LIMIT 25
            """,
            (entity_array,),
        )

        recent_events = _fetch_dicts(
            conn,
            """
            SELECT
                influence_event.id,
                CASE
                    WHEN influence_event.source_entity_id = ANY(%s::bigint[])
                     AND influence_event.recipient_entity_id = ANY(%s::bigint[])
                    THEN 'internal_party_entity_flow'
                    WHEN influence_event.recipient_entity_id = ANY(%s::bigint[])
                    THEN 'as_recipient'
                    ELSE 'as_source'
                END AS entity_role,
                influence_event.event_type,
                influence_event.source_raw_name,
                source_entity.canonical_name AS source_entity_name,
                influence_event.recipient_raw_name,
                recipient_entity.canonical_name AS recipient_entity_name,
                influence_event.amount,
                influence_event.currency,
                influence_event.amount_status,
                influence_event.event_date,
                influence_event.reporting_period,
                influence_event.description,
                influence_event.review_status,
                source_document.source_id,
                source_document.source_name,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity ON source_entity.id = influence_event.source_entity_id
            LEFT JOIN entity recipient_entity ON recipient_entity.id = influence_event.recipient_entity_id
            JOIN source_document ON source_document.id = influence_event.source_document_id
            WHERE influence_event.event_family = 'money'
              AND influence_event.review_status <> 'rejected'
              AND (
                    influence_event.source_entity_id = ANY(%s::bigint[])
                    OR influence_event.recipient_entity_id = ANY(%s::bigint[])
              )
            ORDER BY
                influence_event.event_date DESC NULLS LAST,
                influence_event.id DESC
            LIMIT 50
            """,
            (entity_array, entity_array, entity_array, entity_array, entity_array),
        )

    return _jsonable(
        {
            "party": party,
            "office_summary": office_summary,
            "linked_entities": linked_entities,
            "candidate_entities": candidate_entities,
            "money_summary": money_summary,
            "by_financial_year": by_financial_year,
            "by_return_type": by_return_type,
            "top_sources": top_sources,
            "top_recipients": top_recipients,
            "associated_entity_returns": associated_entity_returns,
            "recent_events": recent_events,
            "caveat": PARTY_PROFILE_CAVEAT,
        }
    )


def _graph_node_id(node_type: str, value: Any) -> str:
    text = str(value or "")
    if node_type in {"person", "entity", "party"}:
        return f"{node_type}:{text}"
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    return f"{node_type}:{digest}"


def _add_graph_node(
    nodes: dict[str, dict[str, Any]],
    *,
    node_id: str,
    node_type: str,
    label: str,
    **metadata: Any,
) -> None:
    if node_id in nodes:
        nodes[node_id].update({key: value for key, value in metadata.items() if value is not None})
        return
    nodes[node_id] = {
        "id": node_id,
        "type": node_type,
        "label": label,
        **{key: value for key, value in metadata.items() if value is not None},
    }


def _raw_graph_node_id(prefix: str, label: Any) -> str:
    return _graph_node_id(prefix, " ".join(str(label or "Unknown").lower().split()))


def _append_graph_edge(
    edges: list[dict[str, Any]],
    *,
    source: str,
    target: str,
    edge_type: str,
    **metadata: Any,
) -> None:
    key = json.dumps(
        {
            "source": source,
            "target": target,
            "type": edge_type,
            "event_family": metadata.get("event_family"),
            "event_type": metadata.get("event_type"),
            "link_type": metadata.get("link_type"),
            "method": metadata.get("method"),
            "review_status": metadata.get("review_status"),
            "evidence_status": metadata.get("evidence_status"),
            "evidence_tier": metadata.get("evidence_tier"),
            "allocation_method": metadata.get("allocation_method"),
        },
        sort_keys=True,
        default=str,
    )
    edge_id = _graph_node_id("edge", key)
    if any(edge["id"] == edge_id for edge in edges):
        return
    edges.append(
        {
            "id": edge_id,
            "source": source,
            "target": target,
            "type": edge_type,
            **{item_key: value for item_key, value in metadata.items() if value is not None},
        }
    )


def _entity_or_raw_node(
    nodes: dict[str, dict[str, Any]],
    *,
    entity_id: Any,
    entity_name: Any,
    raw_name: Any,
    raw_prefix: str,
) -> str:
    if entity_id is not None:
        node_id = _graph_node_id("entity", entity_id)
        _add_graph_node(
            nodes,
            node_id=node_id,
            node_type="entity",
            label=str(entity_name or raw_name or "Unknown entity"),
        )
        return node_id
    label = str(raw_name or "Unidentified source")
    node_id = _raw_graph_node_id(raw_prefix, label)
    _add_graph_node(nodes, node_id=node_id, node_type="raw_name", label=label)
    return node_id


def _append_reviewed_party_money_context(
    conn,
    *,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    party_id: int,
    party_node_id: str,
    limit: int,
) -> dict[str, Any]:
    summary = _party_reviewed_money_summary(conn, party_id=party_id)
    money_rows = _fetch_dicts(
        conn,
        """
        WITH reviewed_entities AS (
            SELECT DISTINCT entity_id
            FROM party_entity_link
            WHERE party_id = %s
              AND review_status = 'reviewed'
        )
        SELECT
            recipient_entity.id AS recipient_entity_id,
            recipient_entity.canonical_name AS recipient_entity_name,
            recipient_entity.entity_type AS recipient_entity_type,
            source_entity.id AS source_entity_id,
            source_entity.canonical_name AS source_entity_name,
            influence_event.source_raw_name,
            influence_event.event_type,
            count(DISTINCT influence_event.id) AS event_count,
            count(DISTINCT influence_event.id) FILTER (
                WHERE influence_event.amount_status = 'reported'
            ) AS reported_amount_event_count,
            count(DISTINCT influence_event.id) FILTER (
                WHERE influence_event.review_status = 'reviewed'
            ) AS reviewed_event_count,
            count(DISTINCT influence_event.id) FILTER (
                WHERE influence_event.review_status = 'needs_review'
            ) AS needs_review_event_count,
            count(DISTINCT influence_event.id) FILTER (
                WHERE jsonb_array_length(influence_event.missing_data_flags) > 0
            ) AS missing_data_event_count,
            sum(influence_event.amount) FILTER (
                WHERE influence_event.amount_status = 'reported'
            ) AS reported_amount_total,
            min(influence_event.event_date) AS first_event_date,
            max(influence_event.event_date) AS last_event_date,
            array_remove(array_agg(DISTINCT source_document.url), NULL) AS source_urls
        FROM influence_event
        JOIN reviewed_entities recipient_link
          ON recipient_link.entity_id = influence_event.recipient_entity_id
        JOIN entity recipient_entity
          ON recipient_entity.id = influence_event.recipient_entity_id
        LEFT JOIN entity source_entity
          ON source_entity.id = influence_event.source_entity_id
        JOIN source_document
          ON source_document.id = influence_event.source_document_id
        WHERE influence_event.event_family = 'money'
          AND influence_event.review_status <> 'rejected'
          AND (
                influence_event.source_entity_id IS NULL
                OR NOT EXISTS (
                    SELECT 1
                    FROM reviewed_entities source_link
                    WHERE source_link.entity_id = influence_event.source_entity_id
                )
          )
        GROUP BY
            recipient_entity.id,
            recipient_entity.canonical_name,
            recipient_entity.entity_type,
            source_entity.id,
            source_entity.canonical_name,
            influence_event.source_raw_name,
            influence_event.event_type
        ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
        LIMIT %s
        """,
        (party_id, limit),
    )
    display_recipient_entity_ids = sorted(
        {int(row["recipient_entity_id"]) for row in money_rows}
    )
    link_rows = _fetch_dicts(
        conn,
        """
        WITH selected_entities AS (
            SELECT entity_id
            FROM (
                SELECT DISTINCT link.entity_id
                FROM party_entity_link link
                WHERE link.party_id = %s
                  AND link.review_status = 'reviewed'
                ORDER BY link.entity_id
                LIMIT %s
            ) limited_links
            UNION
            SELECT unnest(%s::bigint[])
        )
        SELECT
            link.entity_id,
            entity.canonical_name,
            entity.entity_type,
            link.link_type,
            link.method,
            link.confidence,
            link.review_status,
            link.evidence_note
        FROM party_entity_link link
        JOIN selected_entities selected ON selected.entity_id = link.entity_id
        JOIN entity ON entity.id = link.entity_id
        WHERE link.party_id = %s
          AND link.review_status = 'reviewed'
        ORDER BY entity.canonical_name, link.link_type
        """,
        (party_id, limit, display_recipient_entity_ids, party_id),
    )
    for row in link_rows:
        party_entity_node = _graph_node_id("entity", row["entity_id"])
        _add_graph_node(
            nodes,
            node_id=party_entity_node,
            node_type="entity",
            label=row["canonical_name"],
            entity_type=row["entity_type"],
        )
        _append_graph_edge(
            edges,
            source=party_entity_node,
            target=party_node_id,
            edge_type="reviewed_party_entity_link",
            link_type=row["link_type"],
            method=row["method"],
            confidence=row["confidence"],
            review_status=row["review_status"],
            evidence_note=row["evidence_note"],
            evidence_tier="party_entity_context",
            claim_scope="Reviewed party/entity relationship; not a person-level receipt.",
        )
    for row in money_rows:
        recipient_id = _graph_node_id("entity", row["recipient_entity_id"])
        _add_graph_node(
            nodes,
            node_id=recipient_id,
            node_type="entity",
            label=row["recipient_entity_name"],
            entity_type=row["recipient_entity_type"],
        )
        source_id = _entity_or_raw_node(
            nodes,
            entity_id=row["source_entity_id"],
            entity_name=row["source_entity_name"],
            raw_name=row["source_raw_name"],
            raw_prefix="raw_source",
        )
        _append_graph_edge(
            edges,
            source=source_id,
            target=recipient_id,
            edge_type="money_to_reviewed_party_entities",
            event_family="money",
            event_type=row["event_type"],
            event_count=row["event_count"],
            reported_amount_event_count=row["reported_amount_event_count"],
            reviewed_event_count=row["reviewed_event_count"],
            needs_review_event_count=row["needs_review_event_count"],
            missing_data_event_count=row["missing_data_event_count"],
            reported_amount_total=row["reported_amount_total"],
            first_event_date=row["first_event_date"],
            last_event_date=row["last_event_date"],
            source_urls=row["source_urls"],
            evidence_status="non_rejected_public_disclosure",
            evidence_tier="party_entity_context",
            claim_scope="Money disclosed to a reviewed party/entity, not to this representative.",
        )
    return summary


def _party_reviewed_money_summary(conn, *, party_id: int) -> dict[str, Any]:
    summary = {
        "event_count": 0,
        "reported_amount_event_count": 0,
        "reported_amount_total": None,
        "first_event_date": None,
        "last_event_date": None,
        "input_event_ids": set(),
        "input_source_document_ids": set(),
    }
    summary_rows = _fetch_dicts(
        conn,
        """
        WITH reviewed_entities AS (
            SELECT DISTINCT entity_id
            FROM party_entity_link
            WHERE party_id = %s
              AND review_status = 'reviewed'
        )
        SELECT
            count(DISTINCT influence_event.id) AS event_count,
            count(DISTINCT influence_event.id) FILTER (
                WHERE influence_event.amount_status = 'reported'
            ) AS reported_amount_event_count,
            sum(influence_event.amount) FILTER (
                WHERE influence_event.amount_status = 'reported'
            ) AS reported_amount_total,
            min(influence_event.event_date) AS first_event_date,
            max(influence_event.event_date) AS last_event_date,
            array_remove(array_agg(DISTINCT influence_event.id), NULL) AS input_event_ids,
            array_remove(array_agg(DISTINCT source_document.id), NULL)
                AS input_source_document_ids
        FROM influence_event
        JOIN reviewed_entities recipient_link
          ON recipient_link.entity_id = influence_event.recipient_entity_id
        JOIN source_document
          ON source_document.id = influence_event.source_document_id
        WHERE influence_event.event_family = 'money'
          AND influence_event.review_status <> 'rejected'
          AND (
                influence_event.source_entity_id IS NULL
                OR NOT EXISTS (
                    SELECT 1
                    FROM reviewed_entities source_link
                    WHERE source_link.entity_id = influence_event.source_entity_id
                )
          )
        """,
        (party_id,),
    )
    if not summary_rows:
        return summary
    for row in summary_rows:
        summary["event_count"] += int(row["event_count"] or 0)
        summary["reported_amount_event_count"] += int(row["reported_amount_event_count"] or 0)
        if row["reported_amount_total"] is not None:
            summary["reported_amount_total"] = (
                (summary["reported_amount_total"] or Decimal("0")) + row["reported_amount_total"]
            )
        summary["first_event_date"] = min(
            (date_value for date_value in (summary["first_event_date"], row["first_event_date"]) if date_value),
            default=None,
        )
        summary["last_event_date"] = max(
            (date_value for date_value in (summary["last_event_date"], row["last_event_date"]) if date_value),
            default=None,
        )
        summary["input_event_ids"].update(int(event_id) for event_id in row["input_event_ids"] or [])
        summary["input_source_document_ids"].update(
            int(source_document_id)
            for source_document_id in row["input_source_document_ids"] or []
        )
    return summary


def _append_person_party_exposure_context(
    conn,
    *,
    nodes: dict[str, dict[str, Any]],
    edges: list[dict[str, Any]],
    person_id: int,
    person_node_id: str,
    limit: int,
) -> None:
    party_rows = _fetch_dicts(
        conn,
        """
        SELECT DISTINCT ON (party.id)
            party.id,
            party.name,
            party.short_name,
            office_term.chamber,
            electorate.name AS electorate_name,
            COALESCE(
                NULLIF(electorate.state_or_territory, ''),
                NULLIF(office_term.metadata->>'state', '')
            ) AS state_or_territory,
            office_term.term_start,
            COALESCE(current_counts.current_representative_count, 0)
                AS current_representative_count
        FROM office_term
        JOIN party ON party.id = office_term.party_id
        LEFT JOIN electorate ON electorate.id = office_term.electorate_id
        LEFT JOIN (
            SELECT party_id, count(DISTINCT person_id) AS current_representative_count
            FROM office_term
            WHERE term_end IS NULL
              AND party_id IS NOT NULL
            GROUP BY party_id
        ) current_counts ON current_counts.party_id = party.id
        WHERE office_term.person_id = %s
          AND office_term.term_end IS NULL
          AND office_term.party_id IS NOT NULL
        ORDER BY party.id, office_term.term_start DESC NULLS LAST
        LIMIT %s
        """,
        (person_id, 3),
    )
    for party in party_rows:
        party_node_id = _graph_node_id("party", party["id"])
        _add_graph_node(
            nodes,
            node_id=party_node_id,
            node_type="party",
            label=party["name"],
            short_name=party["short_name"],
        )
        party_money = _append_reviewed_party_money_context(
            conn,
            nodes=nodes,
            edges=edges,
            party_id=int(party["id"]),
            party_node_id=party_node_id,
            limit=min(limit, 60),
        )
        representative_count = int(party["current_representative_count"] or 0)
        party_total = party_money["reported_amount_total"]
        modelled_amount = (
            party_total / representative_count
            if party_total is not None and representative_count > 0
            else None
        )
        allocation_weight = (
            Decimal("1") / representative_count
            if modelled_amount is not None and representative_count > 0
            else None
        )
        _append_graph_edge(
            edges,
            source=party_node_id,
            target=person_node_id,
            edge_type=(
                "modelled_party_money_exposure"
                if modelled_amount is not None
                else "current_party_representation_context"
            ),
            event_family="money" if modelled_amount is not None else None,
            event_type="party_aggregate_context" if modelled_amount is not None else None,
            event_count=party_money["event_count"] or None,
            first_event_date=party_money["first_event_date"],
            last_event_date=party_money["last_event_date"],
            evidence_status=(
                "modelled_context_not_disclosed_receipt"
                if modelled_amount is not None
                else "current_office_term"
            ),
            evidence_tier=(
                "modelled_allocation"
                if modelled_amount is not None
                else "party_membership_context"
            ),
            allocation_method=(
                "equal_current_representative_share"
                if modelled_amount is not None
                else "no_allocation"
            ),
            allocation_denominator=representative_count or None,
            allocation_weight=allocation_weight,
            allocation_basis=(
                "reviewed_party_entity_money_total_divided_by_current_party_representatives"
                if modelled_amount is not None
                else None
            ),
            party_context_reported_amount_total=party_total,
            modelled_amount_total=modelled_amount,
            model_name=(
                "equal_current_representative_party_exposure"
                if modelled_amount is not None
                else None
            ),
            model_version="0.1.0" if modelled_amount is not None else None,
            input_event_ids=(
                sorted(party_money["input_event_ids"])
                if modelled_amount is not None
                else None
            ),
            input_source_document_ids=(
                sorted(party_money["input_source_document_ids"])
                if modelled_amount is not None
                else None
            ),
            amount_estimate=modelled_amount,
            amount_lower_bound=modelled_amount,
            amount_upper_bound=modelled_amount,
            currency="AUD" if modelled_amount is not None else None,
            uncertainty_label=(
                "rough_equal_share_point_estimate"
                if modelled_amount is not None
                else None
            ),
            display_caveat=(
                "Estimated indirect exposure only; not a disclosed personal receipt."
                if modelled_amount is not None
                else None
            ),
            generated_at=(
                datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
                if modelled_amount is not None
                else None
            ),
            claim_scope=(
                "Analytical equal-share exposure to reviewed party/entity money; "
                "not a disclosed personal receipt."
                if modelled_amount is not None
                else "Current office-term party relationship; no money allocation applied."
            ),
            chamber=party["chamber"],
            state_or_territory=party["state_or_territory"],
            electorate_name=party["electorate_name"],
            term_start=party["term_start"],
        )


def get_influence_graph(
    *,
    person_id: int | None = None,
    party_id: int | None = None,
    entity_id: int | None = None,
    include_candidates: bool = False,
    limit: int = 100,
    database_url: str | None = None,
) -> dict[str, Any]:
    selected_roots = [value is not None for value in (person_id, party_id, entity_id)]
    if sum(selected_roots) != 1:
        raise ValueError("Provide exactly one of person_id, party_id, or entity_id.")

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    root_id = ""
    with connect(database_url) as conn:
        if person_id is not None:
            person_rows = _fetch_dicts(
                conn,
                """
                SELECT id, display_name, canonical_name
                FROM person
                WHERE id = %s
                """,
                (person_id,),
            )
            if not person_rows:
                return {}
            person = person_rows[0]
            root_id = _graph_node_id("person", person["id"])
            _add_graph_node(
                nodes,
                node_id=root_id,
                node_type="person",
                label=person["display_name"] or person["canonical_name"],
            )
            rows = _fetch_dicts(
                conn,
                """
                SELECT
                    influence_event.event_family,
                    influence_event.event_type,
                    source_entity.id AS source_entity_id,
                    source_entity.canonical_name AS source_entity_name,
                    influence_event.source_raw_name,
                    count(DISTINCT influence_event.id) AS event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'reviewed'
                    ) AS reviewed_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'needs_review'
                    ) AS needs_review_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE jsonb_array_length(influence_event.missing_data_flags) > 0
                    ) AS missing_data_event_count,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_total,
                    min(influence_event.event_date) AS first_event_date,
                    max(influence_event.event_date) AS last_event_date,
                    max(influence_event.metadata->>'claim_scope') AS claim_scope,
                    array_remove(array_agg(DISTINCT source_document.url), NULL) AS source_urls
                FROM influence_event
                LEFT JOIN entity source_entity
                  ON source_entity.id = influence_event.source_entity_id
                JOIN source_document
                  ON source_document.id = influence_event.source_document_id
                WHERE influence_event.recipient_person_id = %s
                  AND influence_event.review_status <> 'rejected'
                  AND influence_event.event_family <> 'campaign_support'
                GROUP BY
                    influence_event.event_family,
                    influence_event.event_type,
                    source_entity.id,
                    source_entity.canonical_name,
                    influence_event.source_raw_name
                ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
                LIMIT %s
                """,
                (person_id, limit),
            )
            for row in rows:
                source_id = _entity_or_raw_node(
                    nodes,
                    entity_id=row["source_entity_id"],
                    entity_name=row["source_entity_name"],
                    raw_name=row["source_raw_name"],
                    raw_prefix="raw_source",
                )
                _append_graph_edge(
                    edges,
                    source=source_id,
                    target=root_id,
                    edge_type="disclosed_to_representative",
                    event_family=row["event_family"],
                    event_type=row["event_type"],
                    event_count=row["event_count"],
                    reported_amount_event_count=row["reported_amount_event_count"],
                    reviewed_event_count=row["reviewed_event_count"],
                    needs_review_event_count=row["needs_review_event_count"],
                    missing_data_event_count=row["missing_data_event_count"],
                    reported_amount_total=row["reported_amount_total"],
                    first_event_date=row["first_event_date"],
                    last_event_date=row["last_event_date"],
                    source_urls=row["source_urls"],
                    evidence_status="non_rejected_public_disclosure",
                    claim_scope=row["claim_scope"],
                )
            _append_person_party_exposure_context(
                conn,
                nodes=nodes,
                edges=edges,
                person_id=person_id,
                person_node_id=root_id,
                limit=limit,
            )

        if party_id is not None:
            party_rows = _fetch_dicts(
                conn,
                """
                SELECT id, name, short_name
                FROM party
                WHERE id = %s
                """,
                (party_id,),
            )
            if not party_rows:
                return {}
            party = party_rows[0]
            root_id = _graph_node_id("party", party["id"])
            _add_graph_node(
                nodes,
                node_id=root_id,
                node_type="party",
                label=party["name"],
                short_name=party["short_name"],
            )
            reviewed_entity_id_rows = _fetch_dicts(
                conn,
                """
                SELECT link.entity_id
                FROM party_entity_link link
                WHERE link.party_id = %s
                  AND link.review_status = 'reviewed'
                """,
                (party_id,),
            )
            link_rows = _fetch_dicts(
                conn,
                """
                SELECT
                    link.entity_id,
                    entity.canonical_name,
                    entity.entity_type,
                    link.link_type,
                    link.method,
                    link.confidence,
                    link.review_status,
                    link.evidence_note
                FROM party_entity_link link
                JOIN entity ON entity.id = link.entity_id
                WHERE link.party_id = %s
                  AND link.review_status = 'reviewed'
                ORDER BY entity.canonical_name
                LIMIT %s
                """,
                (party_id, limit),
            )
            linked_entity_ids = [int(row["entity_id"]) for row in reviewed_entity_id_rows]
            for row in link_rows:
                party_entity_node = _graph_node_id("entity", row["entity_id"])
                _add_graph_node(
                    nodes,
                    node_id=party_entity_node,
                    node_type="entity",
                    label=row["canonical_name"],
                    entity_type=row["entity_type"],
                )
                _append_graph_edge(
                    edges,
                    source=party_entity_node,
                    target=root_id,
                    edge_type="reviewed_party_entity_link",
                    link_type=row["link_type"],
                    method=row["method"],
                    confidence=row["confidence"],
                    review_status=row["review_status"],
                    evidence_note=row["evidence_note"],
                )
            if linked_entity_ids:
                rows = _fetch_dicts(
                    conn,
                    """
                    SELECT
                        recipient_entity.id AS recipient_entity_id,
                        recipient_entity.canonical_name AS recipient_entity_name,
                        recipient_entity.entity_type AS recipient_entity_type,
                        party_link.link_type AS party_link_type,
                        party_link.method AS party_link_method,
                        party_link.confidence AS party_link_confidence,
                        party_link.review_status AS party_link_review_status,
                        party_link.evidence_note AS party_link_evidence_note,
                        source_entity.id AS source_entity_id,
                        source_entity.canonical_name AS source_entity_name,
                        influence_event.source_raw_name,
                        influence_event.event_type,
                        count(DISTINCT influence_event.id) AS event_count,
                        count(DISTINCT influence_event.id) FILTER (
                            WHERE influence_event.amount_status = 'reported'
                        ) AS reported_amount_event_count,
                        count(DISTINCT influence_event.id) FILTER (
                            WHERE influence_event.review_status = 'reviewed'
                        ) AS reviewed_event_count,
                        count(DISTINCT influence_event.id) FILTER (
                            WHERE influence_event.review_status = 'needs_review'
                        ) AS needs_review_event_count,
                        count(DISTINCT influence_event.id) FILTER (
                            WHERE jsonb_array_length(influence_event.missing_data_flags) > 0
                        ) AS missing_data_event_count,
                        sum(influence_event.amount) FILTER (
                            WHERE influence_event.amount_status = 'reported'
                        ) AS reported_amount_total,
                        min(influence_event.event_date) AS first_event_date,
                        max(influence_event.event_date) AS last_event_date,
                        array_remove(array_agg(DISTINCT source_document.url), NULL) AS source_urls
                    FROM influence_event
                    JOIN party_entity_link party_link
                      ON party_link.party_id = %s
                     AND party_link.entity_id = influence_event.recipient_entity_id
                     AND party_link.review_status = 'reviewed'
                    JOIN entity recipient_entity
                      ON recipient_entity.id = influence_event.recipient_entity_id
                    LEFT JOIN entity source_entity
                      ON source_entity.id = influence_event.source_entity_id
                    JOIN source_document
                      ON source_document.id = influence_event.source_document_id
                    WHERE influence_event.event_family = 'money'
                      AND influence_event.review_status <> 'rejected'
                      AND influence_event.recipient_entity_id = ANY(%s::bigint[])
                      AND (
                            influence_event.source_entity_id IS NULL
                            OR NOT influence_event.source_entity_id = ANY(%s::bigint[])
                      )
                    GROUP BY
                        recipient_entity.id,
                        recipient_entity.canonical_name,
                        recipient_entity.entity_type,
                        party_link.link_type,
                        party_link.method,
                        party_link.confidence,
                        party_link.review_status,
                        party_link.evidence_note,
                        source_entity.id,
                        source_entity.canonical_name,
                        influence_event.source_raw_name,
                        influence_event.event_type
                    ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
                    LIMIT %s
                    """,
                    (party_id, linked_entity_ids, linked_entity_ids, limit),
                )
                for row in rows:
                    recipient_id = _graph_node_id("entity", row["recipient_entity_id"])
                    _add_graph_node(
                        nodes,
                        node_id=recipient_id,
                        node_type="entity",
                        label=row["recipient_entity_name"],
                        entity_type=row["recipient_entity_type"],
                    )
                    _append_graph_edge(
                        edges,
                        source=recipient_id,
                        target=root_id,
                        edge_type="reviewed_party_entity_link",
                        link_type=row["party_link_type"],
                        method=row["party_link_method"],
                        confidence=row["party_link_confidence"],
                        review_status=row["party_link_review_status"],
                        evidence_note=row["party_link_evidence_note"],
                    )
                    source_id = _entity_or_raw_node(
                        nodes,
                        entity_id=row["source_entity_id"],
                        entity_name=row["source_entity_name"],
                        raw_name=row["source_raw_name"],
                        raw_prefix="raw_source",
                    )
                    _append_graph_edge(
                        edges,
                        source=source_id,
                        target=recipient_id,
                        edge_type="money_to_reviewed_party_entities",
                        event_family="money",
                        event_type=row["event_type"],
                        event_count=row["event_count"],
                        reported_amount_event_count=row["reported_amount_event_count"],
                        reviewed_event_count=row["reviewed_event_count"],
                        needs_review_event_count=row["needs_review_event_count"],
                        missing_data_event_count=row["missing_data_event_count"],
                        reported_amount_total=row["reported_amount_total"],
                        first_event_date=row["first_event_date"],
                        last_event_date=row["last_event_date"],
                        source_urls=row["source_urls"],
                        evidence_status="non_rejected_public_disclosure",
                    )
            if include_candidates:
                candidate_rows = _fetch_dicts(
                    conn,
                    """
                    SELECT
                        link.entity_id,
                        entity.canonical_name,
                        entity.entity_type,
                        link.link_type,
                        link.confidence,
                        link.review_status,
                        NULLIF(link.metadata->>'influence_event_count', '')::bigint
                            AS influence_event_count,
                        NULLIF(link.metadata->>'reported_amount_total', '')::numeric
                            AS reported_amount_total
                    FROM party_entity_link link
                    JOIN entity ON entity.id = link.entity_id
                    WHERE link.party_id = %s
                      AND link.review_status = 'needs_review'
                    ORDER BY reported_amount_total DESC NULLS LAST, entity.canonical_name
                    LIMIT %s
                    """,
                    (party_id, min(limit, 50)),
                )
                for row in candidate_rows:
                    candidate_id = _graph_node_id("entity", row["entity_id"])
                    _add_graph_node(
                        nodes,
                        node_id=candidate_id,
                        node_type="entity",
                        label=row["canonical_name"],
                        entity_type=row["entity_type"],
                    )
                    _append_graph_edge(
                        edges,
                        source=candidate_id,
                        target=root_id,
                        edge_type="candidate_party_entity_link",
                        link_type=row["link_type"],
                        confidence=row["confidence"],
                        review_status=row["review_status"],
                        event_count=row["influence_event_count"],
                        reported_amount_total=row["reported_amount_total"],
                        evidence_status="candidate_requires_review",
                    )

        if entity_id is not None:
            entity_rows = _fetch_dicts(
                conn,
                """
                SELECT id, canonical_name, entity_type
                FROM entity
                WHERE id = %s
                """,
                (entity_id,),
            )
            if not entity_rows:
                return {}
            entity = entity_rows[0]
            root_id = _graph_node_id("entity", entity["id"])
            _add_graph_node(
                nodes,
                node_id=root_id,
                node_type="entity",
                label=entity["canonical_name"],
                entity_type=entity["entity_type"],
            )
            rows = _fetch_dicts(
                conn,
                """
                SELECT
                    CASE
                        WHEN influence_event.source_entity_id = %s THEN 'as_source'
                        ELSE 'as_recipient'
                    END AS root_role,
                    influence_event.event_family,
                    influence_event.event_type,
                    counterparty_entity.id AS counterparty_entity_id,
                    counterparty_entity.canonical_name AS counterparty_entity_name,
                    counterparty_person.id AS counterparty_person_id,
                    counterparty_person.display_name AS counterparty_person_name,
                    CASE
                        WHEN influence_event.source_entity_id = %s
                        THEN influence_event.recipient_raw_name
                        ELSE influence_event.source_raw_name
                    END AS counterparty_raw_name,
                    count(DISTINCT influence_event.id) AS event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'reviewed'
                    ) AS reviewed_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE influence_event.review_status = 'needs_review'
                    ) AS needs_review_event_count,
                    count(DISTINCT influence_event.id) FILTER (
                        WHERE jsonb_array_length(influence_event.missing_data_flags) > 0
                    ) AS missing_data_event_count,
                    sum(influence_event.amount) FILTER (
                        WHERE influence_event.amount_status = 'reported'
                          AND influence_event.event_family <> 'campaign_support'
                    ) AS reported_amount_total,
                    min(influence_event.event_date) AS first_event_date,
                    max(influence_event.event_date) AS last_event_date,
                    max(influence_event.metadata->>'claim_scope') AS claim_scope,
                    array_remove(array_agg(DISTINCT source_document.url), NULL) AS source_urls
                FROM influence_event
                LEFT JOIN entity counterparty_entity
                  ON counterparty_entity.id = CASE
                      WHEN influence_event.source_entity_id = %s
                      THEN influence_event.recipient_entity_id
                      ELSE influence_event.source_entity_id
                  END
                LEFT JOIN person counterparty_person
                  ON counterparty_person.id = influence_event.recipient_person_id
                 AND influence_event.source_entity_id = %s
                JOIN source_document
                  ON source_document.id = influence_event.source_document_id
                WHERE (
                        influence_event.source_entity_id = %s
                        OR influence_event.recipient_entity_id = %s
                  )
                  AND influence_event.review_status <> 'rejected'
                  AND influence_event.event_family <> 'campaign_support'
                GROUP BY
                    root_role,
                    influence_event.event_family,
                    influence_event.event_type,
                    counterparty_entity.id,
                    counterparty_entity.canonical_name,
                    counterparty_person.id,
                    counterparty_person.display_name,
                    counterparty_raw_name
                ORDER BY reported_amount_total DESC NULLS LAST, event_count DESC
                LIMIT %s
                """,
                (entity_id, entity_id, entity_id, entity_id, entity_id, entity_id, limit),
            )
            for row in rows:
                if row["counterparty_person_id"] is not None:
                    other_id = _graph_node_id("person", row["counterparty_person_id"])
                    _add_graph_node(
                        nodes,
                        node_id=other_id,
                        node_type="person",
                        label=row["counterparty_person_name"],
                    )
                else:
                    other_id = _entity_or_raw_node(
                        nodes,
                        entity_id=row["counterparty_entity_id"],
                        entity_name=row["counterparty_entity_name"],
                        raw_name=row["counterparty_raw_name"],
                        raw_prefix="raw_counterparty",
                    )
                source_id, target_id = (
                    (root_id, other_id) if row["root_role"] == "as_source" else (other_id, root_id)
                )
                _append_graph_edge(
                    edges,
                    source=source_id,
                    target=target_id,
                    edge_type="entity_disclosure_flow",
                    event_family=row["event_family"],
                    event_type=row["event_type"],
                    event_count=row["event_count"],
                    reported_amount_event_count=row["reported_amount_event_count"],
                    reviewed_event_count=row["reviewed_event_count"],
                    needs_review_event_count=row["needs_review_event_count"],
                    missing_data_event_count=row["missing_data_event_count"],
                    reported_amount_total=row["reported_amount_total"],
                    first_event_date=row["first_event_date"],
                    last_event_date=row["last_event_date"],
                    source_urls=row["source_urls"],
                    evidence_status="non_rejected_public_disclosure",
                    claim_scope=row["claim_scope"],
                )

    return _jsonable(
        {
            "root_id": root_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "filters": {
                "person_id": person_id,
                "party_id": party_id,
                "entity_id": entity_id,
                "include_candidates": include_candidates,
                "limit": limit,
            },
            "caveat": GRAPH_CAVEAT,
        }
    )


def get_electorate_profile(electorate_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        electorate_rows = _fetch_dicts(
            conn,
            """
            SELECT
                electorate.id,
                electorate.name,
                electorate.chamber,
                electorate.state_or_territory,
                EXISTS (
                    SELECT 1
                    FROM electorate_boundary boundary
                    WHERE boundary.electorate_id = electorate.id
                ) AS has_boundary
            FROM electorate
            WHERE electorate.id = %s
            """,
            (electorate_id,),
        )
        if not electorate_rows:
            return {}
        representatives = _fetch_dicts(
            conn,
            """
            SELECT
                person.id AS person_id,
                person.display_name,
                party.id AS party_id,
                party.name AS party_name,
                office_term.chamber,
                office_term.term_start,
                office_term.term_end
            FROM office_term
            JOIN person ON person.id = office_term.person_id
            LEFT JOIN party ON party.id = office_term.party_id
            WHERE office_term.electorate_id = %s
            ORDER BY office_term.term_end NULLS FIRST, person.display_name
            """,
            (electorate_id,),
        )
        influence = _fetch_dicts(
            conn,
            """
            SELECT
                ie.recipient_person_id AS person_id,
                person.display_name AS person_name,
                count(*) AS influence_event_count,
                sum(ie.amount) FILTER (
                    WHERE ie.amount_status = 'reported'
                      AND ie.event_family <> 'campaign_support'
                ) AS reported_amount_total,
                count(*) FILTER (WHERE ie.event_family = 'money') AS money_event_count,
                count(*) FILTER (WHERE ie.event_family = 'benefit') AS benefit_event_count,
                count(*) FILTER (
                    WHERE ie.event_family = 'campaign_support'
                ) AS campaign_support_event_count,
                sum(ie.amount) FILTER (
                    WHERE ie.amount_status = 'reported'
                      AND ie.event_family = 'campaign_support'
                ) AS campaign_support_reported_amount_total,
                count(*) FILTER (WHERE ie.review_status = 'needs_review') AS needs_review_event_count
            FROM influence_event ie
            JOIN person ON person.id = ie.recipient_person_id
            JOIN office_term
              ON office_term.person_id = person.id
             AND office_term.electorate_id = %s
             AND office_term.term_end IS NULL
            WHERE ie.review_status <> 'rejected'
            GROUP BY ie.recipient_person_id, person.display_name
            ORDER BY influence_event_count DESC, person.display_name
            """,
            (electorate_id,),
        )
    return _jsonable(
        {
            "electorate": electorate_rows[0],
            "representatives": representatives,
            "current_representative_influence_summary": influence,
            "caveat": SEARCH_CAVEAT,
        }
    )


def get_influence_context(
    *,
    person_id: int | None = None,
    topic_id: int | None = None,
    public_sector: str | None = None,
    limit: int = 50,
    database_url: str | None = None,
) -> dict[str, Any]:
    conditions = []
    params: list[Any] = []
    if person_id is not None:
        conditions.append("person_id = %s")
        params.append(person_id)
    if topic_id is not None:
        conditions.append("topic_id = %s")
        params.append(topic_id)
    if public_sector:
        conditions.append("public_sector = %s")
        params.append(public_sector)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    limit = max(1, min(limit, 200))
    params.append(limit)

    with connect(database_url) as conn:
        rows = _fetch_dicts(
            conn,
            f"""
            SELECT *
            FROM person_policy_influence_context
            {where_clause}
            ORDER BY lifetime_influence_event_count DESC, person_name, topic_label, public_sector
            LIMIT %s
            """,
            tuple(params),
        )
    return _jsonable(
        {
            "rows": rows,
            "row_count": len(rows),
            "caveat": INFLUENCE_CONTEXT_CAVEAT,
        }
    )


def healthcheck(*, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    return {"status": "ok", "database": "ok"}
