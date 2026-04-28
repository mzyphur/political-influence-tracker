from __future__ import annotations

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


def _search_representatives(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            person.id,
            person.display_name,
            person.canonical_name,
            office_term.chamber,
            electorate.name AS electorate_name,
            electorate.state_or_territory,
            party.name AS party_name
        FROM person
        LEFT JOIN office_term
          ON office_term.person_id = person.id
         AND office_term.term_end IS NULL
        LEFT JOIN electorate ON electorate.id = office_term.electorate_id
        LEFT JOIN party ON party.id = office_term.party_id
        WHERE person.display_name ILIKE %s
           OR person.canonical_name ILIKE %s
        ORDER BY
            CASE WHEN person.display_name ILIKE %s THEN 0 ELSE 1 END,
            person.display_name
        LIMIT %s
        """,
        (pattern, pattern, pattern, limit),
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


def _search_electorates(conn, pattern: str, limit: int) -> list[dict[str, Any]]:
    rows = _fetch_dicts(
        conn,
        """
        SELECT
            electorate.id,
            electorate.name,
            electorate.chamber,
            electorate.state_or_territory,
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
        ORDER BY electorate.name
        LIMIT %s
        """,
        (pattern, pattern, limit),
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
    results: list[dict[str, Any]] = []
    with connect(database_url) as conn:
        if "postcode" in requested_types:
            results.extend(_search_postcodes(conn, cleaned, limit, limitations))
        if "representative" in requested_types:
            results.extend(_search_representatives(conn, pattern, limit))
        if "electorate" in requested_types:
            results.extend(_search_electorates(conn, pattern, limit))
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
            """
            SELECT
                office_term.chamber,
                office_term.term_start,
                office_term.term_end,
                electorate.id AS electorate_id,
                electorate.name AS electorate_name,
                electorate.state_or_territory,
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
