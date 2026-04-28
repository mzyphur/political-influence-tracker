from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from psycopg.rows import dict_row

from au_politics_money.config import API_MIN_FREE_TEXT_QUERY_LENGTH
from au_politics_money.db.load import connect


SEARCH_TYPES = {
    "representative",
    "electorate",
    "party",
    "entity",
    "sector",
    "policy_topic",
    "postcode",
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


def _search_parties(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            party.id,
            party.name,
            party.short_name,
            count(DISTINCT office_term.person_id) FILTER (
                WHERE office_term.term_end IS NULL
            ) AS current_representative_count
        FROM party
        LEFT JOIN office_term ON office_term.party_id = party.id
        WHERE party.name ILIKE %s
           OR party.short_name ILIKE %s
        GROUP BY party.id, party.name, party.short_name
        ORDER BY current_representative_count DESC, party.name
        LIMIT %s
        """,
        (pattern, pattern, limit),
    )
    return [
        _result(
            result_type="party",
            result_id=row["id"],
            label=row["name"],
            subtitle=f"{row['current_representative_count']} current representatives",
            rank=30,
            metadata=row,
        )
        for row in rows
    ]


def _search_entities(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            entity.id,
            entity.canonical_name,
            entity.entity_type,
            count(influence_event.id) AS influence_event_count,
            sum(influence_event.amount) FILTER (
                WHERE influence_event.amount_status = 'reported'
            ) AS reported_amount_total
        FROM entity
        LEFT JOIN influence_event ON influence_event.source_entity_id = entity.id
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
            electorate.id AS electorate_id,
            electorate.name AS electorate_name,
            electorate.state_or_territory
        FROM postcode_electorate_crosswalk crosswalk
        JOIN electorate ON electorate.id = crosswalk.electorate_id
        WHERE crosswalk.postcode = %s
        ORDER BY crosswalk.confidence DESC, electorate.name
        LIMIT %s
        """,
        (query, limit),
    )
    return [
        _result(
            result_type="postcode",
            result_id=f"{row['postcode']}:{row['electorate_id']}",
            label=f"{row['postcode']} -> {row['electorate_name']}",
            subtitle=row.get("state_or_territory") or "",
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
            results.extend(_search_parties(conn, pattern, limit))
        if "entity" in requested_types:
            results.extend(_search_entities(conn, pattern, limit))
        if "policy_topic" in requested_types:
            results.extend(_search_policy_topics(conn, pattern, limit))
        if "sector" in requested_types:
            results.extend(_search_sectors(conn, pattern, limit))

    results = sorted(results, key=lambda item: (item["rank"], item["label"].lower()))[:limit]
    return {
        "query": query,
        "normalized_query": cleaned,
        "results": results,
        "result_count": len(results),
        "limitations": limitations,
        "caveat": SEARCH_CAVEAT,
    }


def get_electorate_map(
    *,
    chamber: str = "house",
    state: str | None = None,
    boundary_set: str | None = None,
    include_geometry: bool = True,
    simplify_tolerance: float = 0.0005,
    database_url: str | None = None,
) -> dict[str, Any]:
    chamber = chamber.strip().lower()
    if chamber not in {"house", "senate"}:
        raise ValueError("chamber must be 'house' or 'senate'.")
    state = state.strip().upper() if state else None
    simplify_tolerance = max(0.0, min(float(simplify_tolerance), 0.25))
    if chamber == "senate":
        return _get_senate_map(
            state=state,
            boundary_set=boundary_set,
            include_geometry=include_geometry,
            simplify_tolerance=simplify_tolerance,
            database_url=database_url,
        )
    geometry_expression = (
        """
        ST_AsGeoJSON(
            ST_Multi(ST_SimplifyPreserveTopology(boundary.geom, %s)),
            6
        ) AS geometry_geojson
        """
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
                COALESCE(influence_summary.needs_review_event_count, 0)
                    AS current_representative_needs_review_event_count,
                COALESCE(influence_summary.official_record_event_count, 0)
                    AS current_representative_official_record_event_count,
                influence_summary.reported_amount_total
                    AS current_representative_lifetime_reported_amount_total,
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
                    ) AS reported_amount_total
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
                count(*) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_event_count,
                sum(amount) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE review_status <> 'rejected'
            """,
            (),
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
            GROUP BY chamber
            ORDER BY chamber
            """,
            (),
        )

    totals = influence_total_rows[0] if influence_total_rows else {}
    federal_status = "active"
    state_status = "planned"
    council_status = "planned"
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
            "id": "federal_influence_events",
            "label": "Disclosed money, gifts, interests, and roles",
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
            "attribution": "adapter-ready, not yet ingested",
            "counts": {},
        },
        {
            "id": "local_council_disclosures",
            "label": "Council/local disclosures and meeting records",
            "level": "council",
            "status": council_status,
            "attribution": "adapter-ready, not yet ingested",
            "counts": {},
        },
    ]

    return _jsonable(
        {
            "status": "ok",
            "active_country": "AU",
            "active_levels": ["federal"],
            "planned_levels": ["state", "council"],
            "coverage_layers": layers,
            "source_documents": source_rows,
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


def _get_senate_map(
    *,
    state: str | None = None,
    boundary_set: str | None = None,
    include_geometry: bool = True,
    simplify_tolerance: float = 0.01,
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
                    boundary.geom
                FROM electorate_boundary boundary
                JOIN electorate house_electorate
                  ON house_electorate.id = boundary.electorate_id
                 AND house_electorate.chamber = 'house'
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
                COALESCE(influence_summary.needs_review_event_count, 0)
                    AS current_representative_needs_review_event_count,
                COALESCE(influence_summary.official_record_event_count, 0)
                    AS current_representative_official_record_event_count,
                influence_summary.reported_amount_total
                    AS current_representative_lifetime_reported_amount_total,
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
                    ) AS reported_amount_total
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
            "map_geometry_scope": "state_territory_composite_from_house_boundaries",
        },
        "caveat": (
            f"{MAP_CAVEAT} Senate map geometries are state/territory features "
            "derived from source-backed federal House electorate boundaries; "
            "senator lists and counts come from Senate office records."
        ),
    }


def get_representative_profile(person_id: int, *, database_url: str | None = None) -> dict[str, Any]:
    with connect(database_url) as conn:
        person_rows = _fetch_dicts(
            conn,
            """
            SELECT id, external_key, display_name, canonical_name, metadata
            FROM person
            WHERE id = %s
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
                count(*) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_event_count,
                sum(amount) FILTER (WHERE amount_status = 'reported')
                    AS reported_amount_total,
                min(event_date) AS first_event_date,
                max(event_date) AS last_event_date
            FROM influence_event
            WHERE recipient_person_id = %s
              AND review_status <> 'rejected'
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
                influence_event.evidence_status,
                influence_event.review_status,
                influence_event.missing_data_flags,
                influence_event.source_ref,
                source_document.url AS source_url,
                source_document.final_url AS source_final_url
            FROM influence_event
            LEFT JOIN entity source_entity
              ON source_entity.id = influence_event.source_entity_id
            JOIN source_document
              ON source_document.id = influence_event.source_document_id
            WHERE influence_event.recipient_person_id = %s
              AND influence_event.review_status <> 'rejected'
            ORDER BY
                influence_event.event_date DESC NULLS LAST,
                influence_event.date_reported DESC NULLS LAST,
                influence_event.id DESC
            LIMIT 50
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
            "person": person_rows[0],
            "office_terms": terms,
            "event_summary": event_summary,
            "recent_events": recent_events,
            "influence_by_sector": influence,
            "vote_topics": votes,
            "source_effect_context": context,
            "caveat": INFLUENCE_CONTEXT_CAVEAT,
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
                sum(ie.amount) FILTER (WHERE ie.amount_status = 'reported') AS reported_amount_total,
                count(*) FILTER (WHERE ie.event_family = 'money') AS money_event_count,
                count(*) FILTER (WHERE ie.event_family = 'benefit') AS benefit_event_count,
                count(*) FILTER (WHERE ie.review_status = 'needs_review') AS needs_review_event_count
            FROM influence_event ie
            JOIN person ON person.id = ie.recipient_person_id
            JOIN office_term
              ON office_term.person_id = person.id
             AND office_term.electorate_id = %s
             AND office_term.term_end IS NULL
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
