from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from au_politics_money.api.app import app
from au_politics_money.config import PROJECT_ROOT
from au_politics_money.db.load import (
    apply_migrations,
    apply_schema,
    connect,
    link_aec_direct_representative_money_flows,
    load_influence_events,
)
from au_politics_money.db.party_entity_suggestions import (
    materialize_party_entity_link_candidates,
)
from au_politics_money.db.review import (
    ReviewImportError,
    export_review_queue,
    import_review_decisions,
    reapply_review_decisions,
)


@dataclass(frozen=True)
class IntegrationDatabase:
    url: str
    schema_name: str
    person_id: int
    electorate_id: int
    entity_id: int
    topic_id: int


def _test_database_url() -> str:
    url = os.environ.get("DATABASE_URL_TEST")
    if not url:
        pytest.skip("DATABASE_URL_TEST is required for Postgres integration tests.")
    if os.environ.get("AUPOL_RUN_POSTGRES_INTEGRATION") != "1" and os.environ.get("CI") != "true":
        pytest.skip(
            "Set AUPOL_RUN_POSTGRES_INTEGRATION=1 to run Postgres integration tests locally."
        )
    if url == os.environ.get("DATABASE_URL") and os.environ.get("CI") != "true":
        pytest.fail("DATABASE_URL_TEST must not be identical to DATABASE_URL outside CI.")
    parsed = urlparse(url)
    host = parsed.hostname or ""
    local_hosts = {"localhost", "127.0.0.1", "::1"}
    test_marker_present = "test" in parsed.path.lower() or "test" in (
        parsed.username or ""
    ).lower()
    if host not in local_hosts and os.environ.get("CI") != "true" and not test_marker_present:
        pytest.fail(
            "DATABASE_URL_TEST must point at localhost, CI, or a clearly test-named database/user."
        )
    return url


def _with_search_path(database_url: str, schema_name: str) -> str:
    parsed = urlparse(database_url)
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "options"
    ]
    query_items.append(("options", f"-csearch_path={schema_name},public"))
    return urlunparse(parsed._replace(query=urlencode(query_items)))


def _migration_count() -> int:
    schema_dir = PROJECT_ROOT / "backend" / "schema"
    return sum(1 for path in schema_dir.glob("*.sql") if path.name != "001_initial.sql")


@pytest.fixture()
def integration_db(monkeypatch: pytest.MonkeyPatch) -> Iterator[IntegrationDatabase]:
    base_url = _test_database_url()
    schema_name = f"pytest_{uuid.uuid4().hex}"
    database_url = _with_search_path(base_url, schema_name)
    schema_created = False

    try:
        with connect(base_url) as admin_conn:
            admin_conn.execute(f'CREATE SCHEMA "{schema_name}"')
            admin_conn.commit()
            schema_created = True

        with connect(database_url) as conn:
            apply_schema(conn)
            migration_summary = apply_migrations(conn)
            assert migration_summary["migrations_applied"] == _migration_count()
            assert apply_migrations(conn)["migrations_applied"] == 0
            _assert_expected_indexes(conn)
            ids = _seed_minimal_influence_graph(conn)

        monkeypatch.setenv("DATABASE_URL", database_url)
        yield IntegrationDatabase(database_url, schema_name, **ids)
    finally:
        if schema_created:
            with connect(base_url) as admin_conn:
                admin_conn.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')
                admin_conn.commit()


def _assert_expected_indexes(conn) -> None:
    with conn.cursor() as cur:
        for index_name in (
            "person_display_name_trgm_idx",
            "electorate_name_trgm_idx",
            "policy_topic_label_trgm_idx",
            "policy_topic_slug_trgm_idx",
            "entity_industry_public_sector_trgm_idx",
            "influence_event_recipient_entity_idx",
            "vote_division_external_id_idx",
        ):
            cur.execute("SELECT to_regclass(%s)", (index_name,))
            assert cur.fetchone()[0] is not None, index_name


def _seed_minimal_influence_graph(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_document (
                source_id, source_name, source_type, jurisdiction, url, fetched_at,
                http_status, content_type, sha256, storage_path, metadata
            )
            VALUES (
                'pytest-source', 'Pytest Source', 'test_fixture', 'Commonwealth',
                'https://example.test/source', now(), 200, 'application/json',
                'pytest-sha256', '/tmp/pytest-source.json', '{}'::jsonb
            )
            RETURNING id
            """
        )
        source_document_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO jurisdiction (name, level, code)
            VALUES ('Commonwealth of Australia', 'federal', 'CWLTH')
            RETURNING id
            """
        )
        jurisdiction_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO party (name, short_name, jurisdiction_id, source_document_id)
            VALUES ('Example Party', 'EX', %s, %s)
            RETURNING id
            """,
            (jurisdiction_id, source_document_id),
        )
        party_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, state_or_territory, source_document_id
            )
            VALUES ('Melbourne', %s, 'house', 'VIC', %s)
            RETURNING id
            """,
            (jurisdiction_id, source_document_id),
        )
        electorate_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, state_or_territory, source_document_id
            )
            VALUES ('Senate - VIC', %s, 'senate', 'VIC', %s)
            RETURNING id
            """,
            (jurisdiction_id, source_document_id),
        )
        senate_electorate_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, state_or_territory, source_document_id
            )
            VALUES ('Farrer', %s, 'house', '', %s)
            RETURNING id
            """,
            (jurisdiction_id, source_document_id),
        )
        farrer_electorate_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, state_or_territory, source_document_id
            )
            VALUES ('Senate - NSW', %s, 'senate', 'NSW', %s)
            RETURNING id
            """,
            (jurisdiction_id, source_document_id),
        )
        nsw_senate_electorate_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO electorate_boundary (
                electorate_id, boundary_set, valid_from, geom, source_document_id, metadata
            )
            VALUES (
                %s, 'pytest_boundary_set', '2025-01-01',
                ST_Multi(ST_GeomFromText(
                    'POLYGON((144.90 -37.85,145.00 -37.85,145.00 -37.75,144.90 -37.75,144.90 -37.85))',
                    4326
                )),
                %s, %s
            )
            """,
            (electorate_id, source_document_id, Jsonb({"fixture": True})),
        )

        cur.execute(
            """
            INSERT INTO electorate_boundary (
                electorate_id, boundary_set, valid_from, geom, source_document_id, metadata
            )
            VALUES (
                %s, 'pytest_boundary_set', '2025-01-01',
                ST_Multi(ST_GeomFromText(
                    'POLYGON((145.00 -35.00,145.10 -35.00,145.10 -34.90,145.00 -34.90,145.00 -35.00))',
                    4326
                )),
                %s, %s
            )
            """,
            (farrer_electorate_id, source_document_id, Jsonb({"fixture": True})),
        )

        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, first_name, last_name,
                source_document_id, metadata
            )
            VALUES (
                'person:jane-citizen', 'Jane Citizen', 'Jane Citizen', 'Jane',
                'Citizen', %s, %s
            )
            RETURNING id
            """,
            (source_document_id, Jsonb({"fixture": True})),
        )
        person_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, first_name, last_name,
                source_document_id, metadata
            )
            VALUES (
                'person:alex-senator', 'Alex Senator', 'Alex Senator', 'Alex',
                'Senator', %s, %s
            )
            RETURNING id
            """,
            (source_document_id, Jsonb({"fixture": True})),
        )
        senator_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, first_name, last_name,
                source_document_id, metadata
            )
            VALUES (
                'person:pat-farrer', 'Pat Farrer', 'Pat Farrer', 'Pat',
                'Farrer', %s, %s
            )
            RETURNING id
            """,
            (source_document_id, Jsonb({"fixture": True})),
        )
        farrer_person_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO person (
                external_key, display_name, canonical_name, first_name, last_name,
                source_document_id, metadata
            )
            VALUES (
                'person:sam-senator', 'Sam Senator', 'Sam Senator', 'Sam',
                'Senator', %s, %s
            )
            RETURNING id
            """,
            (source_document_id, Jsonb({"fixture": True})),
        )
        nsw_senator_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id, role_title,
                term_start, source_document_id
            )
            VALUES (
                'term:jane-citizen-current', %s, 'house', %s, %s, 'MP',
                '2022-05-21', %s
            )
            """,
            (person_id, electorate_id, party_id, source_document_id),
        )

        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id, role_title,
                term_start, source_document_id, metadata
            )
            VALUES (
                'term:pat-farrer-current', %s, 'house', %s, %s, 'MP',
                '2022-05-21', %s, %s
            )
            """,
            (
                farrer_person_id,
                farrer_electorate_id,
                party_id,
                source_document_id,
                Jsonb({"state": "New South Wales"}),
            ),
        )

        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id, role_title,
                term_start, source_document_id, metadata
            )
            VALUES (
                'term:alex-senator-current', %s, 'senate', %s, %s, 'Senator',
                '2022-07-01', %s, %s
            )
            """,
            (
                senator_id,
                senate_electorate_id,
                party_id,
                source_document_id,
                Jsonb({"state": "VIC"}),
            ),
        )

        cur.execute(
            """
            INSERT INTO office_term (
                external_key, person_id, chamber, electorate_id, party_id, role_title,
                term_start, source_document_id, metadata
            )
            VALUES (
                'term:sam-senator-current', %s, 'senate', %s, %s, 'Senator',
                '2022-07-01', %s, %s
            )
            """,
            (
                nsw_senator_id,
                nsw_senate_electorate_id,
                party_id,
                source_document_id,
                Jsonb({"state": "NSW"}),
            ),
        )

        cur.execute(
            """
            INSERT INTO entity (
                canonical_name, normalized_name, entity_type, country, source_document_id
            )
            VALUES ('Clean Energy Pty Ltd', 'clean energy pty ltd', 'company', 'AU', %s)
            RETURNING id
            """,
            (source_document_id,),
        )
        entity_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO entity_industry_classification (
                entity_id, public_sector, method, confidence, evidence_note,
                source_document_id
            )
            VALUES (
                %s, 'renewable_energy', 'manual', 'manual_reviewed',
                'Fixture reviewed sector classification.', %s
            )
            """,
            (entity_id, source_document_id),
        )

        cur.execute(
            """
            INSERT INTO influence_event (
                external_key, event_family, event_type, source_entity_id,
                source_raw_name, recipient_person_id, recipient_raw_name,
                jurisdiction_id, amount, amount_status, event_date, chamber,
                disclosure_system, evidence_status, extraction_method, review_status,
                description, source_document_id, source_ref, missing_data_flags,
                metadata
            )
            VALUES (
                'influence:clean-energy:jane-citizen:2023', 'money',
                'donation_or_gift', %s, 'Clean Energy Pty Ltd', %s,
                'Jane Citizen', %s, 1250.00, 'reported', '2023-02-14', 'house',
                'pytest fixture', 'official_record', 'fixture_seed', 'not_required',
                'Fixture disclosed donation from Clean Energy Pty Ltd.',
                %s, 'fixture-row-1', '[]'::jsonb, %s
            )
            """,
            (
                entity_id,
                person_id,
                jurisdiction_id,
                source_document_id,
                Jsonb({"fixture": True}),
            ),
        )

        cur.execute(
            """
            INSERT INTO influence_event (
                external_key, event_family, event_type, source_entity_id,
                source_raw_name, recipient_person_id, recipient_raw_name,
                jurisdiction_id, amount, amount_status, event_date, chamber,
                disclosure_system, evidence_status, extraction_method, review_status,
                description, source_document_id, source_ref, missing_data_flags,
                metadata
            )
            VALUES (
                'influence:clean-energy:jane-citizen:rejected', 'money',
                'donation_or_gift', %s, 'Clean Energy Pty Ltd', %s,
                'Jane Citizen', %s, 9999.00, 'reported', '2023-02-15', 'house',
                'pytest fixture', 'official_record', 'fixture_seed', 'rejected',
                'Fixture rejected event that public surfaces must exclude.',
                %s, 'fixture-row-rejected', '[]'::jsonb, %s
            )
            """,
            (
                entity_id,
                person_id,
                jurisdiction_id,
                source_document_id,
                Jsonb({"fixture": True}),
            ),
        )

        cur.execute(
            """
            INSERT INTO vote_division (
                external_id, chamber, division_date, division_number, title,
                bill_name, motion_text, aye_count, no_count, source_document_id
            )
            VALUES (
                'division:climate-1', 'house', '2023-03-01', 1,
                'Climate Transition Bill', 'Climate Transition Bill',
                'That the bill be read a second time.', 1, 0, %s
            )
            RETURNING id
            """,
            (source_document_id,),
        )
        division_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO person_vote (
                division_id, person_id, vote, party_id, rebelled_against_party,
                source_document_id
            )
            VALUES (%s, %s, 'aye', %s, false, %s)
            """,
            (division_id, person_id, party_id, source_document_id),
        )

        cur.execute(
            """
            INSERT INTO policy_topic (slug, label, description, metadata)
            VALUES (
                'climate_transition', 'Climate Transition',
                'Fixture policy topic for integration testing.', %s
            )
            RETURNING id
            """,
            (Jsonb({"fixture": True}),),
        )
        topic_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO division_topic (
                division_id, topic_id, method, confidence, evidence_note
            )
            VALUES (
                %s, %s, 'manual', 1.000,
                'Fixture manual link between division and climate topic.'
            )
            """,
            (division_id, topic_id),
        )

        cur.execute(
            """
            INSERT INTO sector_policy_topic_link (
                public_sector, topic_id, relationship, method, confidence,
                evidence_note, review_status, reviewer, reviewed_at, metadata
            )
            VALUES (
                'renewable_energy', %s, 'direct_material_interest', 'manual',
                1.000, 'Fixture reviewed sector-policy link.', 'reviewed',
                'pytest', now(), %s
            )
            """,
            (topic_id, Jsonb({"fixture": True})),
        )
    conn.commit()
    return {
        "person_id": person_id,
        "electorate_id": electorate_id,
        "entity_id": entity_id,
        "topic_id": topic_id,
    }


def test_postgres_schema_migrations_and_api_queries(integration_db: IntegrationDatabase) -> None:
    client = TestClient(app)

    health_response = client.get("/api/health")
    assert health_response.status_code == 200
    assert health_response.json()["database"] == "ok"

    map_response = client.get(
        "/api/map/electorates",
        params={"state": "VIC", "boundary_set": "pytest_boundary_set"},
    )
    assert map_response.status_code == 200
    map_payload = map_response.json()
    assert map_payload["type"] == "FeatureCollection"
    assert map_payload["feature_count"] == 1
    map_feature = map_payload["features"][0]
    assert map_feature["geometry"]["type"] == "MultiPolygon"
    assert map_feature["geometry"]["coordinates"][0][0][0] == [144.9, -37.85]
    assert map_feature["properties"]["boundary_set"] == "pytest_boundary_set"
    assert map_feature["properties"]["has_boundary"] is True
    assert map_feature["properties"]["representative_name"] == "Jane Citizen"
    assert map_feature["properties"]["current_representative_count"] == 1
    assert map_feature["properties"]["current_representatives"][0]["display_name"] == "Jane Citizen"
    assert map_feature["properties"]["party_breakdown"][0]["party_name"] == "Example Party"
    assert (
        map_feature["properties"]["current_representative_lifetime_influence_event_count"] == 1
    )
    assert map_feature["properties"]["current_representative_official_record_event_count"] == 1

    missing_boundary_response = client.get(
        "/api/map/electorates",
        params={"state": "VIC", "boundary_set": "missing_boundary_set"},
    )
    assert missing_boundary_response.status_code == 200
    assert missing_boundary_response.json()["feature_count"] == 0

    no_geometry_response = client.get(
        "/api/map/electorates",
        params={
            "state": "VIC",
            "boundary_set": "pytest_boundary_set",
            "include_geometry": "false",
        },
    )
    assert no_geometry_response.status_code == 200
    assert no_geometry_response.json()["features"][0]["geometry"] is None

    senate_map_response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "senate",
            "state": "VIC",
            "boundary_set": "pytest_boundary_set",
        },
    )
    assert senate_map_response.status_code == 200
    senate_payload = senate_map_response.json()
    assert senate_payload["feature_count"] == 1
    senate_feature = senate_payload["features"][0]
    assert senate_feature["geometry"]["type"] == "MultiPolygon"
    assert senate_feature["properties"]["electorate_name"] == "Senate - VIC"
    assert senate_feature["properties"]["current_representative_count"] == 1
    assert senate_feature["properties"]["representative_name"] is None
    assert (
        senate_feature["properties"]["map_geometry_scope"]
        == "state_territory_composite_from_house_boundaries"
    )

    nsw_house_map_response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "house",
            "state": "NSW",
            "boundary_set": "pytest_boundary_set",
        },
    )
    assert nsw_house_map_response.status_code == 200
    nsw_house_payload = nsw_house_map_response.json()
    assert nsw_house_payload["feature_count"] == 1
    assert nsw_house_payload["features"][0]["properties"]["electorate_name"] == "Farrer"
    assert nsw_house_payload["features"][0]["properties"]["state_or_territory"] == "NSW"

    nsw_senate_map_response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "senate",
            "state": "NSW",
            "boundary_set": "pytest_boundary_set",
        },
    )
    assert nsw_senate_map_response.status_code == 200
    nsw_senate_payload = nsw_senate_map_response.json()
    assert nsw_senate_payload["feature_count"] == 1
    assert nsw_senate_payload["features"][0]["properties"]["electorate_name"] == "Senate - NSW"
    assert nsw_senate_payload["features"][0]["properties"]["has_boundary"] is True

    coverage_response = client.get("/api/coverage")
    assert coverage_response.status_code == 200
    coverage_payload = coverage_response.json()
    assert coverage_payload["active_country"] == "AU"
    assert coverage_payload["active_levels"] == ["federal"]
    assert coverage_payload["influence_event_totals"]["event_count"] == 1
    assert coverage_payload["influence_event_totals"]["person_linked_event_count"] == 1
    assert {
        layer["id"]: layer["status"] for layer in coverage_payload["coverage_layers"]
    }["state_territory_disclosures"] == "planned"

    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    assert {
        row["event_family"]: row["event_count"]
        for row in representative_payload["event_summary"]
    }["money"] == 1
    assert representative_payload["influence_by_sector"][0]["influence_event_count"] == 1
    assert representative_payload["source_effect_context"][0]["lifetime_influence_event_count"] == 1
    assert representative_payload["recent_events"][0]["source_raw_name"] == "Clean Energy Pty Ltd"
    assert len(representative_payload["recent_events"]) == 1

    electorate_response = client.get(f"/api/electorates/{integration_db.electorate_id}")
    assert electorate_response.status_code == 200
    electorate_payload = electorate_response.json()
    assert (
        electorate_payload["current_representative_influence_summary"][0][
            "influence_event_count"
        ]
        == 1
    )

    search_response = client.get(
        "/api/search",
        params=[("q", "Jane Citizen"), ("types", "representative"), ("limit", "5")],
    )
    assert search_response.status_code == 200
    search_payload = search_response.json()
    assert search_payload["result_count"] == 1
    assert search_payload["results"][0]["id"] == integration_db.person_id

    entity_search_response = client.get(
        "/api/search",
        params=[("q", "Clean Energy"), ("types", "entity"), ("limit", "5")],
    )
    assert entity_search_response.status_code == 200
    entity_search_payload = entity_search_response.json()
    assert entity_search_payload["result_count"] == 1
    assert entity_search_payload["results"][0]["metadata"]["influence_event_count"] == 1
    assert search_payload["results"][0]["label"] == "Jane Citizen"

    token_search_response = client.get(
        "/api/search",
        params=[("q", "Senator Alex"), ("types", "representative"), ("limit", "5")],
    )
    assert token_search_response.status_code == 200
    token_results = token_search_response.json()["results"]
    assert token_results[0]["label"] == "Alex Senator"
    assert token_results[0]["metadata"]["chamber"] == "senate"
    assert token_results[0]["metadata"]["state_or_territory"] == "VIC"

    broad_search_response = client.get(
        "/api/search",
        params=[("q", "Climate"), ("types", "policy_topic"), ("types", "party")],
    )
    assert broad_search_response.status_code == 200
    broad_search_types = {result["type"] for result in broad_search_response.json()["results"]}
    assert "policy_topic" in broad_search_types

    entity_search_response = client.get(
        "/api/search",
        params=[("q", "Clean Energy"), ("types", "entity")],
    )
    assert entity_search_response.status_code == 200
    entity_search_types = {result["type"] for result in entity_search_response.json()["results"]}
    assert "entity" in entity_search_types

    sector_search_response = client.get(
        "/api/search",
        params=[("q", "renewable"), ("types", "sector")],
    )
    assert sector_search_response.status_code == 200
    sector_search_types = {result["type"] for result in sector_search_response.json()["results"]}
    assert "sector" in sector_search_types

    electorate_response = client.get(f"/api/electorates/{integration_db.electorate_id}")
    assert electorate_response.status_code == 200
    electorate_payload = electorate_response.json()
    assert electorate_payload["electorate"]["name"] == "Melbourne"
    assert electorate_payload["current_representative_influence_summary"][0][
        "reported_amount_total"
    ] == 1250.0

    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    assert representative_payload["person"]["display_name"] == "Jane Citizen"
    assert representative_payload["influence_by_sector"][0]["public_sector"] == "renewable_energy"
    assert representative_payload["vote_topics"][0]["topic_slug"] == "climate_transition"
    assert representative_payload["source_effect_context"][0][
        "lifetime_reported_amount_total"
    ] == 1250.0

    graph_response = client.get(
        "/api/graph/influence",
        params={"person_id": integration_db.person_id, "limit": "10"},
    )
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    assert graph_payload["root_id"] == f"person:{integration_db.person_id}"
    assert graph_payload["edge_count"] == 1
    assert graph_payload["edges"][0]["type"] == "disclosed_to_representative"
    assert graph_payload["edges"][0]["reported_amount_total"] == 1250.0
    assert graph_payload["edges"][0]["source_urls"] == ["https://example.test/source"]
    assert graph_payload["edges"][0]["needs_review_event_count"] == 0
    assert graph_payload["edges"][0]["missing_data_event_count"] == 0
    assert len({edge["id"] for edge in graph_payload["edges"]}) == len(graph_payload["edges"])
    assert {node["label"] for node in graph_payload["nodes"]} >= {
        "Jane Citizen",
        "Clean Energy Pty Ltd",
    }

    entity_response = client.get(f"/api/entities/{integration_db.entity_id}")
    assert entity_response.status_code == 200
    entity_payload = entity_response.json()
    assert entity_payload["entity"]["canonical_name"] == "Clean Energy Pty Ltd"
    assert entity_payload["classifications"][0]["public_sector"] == "renewable_energy"
    assert entity_payload["as_source_summary"][0]["event_count"] == 1
    assert entity_payload["top_recipients"][0]["recipient_label"] == "Jane Citizen"
    assert entity_payload["recent_events"][0]["entity_role"] == "as_source"

    entity_graph_response = client.get(
        "/api/graph/influence",
        params={"entity_id": integration_db.entity_id, "limit": "10"},
    )
    assert entity_graph_response.status_code == 200
    entity_graph_payload = entity_graph_response.json()
    assert entity_graph_payload["root_id"] == f"entity:{integration_db.entity_id}"
    assert entity_graph_payload["edges"][0]["type"] == "entity_disclosure_flow"
    assert entity_graph_payload["edges"][0]["source_urls"] == ["https://example.test/source"]

    context_response = client.get(
        "/api/influence-context",
        params={
            "person_id": integration_db.person_id,
            "topic_id": integration_db.topic_id,
            "public_sector": "renewable_energy",
        },
    )
    assert context_response.status_code == 200
    context_payload = context_response.json()
    assert context_payload["row_count"] == 1
    assert context_payload["rows"][0]["relationship"] == "direct_material_interest"


def test_campaign_support_stays_separate_from_direct_money_totals(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type, source_entity_id,
                    source_raw_name, recipient_person_id, recipient_raw_name,
                    jurisdiction_id, amount, amount_status, event_date, chamber,
                    disclosure_system, evidence_status, extraction_method, review_status,
                    description, source_document_id, source_ref, missing_data_flags,
                    metadata
                )
                VALUES (
                    'influence:clean-energy:jane-citizen:campaign-support',
                    'campaign_support',
                    'candidate_or_senate_group_campaign_expenditure',
                    %s, 'Clean Energy Pty Ltd', %s, 'Jane Citizen', %s,
                    5000.00, 'reported', '2025-04-01', 'house',
                    'pytest fixture', 'official_record_parsed', 'fixture_seed',
                    'not_required',
                    'Fixture campaign support connected to the candidate context, not a personal receipt.',
                    %s, 'fixture-campaign-support-row', '[]'::jsonb, %s
                )
                """,
                (
                    integration_db.entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    source_document_id,
                    Jsonb(
                        {
                            "campaign_support_attribution": {
                                "tier": "source_backed_campaign_support_record",
                                "not_personal_receipt": True,
                            },
                            "fixture": True,
                        }
                    ),
                ),
            )
        conn.commit()

    client = TestClient(app)

    map_response = client.get(
        "/api/map/electorates",
        params={"state": "VIC", "boundary_set": "pytest_boundary_set"},
    )
    assert map_response.status_code == 200
    map_properties = map_response.json()["features"][0]["properties"]
    assert map_properties["current_representative_lifetime_influence_event_count"] == 2
    assert map_properties["current_representative_lifetime_campaign_support_event_count"] == 1
    assert map_properties["current_representative_lifetime_reported_amount_total"] == 1250.0
    assert map_properties["current_representative_campaign_support_reported_total"] == 5000.0

    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    assert {
        row["event_family"]: row["reported_amount_total"]
        for row in representative_payload["event_summary"]
    } == {"money": 1250.0}
    assert representative_payload["campaign_support_summary"][0]["event_count"] == 1
    assert representative_payload["campaign_support_summary"][0]["reported_amount_total"] == 5000.0

    graph_response = client.get(
        "/api/graph/influence",
        params={"person_id": integration_db.person_id, "limit": "10"},
    )
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    assert graph_payload["edge_count"] == 1
    assert graph_payload["edges"][0]["reported_amount_total"] == 1250.0

    entity_response = client.get(f"/api/entities/{integration_db.entity_id}")
    assert entity_response.status_code == 200
    entity_payload = entity_response.json()
    by_family = {row["event_family"]: row for row in entity_payload["as_source_summary"]}
    assert by_family["money"]["reported_amount_total"] == 1250.0
    assert by_family["campaign_support"]["event_count"] == 1
    assert by_family["campaign_support"]["reported_amount_total"] is None
    assert entity_payload["top_recipients"][0]["reported_amount_total"] == 1250.0

    entity_graph_response = client.get(
        "/api/graph/influence",
        params={"entity_id": integration_db.entity_id, "limit": "10"},
    )
    assert entity_graph_response.status_code == 200
    entity_graph_payload = entity_graph_response.json()
    assert entity_graph_payload["edge_count"] == 1
    assert entity_graph_payload["edges"][0]["reported_amount_total"] == 1250.0


def test_aec_direct_member_return_rows_link_to_unique_people(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_raw_name, recipient_raw_name, amount,
                    financial_year, return_type, receipt_type, disclosure_category,
                    jurisdiction_id, source_document_id, source_row_ref, confidence,
                    metadata
                )
                VALUES (
                    'aec-direct-member-return:jane-citizen', 'Example Donor Pty Ltd',
                    'Ms Jane Citizen OAM MP', 2500.00, '2024-25',
                    'Member of HOR Return', 'Donation Received', 'detailed_receipt',
                    %s, %s, 'Detailed Receipts.csv:1', 'unresolved', %s
                )
                """,
                (
                    jurisdiction_id,
                    source_document_id,
                    Jsonb({"fixture": True}),
                ),
            )
        conn.commit()

        summary = link_aec_direct_representative_money_flows(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    recipient_person_id,
                    confidence,
                    metadata->'recipient_person_match'->>'status'
                FROM money_flow
                WHERE external_key = 'aec-direct-member-return:jane-citizen'
                """
            )
            recipient_person_id, confidence, status = cur.fetchone()

    assert summary["direct_representative_money_flows_linked"] == 1
    assert recipient_person_id == integration_db.person_id
    assert confidence == "exact_name_context"
    assert status == "linked"


def test_election_disclosure_observations_do_not_inflate_reported_totals(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            rows = [
                (
                    "election-primary-donation",
                    "Example Donor Pty Ltd",
                    "Example Candidate",
                    "election_candidate_or_senate_group_donation_received",
                    "Donation Received",
                    Jsonb(
                        {
                            "source_dataset": "aec_election",
                            "event_name": "2025 Federal Election",
                            "public_amount_counting_role": "primary_transaction",
                            "normalizer_name": "aec_election_money_flow_normalizer",
                            "disclosure_system": "aec_election_financial_disclosure",
                        }
                    ),
                ),
                (
                    "election-duplicate-donation",
                    "Example Donor Pty Ltd",
                    "Example Candidate",
                    "election_donor_donation_made",
                    "Donation Made",
                    Jsonb(
                        {
                            "source_dataset": "aec_election",
                            "event_name": "2025 Federal Election",
                            "public_amount_counting_role": "duplicate_observation",
                            "normalizer_name": "aec_election_money_flow_normalizer",
                            "disclosure_system": "aec_election_financial_disclosure",
                        }
                    ),
                ),
                (
                    "election-campaign-ad",
                    "Example Party",
                    "Example Media Pty Ltd",
                    "election_media_advertising_expenditure",
                    "Media Advertisement",
                    Jsonb(
                        {
                            "source_dataset": "aec_election",
                            "event_name": "2025 Federal Election",
                            "public_amount_counting_role": "single_observation",
                            "normalizer_name": "aec_election_money_flow_normalizer",
                            "disclosure_system": "aec_election_financial_disclosure",
                        }
                    ),
                ),
            ]
            cur.executemany(
                """
                INSERT INTO money_flow (
                    external_key, source_raw_name, recipient_raw_name, amount,
                    financial_year, date_received, return_type, receipt_type,
                    disclosure_category, jurisdiction_id, source_document_id,
                    source_row_ref, confidence, metadata
                )
                VALUES (
                    %s, %s, %s, 1200.00, NULL, '2025-04-14',
                    'Election Candidate Return', %s, %s, %s, %s,
                    'fixture.csv:1', 'unresolved', %s
                )
                """,
                [
                    (
                        external_key,
                        source_raw_name,
                        recipient_raw_name,
                        receipt_type,
                        disclosure_category,
                        jurisdiction_id,
                        source_document_id,
                        metadata,
                    )
                    for (
                        external_key,
                        source_raw_name,
                        recipient_raw_name,
                        disclosure_category,
                        receipt_type,
                        metadata,
                    ) in rows
                ],
            )
        conn.commit()

        load_influence_events(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    money_flow.external_key,
                    influence_event.event_type,
                    influence_event.amount_status,
                    influence_event.reporting_period,
                    influence_event.missing_data_flags
                FROM influence_event
                JOIN money_flow ON money_flow.id = influence_event.money_flow_id
                WHERE money_flow.external_key LIKE 'election-%'
                ORDER BY money_flow.external_key
                """
            )
            loaded_rows = {row[0]: row[1:] for row in cur.fetchall()}

    assert loaded_rows["election-primary-donation"][:3] == (
        "donation_or_gift",
        "reported",
        "2025 Federal Election",
    )
    assert loaded_rows["election-duplicate-donation"][1] == "not_applicable"
    assert (
        "duplicate_disclosure_observation_not_counted_in_reported_total"
        in loaded_rows["election-duplicate-donation"][3]
    )
    assert loaded_rows["election-campaign-ad"][0] == "campaign_expenditure"
    assert loaded_rows["election-campaign-ad"][1] == "not_applicable"
    assert "campaign_expenditure_not_counted_in_reported_total" in loaded_rows[
        "election-campaign-ad"
    ][3]


def test_party_profile_aggregates_reviewed_party_entity_money(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM party WHERE name = 'Example Party'")
            party_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (
                    canonical_name, normalized_name, entity_type, country, source_document_id
                )
                VALUES (
                    'Example Party Federal Campaign',
                    'example party federal campaign',
                    'political_party',
                    'AU',
                    %s
                )
                RETURNING id
                """,
                (source_document_id,),
            )
            party_entity_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (
                    canonical_name, normalized_name, entity_type, country, source_document_id
                )
                VALUES ('Example Donor Pty Ltd', 'example donor pty ltd', 'company', 'AU', %s)
                RETURNING id
                """,
                (source_document_id,),
            )
            donor_entity_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO party_entity_link (
                    party_id, entity_id, link_type, method, confidence, review_status,
                    evidence_note, reviewer, reviewed_at, source_document_id
                )
                VALUES (
                    %s, %s, 'party_branch', 'manual', 'manual_reviewed', 'reviewed',
                    'Fixture reviewed link.', 'pytest', now(), %s
                )
                """,
                (party_id, party_entity_id, source_document_id),
            )
            for external_key, review_status, amount in (
                ("party-profile:accepted", "not_required", "3000.00"),
                ("party-profile:rejected", "rejected", "9999.00"),
            ):
                cur.execute(
                    """
                    INSERT INTO influence_event (
                        external_key, event_family, event_type, source_entity_id,
                        source_raw_name, recipient_entity_id, recipient_raw_name,
                        jurisdiction_id, amount, amount_status, event_date,
                        reporting_period, disclosure_system, evidence_status,
                        extraction_method, review_status, description,
                        source_document_id, source_ref, missing_data_flags, metadata
                    )
                    VALUES (
                        %s, 'money', 'donation_or_gift', %s, 'Example Donor Pty Ltd',
                        %s, 'Example Party Federal Campaign', %s, %s, 'reported',
                        '2024-06-01', '2023-24', 'pytest fixture',
                        'official_record_parsed', 'fixture_seed', %s,
                        'Fixture party disclosure.', %s, 'party-row', '[]'::jsonb, %s
                    )
                    """,
                    (
                        external_key,
                        donor_entity_id,
                        party_entity_id,
                        jurisdiction_id,
                        amount,
                        review_status,
                        source_document_id,
                        Jsonb({"return_type": "Political Party Return"}),
                    ),
                )
        conn.commit()

    client = TestClient(app)
    response = client.get(f"/api/parties/{party_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["party"]["name"] == "Example Party"
    assert payload["linked_entities"][0]["canonical_name"] == "Example Party Federal Campaign"
    assert payload["money_summary"][0]["reported_amount_total"] == 3000.0
    assert payload["top_sources"][0]["source_label"] == "Example Donor Pty Ltd"
    assert payload["recent_events"][0]["review_status"] == "not_required"


def test_party_entity_link_review_accepts_and_rejects_candidates(
    integration_db: IntegrationDatabase,
    tmp_path,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM party WHERE name = 'Example Party'")
            party_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (
                    canonical_name, normalized_name, entity_type, country, source_document_id
                )
                VALUES ('Example Donor Pty Ltd', 'example donor pty ltd', 'company', 'AU', %s)
                RETURNING id
                """,
                (source_document_id,),
            )
            donor_entity_id = cur.fetchone()[0]
            for label, amount in (
                ("Example Party Federal Campaign", 3000),
                ("Example Party Rejected Campaign", 9000),
            ):
                normalized = label.lower()
                cur.execute(
                    """
                    INSERT INTO entity (
                        canonical_name, normalized_name, entity_type, country, source_document_id
                    )
                    VALUES (%s, %s, 'political_party', 'AU', %s)
                    RETURNING id
                    """,
                    (label, normalized, source_document_id),
                )
                entity_id = cur.fetchone()[0]
                cur.execute(
                    """
                    INSERT INTO influence_event (
                        external_key, event_family, event_type, source_entity_id,
                        source_raw_name, recipient_entity_id, recipient_raw_name,
                        jurisdiction_id, amount, amount_status, event_date,
                        reporting_period, disclosure_system, evidence_status,
                        extraction_method, review_status, description,
                        source_document_id, source_ref, missing_data_flags, metadata
                    )
                    VALUES (
                        %s, 'money', 'donation_or_gift', %s, 'Example Donor Pty Ltd',
                        %s, %s, %s, %s, 'reported', '2024-06-01', '2023-24',
                        'pytest fixture', 'official_record_parsed', 'fixture_seed',
                        'not_required', 'Fixture party disclosure.', %s, %s,
                        '[]'::jsonb, %s
                    )
                    """,
                    (
                        f"party-entity-review:{entity_id}",
                        donor_entity_id,
                        entity_id,
                        label,
                        jurisdiction_id,
                        str(amount),
                        source_document_id,
                        f"party-entity-review:{entity_id}",
                        Jsonb({"return_type": "Political Party Return"}),
                    ),
                )
        conn.commit()

        materialize_summary = materialize_party_entity_link_candidates(conn)
        assert materialize_summary["candidates_inserted_or_refreshed"] >= 2

        candidate_response = TestClient(app).get(f"/api/parties/{party_id}")
        assert candidate_response.status_code == 200
        candidate_payload = candidate_response.json()
        assert candidate_payload["linked_entities"] == []
        assert candidate_payload["money_summary"] == []
        candidate_names = {
            entity["canonical_name"] for entity in candidate_payload["candidate_entities"]
        }
        assert "Example Party Federal Campaign" in candidate_names
        assert "Example Party Rejected Campaign" in candidate_names

        queue_path = export_review_queue(
            conn,
            "party-entity-links",
            output_dir=tmp_path,
        )
        queue_summary = json.loads(queue_path.read_text(encoding="utf-8"))
        queue_jsonl_path = Path(queue_summary["jsonl_path"])
        records = [
            json.loads(line)
            for line in queue_jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_name = {record["entity_name"]: record for record in records}
        assert "Example Party Federal Campaign" in by_name
        assert "Example Party Rejected Campaign" in by_name

        bad_accept_path = tmp_path / "party_entity_bad_accept.jsonl"
        bad_accept_record = {
            **by_name["Example Party Federal Campaign"],
            "decision": "accept",
            "reviewer": "m.zyphur@uq.edu.au",
            "evidence_note": "Generated context alone must not satisfy the review gate.",
            "proposed_changes": by_name["Example Party Federal Campaign"][
                "draft_proposed_changes"
            ],
            "supporting_sources": by_name["Example Party Federal Campaign"][
                "draft_supporting_sources"
            ],
        }
        bad_accept_path.write_text(json.dumps(bad_accept_record) + "\n", encoding="utf-8")
        with pytest.raises(ReviewImportError, match="party_entity_relationship"):
            import_review_decisions(conn, bad_accept_path, apply=False, output_dir=tmp_path)

        decisions_path = tmp_path / "party_entity_decisions.jsonl"
        decisions = []
        for entity_name, decision in (
            ("Example Party Federal Campaign", "accept"),
            ("Example Party Rejected Campaign", "reject"),
        ):
            record = by_name[entity_name]
            decisions.append(
                {
                    **record,
                    "decision": decision,
                    "reviewer": "m.zyphur@uq.edu.au",
                    "evidence_note": (
                        "Accepted source-backed party/entity relationship."
                        if decision == "accept"
                        else "Rejected because the fixture source does not support this link."
                    ),
                    "proposed_changes": record["draft_proposed_changes"],
                    "supporting_sources": (
                        [
                            {
                                "evidence_role": "party_entity_relationship",
                                "source_document_id": source_document_id,
                                "note": "Fixture source supports the accepted test link.",
                            }
                        ]
                        if decision == "accept"
                        else []
                    ),
                }
            )
        decisions_path.write_text(
            "".join(json.dumps(decision, sort_keys=True) + "\n" for decision in decisions),
            encoding="utf-8",
        )

        dry_run = import_review_decisions(conn, decisions_path, apply=False, output_dir=tmp_path)
        assert dry_run["records_seen"] == 2
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM party_entity_link WHERE review_status = 'needs_review'"
            )
            assert cur.fetchone()[0] >= 2

        applied = import_review_decisions(conn, decisions_path, apply=True, output_dir=tmp_path)
        assert applied["decisions_inserted"] == 2
        assert applied["applied_updates"]["party_entity_links_reviewed"] == 1
        assert applied["applied_updates"]["party_entity_links_rejected"] == 1

        duplicate = import_review_decisions(conn, decisions_path, apply=True, output_dir=tmp_path)
        assert duplicate["duplicate_decisions"] == 2
        assert duplicate["applied_updates"]["party_entity_links_already_applied"] == 2

        replayed = reapply_review_decisions(
            conn,
            apply=True,
            subject_type="party_entity_link",
            output_dir=tmp_path,
        )
        assert replayed["records_reapplied"] == 2
        assert replayed["applied_updates"]["party_entity_links_already_applied"] == 2

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT entity.canonical_name, link.review_status, link.confidence,
                       link.evidence_note, link.metadata->>'review_evidence_note'
                FROM party_entity_link link
                JOIN entity ON entity.id = link.entity_id
                WHERE link.party_id = %s
                ORDER BY entity.canonical_name
                """,
                (party_id,),
            )
            link_rows = cur.fetchall()
        assert ("Example Party Federal Campaign", "reviewed") in {
            (row[0], row[1]) for row in link_rows
        }
        assert ("Example Party Rejected Campaign", "rejected") in {
            (row[0], row[1]) for row in link_rows
        }
        accepted_row = next(row for row in link_rows if row[0] == "Example Party Federal Campaign")
        assert accepted_row[2] == "manual_reviewed"
        assert "Candidate generated" in accepted_row[3]
        assert accepted_row[4] == "Accepted source-backed party/entity relationship."

    client = TestClient(app)
    response = client.get(f"/api/parties/{party_id}")
    assert response.status_code == 200
    payload = response.json()
    linked_names = {entity["canonical_name"] for entity in payload["linked_entities"]}
    assert "Example Party Federal Campaign" in linked_names
    assert "Example Party Rejected Campaign" not in linked_names
    candidate_names = {entity["canonical_name"] for entity in payload["candidate_entities"]}
    assert "Example Party Rejected Campaign" not in candidate_names
    assert payload["money_summary"][0]["reported_amount_total"] == 3000.0

    graph_response = client.get(
        "/api/graph/influence",
        params={"party_id": party_id, "include_candidates": "true", "limit": "20"},
    )
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    edge_types = {edge["type"] for edge in graph_payload["edges"]}
    assert "reviewed_party_entity_link" in edge_types
    assert "money_to_reviewed_party_entities" in edge_types
    graph_labels = {node["label"] for node in graph_payload["nodes"]}
    assert "Example Party Federal Campaign" in graph_labels
    assert "Example Party Rejected Campaign" not in graph_labels
    assert len({edge["id"] for edge in graph_payload["edges"]}) == len(graph_payload["edges"])
    party_entity_node_id = next(
        node["id"]
        for node in graph_payload["nodes"]
        if node["label"] == "Example Party Federal Campaign"
    )
    money_edges = [
        edge for edge in graph_payload["edges"] if edge["type"] == "money_to_reviewed_party_entities"
    ]
    assert money_edges
    assert all(edge["target"] == party_entity_node_id for edge in money_edges)
    assert all(edge["target"] != graph_payload["root_id"] for edge in money_edges)
    assert any(
        edge["type"] == "reviewed_party_entity_link"
        and edge["source"] == party_entity_node_id
        and edge["target"] == graph_payload["root_id"]
        for edge in graph_payload["edges"]
    )
