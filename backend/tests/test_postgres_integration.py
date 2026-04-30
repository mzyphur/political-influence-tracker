from __future__ import annotations

import hashlib
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
    link_aec_candidate_campaign_money_flows,
    link_aec_direct_representative_money_flows,
    _load_aec_money_flow_jsonl,
    load_aec_candidate_contests,
    load_display_land_mask,
    load_influence_events,
    load_postcode_electorate_crosswalk,
    load_qld_council_boundaries,
    load_qld_current_members,
    load_qld_ecq_eds_contexts,
    load_qld_ecq_eds_participants,
)
from au_politics_money.ingest.land_mask import (
    AIMS_COASTLINE_PARSER_NAME,
    AIMS_COASTLINE_PARSER_VERSION,
    AIMS_COASTLINE_SOURCE_ID,
)
from au_politics_money.db.party_entity_suggestions import (
    materialize_party_entity_link_candidates,
)
from au_politics_money.db.quality import (
    ServingDatabaseQualityConfig,
    run_serving_database_quality_checks,
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
            "postcode_electorate_crosswalk_postcode_idx",
            "postcode_electorate_crosswalk_electorate_idx",
            "postcode_electorate_crosswalk_source_document_idx",
            "postcode_electorate_crosswalk_unresolved_postcode_idx",
            "postcode_electorate_crosswalk_unresolved_source_document_idx",
            "money_flow_current_source_dataset_idx",
            "gift_interest_current_chamber_idx",
            "official_decision_record_current_source_idx",
            "official_decision_record_document_current_record_idx",
            "vote_division_current_chamber_idx",
            "person_vote_current_division_idx",
            "influence_event_person_direct_feed_idx",
            "influence_event_person_campaign_feed_idx",
            "money_flow_qld_ecq_current_record_feed_idx",
            "money_flow_qld_ecq_current_kind_record_feed_idx",
            "candidate_contest_name_electorate_idx",
            "candidate_contest_person_idx",
            "candidate_contest_office_term_idx",
            "candidate_contest_source_document_idx",
            "money_flow_candidate_contest_idx",
            "money_flow_office_term_idx",
            "influence_event_candidate_contest_idx",
            "influence_event_office_term_idx",
            "person_vote_office_term_idx",
            "aggregate_context_observation_source_dataset_idx",
            "aggregate_context_observation_jurisdiction_idx",
            "aggregate_context_observation_context_type_idx",
            "aggregate_context_observation_geography_name_trgm_idx",
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
            INSERT INTO display_land_mask (
                source_key, country_name, geometry_role, geom, source_document_id, metadata
            )
            VALUES (
                'pytest_land_mask:australia', 'Australia',
                'country_high_resolution_land_display_mask',
                ST_Multi(ST_GeomFromText(
                    'POLYGON((144.0 -38.0,146.0 -38.0,146.0 -34.0,144.0 -34.0,144.0 -38.0))',
                    4326
                )),
                %s,
                %s
            )
            """,
            (
                source_document_id,
                Jsonb(
                    {
                        "mask_method": "pytest_fixture_land_mask",
                        "licence_status": "test_fixture",
                    }
                ),
            ),
        )

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
            INSERT INTO jurisdiction (name, level, code)
            VALUES ('Queensland', 'state', 'QLD')
            RETURNING id
            """
        )
        qld_jurisdiction_id = cur.fetchone()[0]

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
            INSERT INTO electorate (
                name, jurisdiction_id, chamber, state_or_territory, source_document_id
            )
            VALUES ('McDowall', %s, 'state', 'QLD', %s)
            RETURNING id
            """,
            (qld_jurisdiction_id, source_document_id),
        )
        qld_state_electorate_id = cur.fetchone()[0]

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
            INSERT INTO electorate_boundary (
                electorate_id, boundary_set, valid_from, geom, source_document_id, metadata
            )
            VALUES (
                %s, 'qld_state_pytest_boundary_set', '2017-10-29',
                ST_Multi(ST_GeomFromText(
                    'POLYGON((152.90 -27.45,153.00 -27.45,153.00 -27.35,152.90 -27.35,152.90 -27.45))',
                    4326
                )),
                %s, %s
            )
            """,
            (qld_state_electorate_id, source_document_id, Jsonb({"fixture": True})),
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

    qld_state_map_response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "state",
            "state": "QLD",
            "boundary_set": "qld_state_pytest_boundary_set",
        },
    )
    assert qld_state_map_response.status_code == 200
    qld_state_payload = qld_state_map_response.json()
    assert qld_state_payload["feature_count"] == 1
    assert qld_state_payload["features"][0]["properties"]["electorate_name"] == "McDowall"
    assert qld_state_payload["features"][0]["properties"]["state_or_territory"] == "QLD"
    assert qld_state_payload["features"][0]["properties"]["current_representative_count"] == 0
    assert "not yet attributed to current state MPs" in qld_state_payload["caveat"]

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
    assert coverage_payload["display_land_masks"][0]["source_key"] == "pytest_land_mask:australia"
    assert coverage_payload["display_land_masks"][0]["licence_status"] == "test_fixture"
    assert {
        layer["id"]: layer["status"] for layer in coverage_payload["coverage_layers"]
    }["federal_display_land_mask"] == "active"

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

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO electorate (
                    name, jurisdiction_id, chamber, state_or_territory, source_document_id
                )
                VALUES ('Canberra', %s, 'house', 'ACT', %s), ('Bean', %s, 'house', 'ACT', %s)
                ON CONFLICT (name, jurisdiction_id, chamber) DO UPDATE SET
                    state_or_territory = EXCLUDED.state_or_territory
                """,
                (jurisdiction_id, source_document_id, jurisdiction_id, source_document_id),
            )
            cur.execute(
                """
                INSERT INTO postcode_electorate_crosswalk (
                    postcode, electorate_id, state_or_territory, match_method,
                    confidence, locality_count, localities, source_document_id,
                    source_updated_text, metadata
                )
                SELECT '2600', electorate.id, 'ACT', 'aec_postcode_locality_search',
                       0.5000, 3, %s, %s, '11 September 2025',
                       %s
                FROM electorate
                WHERE electorate.name = 'Canberra'
                  AND electorate.jurisdiction_id = %s
                  AND electorate.chamber = 'house'
                UNION ALL
                SELECT '2600', electorate.id, 'ACT', 'aec_postcode_locality_search',
                       0.5000, 1, %s, %s, '11 September 2025',
                       %s
                FROM electorate
                WHERE electorate.name = 'Bean'
                  AND electorate.jurisdiction_id = %s
                  AND electorate.chamber = 'house'
                """,
                (
                    Jsonb(["BARTON", "DEAKIN", "PARKES"]),
                    source_document_id,
                    Jsonb({"ambiguity": "ambiguous_postcode", "fixture": True}),
                    jurisdiction_id,
                    Jsonb(["HMAS HARMAN"]),
                    source_document_id,
                    Jsonb({"ambiguity": "ambiguous_postcode", "fixture": True}),
                    jurisdiction_id,
                ),
            )
        conn.commit()

    postcode_search_response = client.get(
        "/api/search",
        params=[("q", "2600"), ("types", "postcode"), ("limit", "5")],
    )
    assert postcode_search_response.status_code == 200
    postcode_payload = postcode_search_response.json()
    assert postcode_payload["result_count"] == 2
    assert [result["label"] for result in postcode_payload["results"]] == [
        "2600 -> Canberra",
        "2600 -> Bean",
    ]
    assert all(
        result["metadata"]["match_method"] == "aec_postcode_locality_search"
        for result in postcode_payload["results"]
    )
    assert {
        result["metadata"]["electorate_name"]: result["metadata"]["locality_count"]
        for result in postcode_payload["results"]
    } == {"Canberra": 3, "Bean": 1}
    assert {
        result["metadata"]["electorate_name"]: result["metadata"]["chamber"]
        for result in postcode_payload["results"]
    } == {"Canberra": "house", "Bean": "house"}

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
    edge_by_type = {edge["type"]: edge for edge in graph_payload["edges"]}
    assert graph_payload["edge_count"] == 2
    assert edge_by_type["disclosed_to_representative"]["reported_amount_total"] == 1250.0
    assert edge_by_type["disclosed_to_representative"]["source_urls"] == [
        "https://example.test/source"
    ]
    assert edge_by_type["disclosed_to_representative"]["needs_review_event_count"] == 0
    assert edge_by_type["disclosed_to_representative"]["missing_data_event_count"] == 0
    assert edge_by_type["current_party_representation_context"][
        "allocation_method"
    ] == "no_allocation"
    assert edge_by_type["current_party_representation_context"][
        "evidence_tier"
    ] == "party_membership_context"
    assert len({edge["id"] for edge in graph_payload["edges"]}) == len(graph_payload["edges"])
    assert {node["label"] for node in graph_payload["nodes"]} >= {
        "Jane Citizen",
        "Clean Energy Pty Ltd",
        "Example Party",
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


def test_qld_current_member_loader_joins_state_map_representatives(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
) -> None:
    source_body = tmp_path / "qld-members.xlsx"
    source_body.write_bytes(b"fixture")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body),
                "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "fetched_at": "20260429T000000Z",
                "final_url": (
                    "https://documents.parliament.qld.gov.au/Members/mailingLists/"
                    "MEMMERGEEXCEL.xlsx"
                ),
                "http_status": 200,
                "sha256": "pytest-qld-members-sha",
                "source": {
                    "source_id": "qld_parliament_members_mail_merge_xlsx",
                    "name": "Queensland Parliament Members Mail Merge List Excel",
                    "source_type": "state_current_member_contact_xlsx",
                    "jurisdiction": "Queensland",
                    "url": (
                        "https://documents.parliament.qld.gov.au/Members/mailingLists/"
                        "MEMMERGEEXCEL.xlsx"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    records = []
    for index in range(93):
        electorate = "McDowall" if index == 0 else f"Roster Test {index}"
        is_vacant = index == 92
        email = f"{electorate.lower().replace(' ', '.')}@parliament.qld.gov.au"
        records.append(
            {
                "chamber": "state_lower",
                "display_name": "" if is_vacant else f"Ms Example Member {index}",
                "electorate": electorate,
                "electorate_offices": [
                    {
                        "address_lines": ["1 Test Street", "BRISBANE QLD 4000"],
                        "email": email,
                        "source_row_number": index + 2,
                    }
                ],
                "email": email,
                "first_name": "" if is_vacant else "Example",
                "is_vacant": is_vacant,
                "last_name": "" if is_vacant else f"Member {index}",
                "parser_name": "qld_parliament_current_members_mail_merge_xlsx_v1",
                "parser_version": "1",
                "party_short_name": "-" if is_vacant else "LNP",
                "portfolio": "" if is_vacant else "Fixture portfolio",
                "salutation": "Sir/Madam" if is_vacant else "Ms Member",
                "source_dataset": "qld_parliament_current_members",
                "source_metadata_path": str(metadata_path),
                "source_rows": [],
                "state_or_territory": "QLD",
                "title": "" if is_vacant else "Ms",
            }
        )
    jsonl_path = tmp_path / "qld-members.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    with connect(integration_db.url) as conn:
        summary = load_qld_current_members(conn, jsonl_path)

    assert summary["electorate_count"] == 93
    assert summary["people_upserted"] == 92
    assert summary["office_terms_upserted"] == 92
    assert summary["vacant_electorates"] == 1

    client = TestClient(app)
    response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "state",
            "state": "QLD",
            "boundary_set": "qld_state_pytest_boundary_set",
        },
    )
    assert response.status_code == 200
    properties = response.json()["features"][0]["properties"]
    assert properties["electorate_name"] == "McDowall"
    assert properties["current_representative_count"] == 1
    representative = properties["current_representatives"][0]
    assert representative["display_name"] == "Ms Example Member 0"
    assert representative["party_short_name"] == "LNP"
    assert representative["public_email"] == "mcdowall@parliament.qld.gov.au"
    assert representative["electorate_offices"][0]["address_lines"] == [
        "1 Test Street",
        "BRISBANE QLD 4000",
    ]


def test_qld_council_boundary_loader_exposes_council_map(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_body = tmp_path / "qld-council-boundaries.json"
    source_body.write_text('{"fixture": true}\n', encoding="utf-8")
    metadata_path = tmp_path / "qld-council-metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body),
                "content_type": "application/geo+json",
                "fetched_at": "20260429T000000Z",
                "final_url": (
                    "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                    "Boundaries/AdministrativeBoundaries/MapServer/1/query"
                ),
                "http_status": 200,
                "sha256": hashlib.sha256(source_body.read_bytes()).hexdigest(),
                "source": {
                    "source_id": "qld_local_government_boundaries_arcgis",
                    "name": "Queensland current local government boundaries ArcGIS GeoJSON",
                    "source_type": "local_government_boundary_geojson",
                    "jurisdiction": "Queensland",
                    "url": (
                        "https://spatial-gis.information.qld.gov.au/arcgis/rest/services/"
                        "Boundaries/AdministrativeBoundaries/MapServer/1/query"
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    features = []
    for index in range(78):
        if index == 0:
            name = "Brisbane City"
        elif index == 1:
            name = "Moreton Bay City"
        elif index == 2:
            name = "Weipa Town"
        else:
            name = f"Fixture Council {index}"
        x = 152.0 + (index % 10) * 0.02
        y = -27.0 - (index // 10) * 0.02
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "boundary_set": "qld_council_pytest_boundary_set",
                    "chamber": "council",
                    "division_name": name,
                    "official_name": name,
                    "state_or_territory": "QLD",
                    "lga_code": str(100 + index),
                    "source_metadata_path": str(metadata_path),
                    "parser_name": "qld_local_government_boundaries_arcgis_geojson_v1",
                    "parser_version": "1",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [x, y],
                            [x + 0.01, y],
                            [x + 0.01, y - 0.01],
                            [x, y - 0.01],
                            [x, y],
                        ]
                    ],
                },
            }
        )
    geojson_path = tmp_path / "qld-council-boundaries.geojson"
    geojson_path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )

    def fake_display_geometries(conn, *, boundary_set: str, **kwargs):
        return {
            "boundary_set": boundary_set,
            "source_boundary_count": 78,
            "display_geometries_upserted": 0,
            "stale_display_geometries_deleted": 0,
            "land_mask": {"source_key": "pytest"},
        }

    monkeypatch.setattr(
        "au_politics_money.db.load.load_electorate_boundary_display_geometries",
        fake_display_geometries,
    )

    with connect(integration_db.url) as conn:
        summary = load_qld_council_boundaries(conn, geojson_path)
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'QLD-LOCAL'")
            qld_local_jurisdiction_id = cur.fetchone()[0]
            cur.execute("SELECT min(id) FROM source_document")
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                SELECT electorate.id
                FROM electorate
                WHERE electorate.name = 'Brisbane City'
                  AND electorate.chamber = 'council'
                """
            )
            brisbane_electorate_id = cur.fetchone()[0]
            cur.execute(
                """
                SELECT electorate.id
                FROM electorate
                WHERE electorate.name = 'Moreton Bay City'
                  AND electorate.chamber = 'council'
                """
            )
            moreton_bay_electorate_id = cur.fetchone()[0]
            cur.execute(
                """
                SELECT electorate.id
                FROM electorate
                WHERE electorate.name = 'Weipa Town'
                  AND electorate.chamber = 'council'
                """
            )
            weipa_electorate_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO electorate (
                    name, jurisdiction_id, chamber, state_or_territory, source_document_id
                )
                VALUES ('Stale Council Without Boundary', %s, 'council', 'QLD', %s)
                """,
                (qld_local_jurisdiction_id, source_document_id),
            )
            qld_context_rows = (
                (
                    "pytest-qld-council-brisbane-division-spend",
                    "Campaign Supplier",
                    "Local Candidate",
                    250,
                    "qld_electoral_expenditure",
                    "2026-01-03",
                    True,
                    "Brisbane City Division 7",
                    "lga-brisbane-division-7",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-brisbane-area-gift",
                    "Local Donor",
                    "Local Recipient",
                    50,
                    "qld_gift",
                    "2026-01-02",
                    True,
                    "Brisbane City",
                    "lga-brisbane-city",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-brisbane-named-ward-spend",
                    "Ward Campaign Supplier",
                    "Local Candidate",
                    125,
                    "qld_electoral_expenditure",
                    "2026-01-03",
                    True,
                    "Brisbane City Tennyson",
                    "lga-brisbane-tennyson",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-division-nonnumeric",
                    "Office Supplier",
                    "Local Candidate",
                    500,
                    "qld_electoral_expenditure",
                    "2026-01-04",
                    True,
                    "Brisbane City Division Office",
                    "lga-brisbane-division-office",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-inactive-spend",
                    "Inactive Supplier",
                    "Local Recipient",
                    9900,
                    "qld_electoral_expenditure",
                    "2026-01-05",
                    False,
                    "Brisbane City Division 7",
                    "lga-brisbane-division-7",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-other-area",
                    "Other Donor",
                    "Other Recipient",
                    77,
                    "qld_electoral_expenditure",
                    "2026-01-05",
                    True,
                    "Whitsunday Regional",
                    "lga-whitsunday",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-moreton-bay-legacy-division-spend",
                    "Moreton Campaign Supplier",
                    "Moreton Local Candidate",
                    300,
                    "qld_electoral_expenditure",
                    "2026-01-06",
                    True,
                    "Moreton Bay Regional Division 7",
                    "lga-moreton-bay-regional-division-7",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
                (
                    "pytest-qld-council-weipa-prefix-alias-gift",
                    "Weipa Donor",
                    "Weipa Recipient",
                    42,
                    "qld_gift",
                    "2026-01-07",
                    True,
                    "Town of Weipa",
                    "lga-town-of-weipa",
                    "2028 Local Government Elections",
                    "event-local-2028",
                ),
            )
            for (
                external_key,
                source_name,
                recipient_name,
                amount,
                flow_kind,
                date_received,
                is_current,
                local_electorate_name,
                local_electorate_id,
                event_name,
                event_id,
            ) in qld_context_rows:
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_raw_name, recipient_raw_name, amount,
                        receipt_type, disclosure_category, jurisdiction_id,
                        source_document_id, source_row_ref, original_text,
                        date_received, confidence, is_current, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, '{}',
                        %s, 'resolved', %s, %s
                    )
                    """,
                    (
                        external_key,
                        source_name,
                        recipient_name,
                        amount,
                        "Gift" if flow_kind == "qld_gift" else "Electoral Expenditure",
                        flow_kind,
                        qld_local_jurisdiction_id,
                        source_document_id,
                        external_key,
                        date_received,
                        is_current,
                        Jsonb(
                            {
                                "flow_kind": flow_kind,
                                "source_dataset": "qld_ecq_eds",
                                "event_name": event_name,
                                "local_electorate": local_electorate_name,
                            }
                        ),
                    ),
                )
            qld_contexts_path = tmp_path / "qld-council-contexts.jsonl"
            qld_context_records = [
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_political_events",
                    "source_record_type": "qld_ecq_political_event",
                    "context_type": "political_event",
                    "external_id": "event-local-2028",
                    "identifier": {
                        "identifier_type": "qld_ecq_event_id",
                        "identifier_value": "event-local-2028",
                    },
                    "display_name": "2028 Local Government Elections",
                    "normalized_name": "2028 local government elections",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_political_event:event-local-2028",
                    "metadata": {"event_type": "Local Government Election"},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-brisbane-city",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-brisbane-city",
                    },
                    "display_name": "Brisbane City",
                    "normalized_name": "brisbane city",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_local_electorate:lga-brisbane-city",
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-brisbane-division-7",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-brisbane-division-7",
                    },
                    "display_name": "Brisbane City Division 7",
                    "normalized_name": "brisbane city division 7",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_local_electorate:lga-brisbane-division-7",
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-brisbane-tennyson",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-brisbane-tennyson",
                    },
                    "display_name": "Brisbane City Tennyson",
                    "normalized_name": "brisbane city tennyson",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_local_electorate:lga-brisbane-tennyson",
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-brisbane-division-office",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-brisbane-division-office",
                    },
                    "display_name": "Brisbane City Division Office",
                    "normalized_name": "brisbane city division office",
                    "level": "council",
                    "stable_key": (
                        "pytest:qld_ecq_local_electorate:lga-brisbane-division-office"
                    ),
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-whitsunday",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-whitsunday",
                    },
                    "display_name": "Whitsunday Regional",
                    "normalized_name": "whitsunday regional",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_local_electorate:lga-whitsunday",
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-moreton-bay-regional-division-7",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-moreton-bay-regional-division-7",
                    },
                    "display_name": "Moreton Bay Regional Division 7",
                    "normalized_name": "moreton bay regional division 7",
                    "level": "council",
                    "stable_key": (
                        "pytest:qld_ecq_local_electorate:"
                        "lga-moreton-bay-regional-division-7"
                    ),
                    "metadata": {},
                },
                {
                    "schema_version": "qld_ecq_eds_context_v1",
                    "parser_name": "qld_ecq_eds_context_normalizer",
                    "parser_version": "1",
                    "source_id": "qld_ecq_eds_api_local_electorates",
                    "source_record_type": "qld_ecq_local_electorate",
                    "context_type": "local_electorate",
                    "external_id": "lga-town-of-weipa",
                    "identifier": {
                        "identifier_type": "qld_ecq_local_electorate_id",
                        "identifier_value": "lga-town-of-weipa",
                    },
                    "display_name": "Town of Weipa",
                    "normalized_name": "town of weipa",
                    "level": "council",
                    "stable_key": "pytest:qld_ecq_local_electorate:lga-town-of-weipa",
                    "metadata": {},
                },
            ]
            qld_contexts_path.write_text(
                "\n".join(json.dumps(record) for record in qld_context_records) + "\n",
                encoding="utf-8",
            )
            context_summary = load_qld_ecq_eds_contexts(conn, jsonl_path=qld_contexts_path)
            assert context_summary["local_electorate_context_matched_money_flows"] == 7
            cur.execute(
                """
                SELECT jurisdiction.level, jurisdiction.code, count(electorate_boundary.id)
                FROM electorate
                JOIN jurisdiction ON jurisdiction.id = electorate.jurisdiction_id
                LEFT JOIN electorate_boundary
                  ON electorate_boundary.electorate_id = electorate.id
                WHERE electorate.chamber = 'council'
                GROUP BY jurisdiction.level, jurisdiction.code
                """
            )
            jurisdiction_row = cur.fetchone()

    assert summary["division_count"] == 78
    assert summary["boundaries_inserted"] == 78
    assert jurisdiction_row == ("local", "QLD-LOCAL", 78)

    client = TestClient(app)
    response = client.get(
        "/api/map/electorates",
        params={
            "chamber": "council",
            "state": "QLD",
            "boundary_set": "qld_council_pytest_boundary_set",
            "geometry_role": "source",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["feature_count"] == 78
    first = payload["features"][0]["properties"]
    assert first["chamber"] == "council"
    assert first["electorate_name"] == "Brisbane City"
    assert first["current_representative_count"] == 0
    assert "not attributed to councillors" in payload["caveat"]

    profile_response = client.get(f"/api/electorates/{brisbane_electorate_id}")
    assert profile_response.status_code == 200
    profile_payload = profile_response.json()
    context = profile_payload["qld_ecq_local_disclosure_context"]
    assert context["available"] is True
    assert context["not_council_or_councillor_receipt"] is True
    assert context["money_flow_count"] == 3
    assert context["gift_or_donation_count"] == 1
    assert context["electoral_expenditure_count"] == 2
    assert context["exact_area_count"] == 1
    assert context["alias_area_count"] == 0
    assert context["child_area_count"] == 2
    assert context["matched_local_electorate_count"] == 3
    assert "reported_amount_total" not in context
    assert context["gift_or_donation_reported_amount_total"] == 50.0
    assert context["electoral_expenditure_reported_amount_total"] == 375.0
    assert {
        row["local_electorate_name"] for row in context["matched_local_electorates"]
    } == {"Brisbane City", "Brisbane City Division 7", "Brisbane City Tennyson"}
    assert {
        row["local_electorate_name"]: row["match_scope"]
        for row in context["matched_local_electorates"]
    } == {
        "Brisbane City": "exact_area",
        "Brisbane City Division 7": "child_area",
        "Brisbane City Tennyson": "child_area",
    }
    assert all("reported_amount_total" not in row for row in context["matched_local_electorates"])
    assert all("reported_amount_total" not in row for row in context["top_events"])
    assert context["top_events"][0]["event_name"] == "2028 Local Government Elections"
    assert context["top_gift_donors"][0]["source_name"] == "Local Donor"
    assert context["top_expenditure_actors"][0]["source_name"] in {
        "Campaign Supplier",
        "Ward Campaign Supplier",
    }
    assert "not claims" in context["caveat"]

    moreton_profile_response = client.get(f"/api/electorates/{moreton_bay_electorate_id}")
    assert moreton_profile_response.status_code == 200
    moreton_profile_payload = moreton_profile_response.json()
    moreton_context = moreton_profile_payload["qld_ecq_local_disclosure_context"]
    assert moreton_context["available"] is True
    assert moreton_context["money_flow_count"] == 1
    assert moreton_context["child_area_count"] == 1
    assert moreton_context["matched_local_electorates"][0]["local_electorate_name"] == (
        "Moreton Bay Regional Division 7"
    )
    assert moreton_context["matched_local_electorates"][0]["match_scope"] == (
        "alias_child_area"
    )

    weipa_profile_response = client.get(f"/api/electorates/{weipa_electorate_id}")
    assert weipa_profile_response.status_code == 200
    weipa_profile_payload = weipa_profile_response.json()
    weipa_context = weipa_profile_payload["qld_ecq_local_disclosure_context"]
    assert weipa_context["available"] is True
    assert weipa_context["money_flow_count"] == 1
    assert weipa_context["alias_area_count"] == 1
    assert weipa_context["gift_or_donation_reported_amount_total"] == 42.0
    assert weipa_context["matched_local_electorates"][0]["local_electorate_name"] == (
        "Town of Weipa"
    )
    assert weipa_context["matched_local_electorates"][0]["match_scope"] == "alias_area"

    default_response = client.get(
        "/api/map/electorates",
        params={"chamber": "council", "state": "QLD", "geometry_role": "source"},
    )
    assert default_response.status_code == 200
    default_payload = default_response.json()
    assert default_payload["feature_count"] == 78
    assert all(
        feature["properties"]["electorate_name"] != "Stale Council Without Boundary"
        for feature in default_payload["features"]
    )


def test_qld_council_disclosure_context_alias_regex_matrix(
    integration_db: IntegrationDatabase,
) -> None:
    """Adversarial alias-regex matrix.

    The QLD council disclosure context matcher distinguishes between council names
    that share a common base (`Town of Weipa` vs `Townsville City`), so the regex
    branches in `_qld_council_disclosure_context` must not produce false positives
    across them. This test seeds a focused matrix of council electorates and ECQ
    rows that cross several adversarial edges and asserts the resulting
    `match_scope` enum per electorate via `/api/electorates/{id}`.
    """
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Queensland Local Government (alias matrix)', 'local', 'QLD-LOCAL')
                ON CONFLICT (name) DO UPDATE SET level = EXCLUDED.level, code = EXCLUDED.code
                RETURNING id
                """
            )
            qld_local_jurisdiction_id = cur.fetchone()[0]

            council_names = [
                "Townsville City",
                "Weipa Town",
                "Sunshine Coast Regional",
                "Sunshine Coast Hinterland Regional",
                "Mareeba Shire",
                "Cairns Regional",
            ]
            council_ids: dict[str, int] = {}
            for name in council_names:
                cur.execute(
                    """
                    INSERT INTO electorate (
                        name, jurisdiction_id, chamber, state_or_territory, source_document_id
                    )
                    VALUES (%s, %s, 'council', 'QLD', %s)
                    RETURNING id
                    """,
                    (name, qld_local_jurisdiction_id, source_document_id),
                )
                council_ids[name] = cur.fetchone()[0]

            # ECQ rows. Each row pretends to be from a real ECQ local_electorate. The
            # matcher must associate each row only with the electorate whose name
            # actually matches it under the alias rules; cross-prefix and
            # similar-base names must NOT cross-match.
            ecq_rows = [
                ("matrix-townsville-exact", "Townsville City"),
                ("matrix-townsville-child", "Townsville City Division 4"),
                ("matrix-weipa-alias", "Town of Weipa"),
                ("matrix-weipa-exact", "Weipa Town"),
                ("matrix-sunshine-base", "Sunshine Coast Regional"),
                ("matrix-sunshine-child", "Sunshine Coast Regional Division 2"),
                ("matrix-sunshine-hinterland", "Sunshine Coast Hinterland Regional"),
                ("matrix-mareeba-alias", "Shire of Mareeba"),
                ("matrix-mareeba-exact", "Mareeba Shire"),
                ("matrix-cairns-base", "Cairns Regional"),
                ("matrix-cairns-child", "Cairns Regional Division 1"),
            ]
            for index, (external_key, local_electorate_name) in enumerate(ecq_rows):
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_raw_name, recipient_raw_name, amount,
                        receipt_type, disclosure_category, jurisdiction_id,
                        source_document_id, source_row_ref, original_text,
                        date_received, confidence, is_current, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        'Gift', 'qld_gift', %s,
                        %s, %s, '{}',
                        '2026-01-02', 'resolved', TRUE, %s
                    )
                    """,
                    (
                        external_key,
                        f"Alias matrix donor {index}",
                        f"Alias matrix recipient {index}",
                        100 + index,
                        qld_local_jurisdiction_id,
                        source_document_id,
                        external_key,
                        Jsonb(
                            {
                                "flow_kind": "qld_gift",
                                "source_dataset": "qld_ecq_eds",
                                "event_name": "2028 Local Government Elections (matrix)",
                                "qld_ecq_context": {
                                    "event": {
                                        "external_id": "matrix-event-2028",
                                        "name": "2028 Local Government Elections (matrix)",
                                    },
                                    "local_electorate": {
                                        "external_id": (
                                            "matrix-"
                                            + local_electorate_name.lower().replace(" ", "-")
                                        ),
                                        "name": local_electorate_name,
                                        "status": "matched",
                                    },
                                },
                            }
                        ),
                    ),
                )
        conn.commit()

    client = TestClient(app)

    def _scopes_for(council_name: str) -> dict[str, str]:
        response = client.get(f"/api/electorates/{council_ids[council_name]}")
        assert response.status_code == 200, response.text
        payload = response.json()
        context = payload["qld_ecq_local_disclosure_context"]
        if not context.get("available"):
            return {}
        return {
            row["local_electorate_name"]: row["match_scope"]
            for row in context["matched_local_electorates"]
        }

    # Townsville City matches its own rows but NOT "Town of Weipa" (cross-prefix).
    townsville_scopes = _scopes_for("Townsville City")
    assert townsville_scopes == {
        "Townsville City": "exact_area",
        "Townsville City Division 4": "child_area",
    }, townsville_scopes
    assert "Town of Weipa" not in townsville_scopes
    assert "Weipa Town" not in townsville_scopes

    # Weipa Town matches "Town of Weipa" via alias_area + its own exact name; must
    # NOT pick up Townsville City rows even though "town" appears in both.
    weipa_scopes = _scopes_for("Weipa Town")
    assert weipa_scopes == {
        "Town of Weipa": "alias_area",
        "Weipa Town": "exact_area",
    }, weipa_scopes
    assert "Townsville City" not in weipa_scopes
    assert "Townsville City Division 4" not in weipa_scopes

    # Sunshine Coast Regional matches its own rows but must NOT swallow
    # "Sunshine Coast Hinterland Regional" (a distinct council that shares a prefix).
    sunshine_scopes = _scopes_for("Sunshine Coast Regional")
    assert sunshine_scopes == {
        "Sunshine Coast Regional": "exact_area",
        "Sunshine Coast Regional Division 2": "child_area",
    }, sunshine_scopes
    assert "Sunshine Coast Hinterland Regional" not in sunshine_scopes

    # Sunshine Coast Hinterland Regional must match its own row only.
    hinterland_scopes = _scopes_for("Sunshine Coast Hinterland Regional")
    assert hinterland_scopes == {
        "Sunshine Coast Hinterland Regional": "exact_area",
    }, hinterland_scopes
    assert "Sunshine Coast Regional" not in hinterland_scopes
    assert "Sunshine Coast Regional Division 2" not in hinterland_scopes

    # Mareeba Shire / Shire of Mareeba pair: alias forms with the trailing/leading
    # qualifier swapped. Both must resolve to the Mareeba Shire electorate.
    mareeba_scopes = _scopes_for("Mareeba Shire")
    assert mareeba_scopes == {
        "Mareeba Shire": "exact_area",
        "Shire of Mareeba": "alias_area",
    }, mareeba_scopes

    # Cairns Regional should match its own + child but NOT Mareeba (no shared base).
    cairns_scopes = _scopes_for("Cairns Regional")
    assert cairns_scopes == {
        "Cairns Regional": "exact_area",
        "Cairns Regional Division 1": "child_area",
    }, cairns_scopes
    assert "Mareeba Shire" not in cairns_scopes
    assert "Shire of Mareeba" not in cairns_scopes


def test_load_display_land_mask_reuses_only_valid_aims_cache(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact_path = tmp_path / "aims-mask.geojson"
    artifact_path.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")
    monkeypatch.setattr(
        "au_politics_money.db.load.latest_aims_australian_coastline_land_mask_geojson",
        lambda **kwargs: artifact_path,
    )
    source_key = f"{AIMS_COASTLINE_SOURCE_ID}:australia"
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, parser_name,
                    parser_version, metadata
                )
                VALUES (
                    %s, 'AIMS fixture', 'display_land_mask', 'Australia',
                    'https://example.test/aims', now(), 200, 'application/geo+json',
                    %s, %s, %s, %s, '{}'::jsonb
                )
                RETURNING id
                """,
                (
                    AIMS_COASTLINE_SOURCE_ID,
                    f"pytest-aims-{uuid.uuid4()}",
                    str(artifact_path),
                    AIMS_COASTLINE_PARSER_NAME,
                    AIMS_COASTLINE_PARSER_VERSION,
                ),
            )
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO display_land_mask (
                    source_key, country_name, geometry_role, geom, source_document_id, metadata
                )
                VALUES (
                    %s, 'Australia', 'country_high_resolution_land_display_mask',
                    ST_Multi(ST_GeomFromText(
                        'POLYGON((140 -40,155 -40,155 -10,140 -10,140 -40))',
                        4326
                    )),
                    %s,
                    %s
                )
                """,
                (
                    source_key,
                    source_document_id,
                    Jsonb(
                        {
                            "geojson_path": str(artifact_path),
                            "parser_name": AIMS_COASTLINE_PARSER_NAME,
                            "parser_version": AIMS_COASTLINE_PARSER_VERSION,
                        }
                    ),
                ),
            )
        conn.commit()

        cached = load_display_land_mask(conn)
        assert cached["cache_status"] == "existing_display_land_mask_reused"
        assert cached["source_document_id"] == source_document_id

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE display_land_mask
                SET metadata = metadata || %s
                WHERE source_key = %s
                """,
                (Jsonb({"parser_version": "stale"}), source_key),
            )
        conn.commit()

        monkeypatch.setattr(
            "au_politics_money.db.load.load_aims_display_land_mask",
            lambda conn, *, country_name, geojson_path=None: {
                "country_name": country_name,
                "source_key": source_key,
                "cache_status": "fallback_reloaded",
            },
        )

        reloaded = load_display_land_mask(conn)
        assert reloaded["cache_status"] == "fallback_reloaded"


def test_vote_summary_excludes_non_current_official_rows(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT min(id) FROM source_document")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT min(id) FROM party")
            party_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO vote_division (
                    external_id, chamber, division_date, division_number, title,
                    no_count, source_document_id, metadata, is_current, withdrawn_at
                )
                VALUES (
                    'division:withdrawn-climate-2', 'house', '2023-03-02', 2,
                    'Withdrawn Climate Division', 1, %s, %s, FALSE, now()
                )
                RETURNING id
                """,
                (
                    source_document_id,
                    Jsonb({"source": "aph_official_decision_record", "fixture": True}),
                ),
            )
            withdrawn_division_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO person_vote (
                    division_id, person_id, vote, party_id, source_document_id,
                    metadata, is_current, withdrawn_at
                )
                VALUES (%s, %s, 'no', %s, %s, %s, FALSE, now())
                """,
                (
                    withdrawn_division_id,
                    integration_db.person_id,
                    party_id,
                    source_document_id,
                    Jsonb({"source": "aph_official_decision_record", "fixture": True}),
                ),
            )
            cur.execute(
                """
                INSERT INTO division_topic (
                    division_id, topic_id, method, confidence, evidence_note
                )
                VALUES (
                    %s, %s, 'manual', 1.000,
                    'Fixture link for withdrawn official vote.'
                )
                """,
                (withdrawn_division_id, integration_db.topic_id),
            )
            cur.execute(
                """
                SELECT division_vote_count, aye_count, no_count
                FROM person_policy_vote_summary
                WHERE person_id = %s
                  AND topic_id = %s
                """,
                (integration_db.person_id, integration_db.topic_id),
            )
            row = cur.fetchone()
        conn.commit()

    assert row == (1, 1, 0)

    client = TestClient(app)
    coverage_response = client.get("/api/coverage")
    assert coverage_response.status_code == 200
    vote_counts = {
        item["chamber"]: item["division_count"]
        for item in coverage_response.json()["vote_divisions_by_chamber"]
    }
    assert vote_counts["house"] == 1


def test_postcode_loader_keeps_unresolved_aec_candidates_auditable(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "postcode.html"
    body_text = "<html><body>AEC postcode fixture</body></html>"
    body_path.write_text(body_text, encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": "aec_electorate_finder_postcode_9999",
                    "name": "AEC Electorate Finder postcode 9999",
                    "source_type": "postcode_locality_electorate_lookup",
                    "jurisdiction": "Commonwealth",
                    "url": (
                        "https://electorate.aec.gov.au/LocalitySearchResults.aspx"
                        "?filter=9999&filterby=Postcode"
                    ),
                },
                "fetched_at": "20260429T000000Z",
                "final_url": (
                    "https://electorate.aec.gov.au/LocalitySearchResults.aspx"
                    "?filter=9999&filterby=Postcode"
                ),
                "http_status": 200,
                "content_type": "text/html",
                "sha256": hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
                "body_path": str(body_path),
            }
        ),
        encoding="utf-8",
    )
    jsonl_path = tmp_path / "postcode_crosswalk.jsonl"
    record = {
        "postcode": "9999",
        "electorate_name": "Future Seat",
        "state_or_territory": "NSW",
        "match_method": "aec_postcode_locality_search",
        "confidence": "1.0",
        "locality_count": 1,
        "localities": ["FUTURE TOWN"],
        "redistributed_electorates": [],
        "other_localities": [],
        "aec_division_ids": [999],
        "page_updated_text": "29 April 2026",
        "source_boundary_context": "next_federal_election_electorates",
        "current_member_context": "previous_election_or_subsequent_by_election_member",
        "source_dataset": "aec_electorate_finder_postcode",
        "normalizer_name": "aec_electorate_finder_postcode_normalizer",
        "normalizer_version": "1",
        "caveat": "fixture caveat",
        "ambiguity": "single_electorate",
        "source_metadata_path": str(metadata_path),
        "original_rows": [{"Locality/Suburb": "FUTURE TOWN"}],
    }
    jsonl_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with connect(integration_db.url) as conn:
        summary = load_postcode_electorate_crosswalk(conn, jsonl_path=jsonl_path)
        assert summary["postcode_electorate_crosswalk_rows"] == 0
        assert summary["skipped_missing_electorate"] == 1
        assert summary["unresolved_postcode_candidates"] == 1
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT postcode, electorate_name, aec_division_ids
                FROM postcode_electorate_crosswalk_unresolved
                WHERE postcode = '9999'
                """
            )
            unresolved = cur.fetchone()
        assert unresolved[0] == "9999"
        assert unresolved[1] == "Future Seat"
        assert unresolved[2] == [999]

    client = TestClient(app)
    response = client.get(
        "/api/search",
        params=[("q", "9999"), ("types", "postcode"), ("limit", "5")],
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result_count"] == 0
    statuses = {limitation["status"] for limitation in payload["limitations"]}
    assert "postcode_candidates_unresolved" in statuses
    assert "postcode_no_map_linked_results" in statuses
    assert "Future Seat" in " ".join(
        limitation["message"] for limitation in payload["limitations"]
    )


def test_coverage_reports_partial_qld_state_and_local_levels(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, metadata
                )
                VALUES (
                    'qld_ecq_eds_map_export_csv', 'ECQ EDS Gift Map CSV Export',
                    'state_local_financial_disclosure_export_csv', 'Queensland',
                    'https://disclosures.ecq.qld.gov.au/Map/ExportCsv', now(),
                    200, 'text/csv', 'pytest-qld-sha256', '/tmp/qld.csv', '{}'::jsonb
                )
                RETURNING id
                """
            )
            source_document_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Queensland', 'state', 'QLD')
                ON CONFLICT (name)
                DO UPDATE SET code = EXCLUDED.code
                RETURNING id
                """
            )
            qld_state_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Queensland local governments', 'local', 'QLD-LOCAL')
                RETURNING id
                """
            )
            qld_local_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO entity (canonical_name, normalized_name, entity_type)
                VALUES ('QLD Donor', 'qld donor', 'organisation')
                RETURNING id
                """
            )
            donor_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (canonical_name, normalized_name, entity_type)
                VALUES ('QLD Recipient', 'qld recipient', 'organisation')
                RETURNING id
                """
            )
            recipient_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity_identifier (
                    entity_id, identifier_type, identifier_value, source_document_id
                )
                VALUES
                    (%s, 'qld_ecq_elector_id', 'pytest-qld-donor', %s),
                    (%s, 'qld_ecq_political_party_id', 'pytest-qld-recipient', %s)
                """,
                (donor_id, source_document_id, recipient_id, source_document_id),
            )

            qld_rows = (
                (
                    "pytest-qld-state-gift",
                    "QLD Donor",
                    "QLD Recipient",
                    100,
                    "Gift",
                    "qld_gift",
                    qld_state_id,
                    True,
                    {
                        "event_name": "2026 Stafford State By-election",
                        "flow_kind": "qld_gift",
                        "source_dataset": "qld_ecq_eds",
                    },
                ),
                (
                    "pytest-qld-state-gift-withdrawn",
                    "QLD Donor",
                    "QLD Recipient",
                    9900,
                    "Gift",
                    "qld_gift",
                    qld_state_id,
                    False,
                    {
                        "event_name": "2026 Stafford State By-election",
                        "flow_kind": "qld_gift",
                        "source_dataset": "qld_ecq_eds",
                    },
                ),
                (
                    "pytest-qld-local-expenditure",
                    "QLD Donor",
                    "QLD Recipient",
                    200,
                    "Electoral Expenditure",
                    "qld_electoral_expenditure",
                    qld_local_id,
                    True,
                    {
                        "event_name": "2028 Local Government Elections",
                        "flow_kind": "qld_electoral_expenditure",
                        "local_electorate": "Whitsunday Regional",
                        "source_dataset": "qld_ecq_eds",
                    },
                ),
            )
            for row in qld_rows:
                (
                    external_key,
                    source_name,
                    recipient_name,
                    amount,
                    receipt_type,
                    flow_kind,
                    jurisdiction_id,
                    is_current,
                    metadata,
                ) = row
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_entity_id, source_raw_name,
                        recipient_entity_id, recipient_raw_name, amount,
                        receipt_type, disclosure_category, jurisdiction_id,
                        source_document_id, source_row_ref, original_text,
                        confidence, is_current, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'resolved', %s, %s
                    )
                    """,
                    (
                        external_key,
                        donor_id,
                        source_name,
                        recipient_id,
                        recipient_name,
                        amount,
                        receipt_type,
                        flow_kind,
                        jurisdiction_id,
                        source_document_id,
                        external_key,
                        "{}",
                        is_current,
                        Jsonb(metadata),
                    ),
                )
        conn.commit()
        qld_contexts_path = tmp_path / "qld_contexts.jsonl"
        qld_context_records = [
            {
                "schema_version": "qld_ecq_eds_context_v1",
                "parser_name": "qld_ecq_eds_context_normalizer",
                "parser_version": "1",
                "source_id": "qld_ecq_eds_api_political_events",
                "source_record_type": "qld_ecq_political_event",
                "context_type": "political_event",
                "external_id": "100",
                "identifier": {
                    "identifier_type": "qld_ecq_event_id",
                    "identifier_value": "100",
                },
                "display_name": "2026 Stafford State By-election",
                "normalized_name": "2026 stafford state by election",
                "level": "state",
                "stable_key": "qld_ecq_eds_api_political_events:qld_ecq_political_event:100",
                "metadata": {
                    "code": "STAFFORD2026",
                    "event_type": "State By-election",
                    "is_state": True,
                    "polling_date": "2026-04-18T00:00:00",
                },
            },
            {
                "schema_version": "qld_ecq_eds_context_v1",
                "parser_name": "qld_ecq_eds_context_normalizer",
                "parser_version": "1",
                "source_id": "qld_ecq_eds_api_political_events",
                "source_record_type": "qld_ecq_political_event",
                "context_type": "political_event",
                "external_id": "636",
                "identifier": {
                    "identifier_type": "qld_ecq_event_id",
                    "identifier_value": "636",
                },
                "display_name": "2028 Local Government Elections",
                "normalized_name": "2028 local government elections",
                "level": "council",
                "stable_key": "qld_ecq_eds_api_political_events:qld_ecq_political_event:636",
                "metadata": {
                    "code": "LGE2028",
                    "event_type": "Local Government Election",
                    "is_state": False,
                    "polling_date": "2028-03-25T00:00:00",
                },
            },
            {
                "schema_version": "qld_ecq_eds_context_v1",
                "parser_name": "qld_ecq_eds_context_normalizer",
                "parser_version": "1",
                "source_id": "qld_ecq_eds_api_local_electorates",
                "source_record_type": "qld_ecq_local_electorate",
                "context_type": "local_electorate",
                "external_id": "777",
                "identifier": {
                    "identifier_type": "qld_ecq_local_electorate_id",
                    "identifier_value": "777",
                },
                "display_name": "Whitsunday Regional",
                "normalized_name": "whitsunday regional",
                "level": "council",
                "stable_key": "qld_ecq_eds_api_local_electorates:qld_ecq_local_electorate:777",
                "metadata": {},
            },
        ]
        qld_contexts_path.write_text(
            "\n".join(json.dumps(record) for record in qld_context_records) + "\n",
            encoding="utf-8",
        )
        context_summary = load_qld_ecq_eds_contexts(conn, jsonl_path=qld_contexts_path)
        assert context_summary["event_context_matched_money_flows"] == 2
        assert context_summary["local_electorate_context_matched_money_flows"] == 1

    client = TestClient(app)
    response = client.get("/api/coverage")
    assert response.status_code == 200
    payload = response.json()

    assert payload["active_levels"] == ["federal"]
    assert payload["partial_levels"] == ["state", "council"]
    layers = {layer["id"]: layer for layer in payload["coverage_layers"]}
    assert layers["state_territory_disclosures"]["status"] == "partial"
    assert layers["state_territory_disclosures"]["jurisdiction"] == "QLD"
    assert layers["state_territory_disclosures"]["counts"]["money_flow_rows"] == 1
    assert layers["state_territory_disclosures"]["counts"]["gift_or_donation_rows"] == 1
    assert layers["local_council_disclosures"]["status"] == "partial"
    assert layers["local_council_disclosures"]["jurisdiction"] == "QLD-LOCAL"
    assert layers["local_council_disclosures"]["counts"]["money_flow_rows"] == 1
    assert layers["local_council_disclosures"]["counts"]["electoral_expenditure_rows"] == 1

    state_summary_response = client.get(
        "/api/state-local/summary",
        params={"level": "state", "limit": "3"},
    )
    assert state_summary_response.status_code == 200
    state_summary = state_summary_response.json()
    assert state_summary["source_document_count"] == 1
    assert state_summary["latest_source_fetched_at"] is not None
    assert state_summary["totals_by_level"][0]["money_flow_count"] == 1
    assert state_summary["totals_by_level"][0]["gift_or_donation_count"] == 1
    assert state_summary["totals_by_level"][0]["source_identifier_backed_count"] == 1
    assert state_summary["totals_by_level"][0]["recipient_identifier_backed_count"] == 1
    assert state_summary["top_gift_donors"][0]["name"] == "QLD Donor"
    assert state_summary["top_gift_donors"][0]["identifier_backed"] is True
    assert state_summary["totals_by_level"][0]["gift_or_donation_reported_amount_total"] == 100
    assert state_summary["top_gift_donors"][0]["reported_amount_total"] == 100
    assert state_summary["totals_by_level"][0]["electoral_expenditure_reported_amount_total"] == 0
    assert state_summary["totals_by_level"][0]["event_context_backed_count"] == 1
    assert state_summary["top_events"][0]["external_id"] == "100"
    assert state_summary["top_events"][0]["name"] == "2026 Stafford State By-election"
    assert state_summary["recent_records"][0]["flow_kind"] == "qld_gift"
    assert state_summary["recent_records"][0]["source_name"] == "QLD Donor"
    assert state_summary["recent_records"][0]["recipient_name"] == "QLD Recipient"
    assert state_summary["recent_records"][0]["source_identifier_backed"] is True
    assert state_summary["recent_records"][0]["event_name"] == "2026 Stafford State By-election"

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO aggregate_context_observation (
                    jurisdiction_id, source_document_id, source_dataset, source_id,
                    observation_key, context_family, context_type, geography_type,
                    geography_name, amount, amount_status, record_count,
                    reporting_period_start, reporting_period_end, evidence_status,
                    attribution_scope, caveat, metadata, is_current
                )
                VALUES (
                    %s, %s, 'nsw_electoral_disclosures',
                    'nsw_2023_state_election_donation_heatmap',
                    'pytest-nsw-heatmap:sydney', 'money_aggregate_context',
                    'pre_election_reportable_donation_donor_location',
                    'state_electoral_district_donor_location', 'Sydney', 1234.56,
                    'reported', 7, DATE '2022-10-01', DATE '2023-03-25',
                    'official_record_parsed',
                    'aggregate_context_not_recipient_attribution',
                    'Aggregate context fixture; not recipient attribution.',
                    '{}'::jsonb, TRUE
                )
                """,
                (qld_state_id, source_document_id),
            )
        conn.commit()

    state_summary_with_aggregates_response = client.get(
        "/api/state-local/summary",
        params={"level": "state", "limit": "3"},
    )
    assert state_summary_with_aggregates_response.status_code == 200
    state_summary_with_aggregates = state_summary_with_aggregates_response.json()
    assert state_summary_with_aggregates["source_family"] == "state_local_disclosures"
    assert (
        state_summary_with_aggregates["aggregate_context_totals"][0]["source_dataset"]
        == "nsw_electoral_disclosures"
    )
    assert (
        state_summary_with_aggregates["aggregate_context_totals"][0][
            "reported_amount_total"
        ]
        == 1234.56
    )
    assert (
        state_summary_with_aggregates["top_aggregate_donor_locations"][0][
            "geography_name"
        ]
        == "Sydney"
    )
    assert (
        state_summary_with_aggregates["top_aggregate_donor_locations"][0][
            "attribution_scope"
        ]
        == "aggregate_context_not_recipient_attribution"
    )

    council_summary_response = client.get(
        "/api/state-local/summary",
        params={"level": "council", "limit": "3"},
    )
    assert council_summary_response.status_code == 200
    council_summary = council_summary_response.json()
    assert council_summary["totals_by_level"][0]["jurisdiction_level"] == "local"
    assert council_summary["totals_by_level"][0]["electoral_expenditure_count"] == 1
    assert (
        council_summary["totals_by_level"][0]["electoral_expenditure_reported_amount_total"]
        == 200
    )
    assert council_summary["totals_by_level"][0]["gift_or_donation_reported_amount_total"] == 0
    assert council_summary["totals_by_level"][0]["local_electorate_context_backed_count"] == 1
    assert council_summary["top_expenditure_actors"][0]["name"] == "QLD Donor"
    assert council_summary["top_events"][0]["external_id"] == "636"
    assert council_summary["top_local_electorates"][0]["name"] == "Whitsunday Regional"
    assert council_summary["recent_records"][0]["flow_kind"] == "qld_electoral_expenditure"
    assert council_summary["recent_records"][0]["local_electorate_name"] == "Whitsunday Regional"
    assert (
        council_summary["top_local_electorates"][0]["gift_or_donation_reported_amount_total"]
        == 0
    )

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_entity_id, source_raw_name,
                    recipient_entity_id, recipient_raw_name, amount,
                    date_received, receipt_type, disclosure_category,
                    jurisdiction_id, source_document_id, source_row_ref,
                    original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-qld-state-gift-second', %s, 'QLD Donor',
                    %s, 'QLD Recipient', 300, DATE '2026-04-20',
                    'Gift', 'qld_gift', %s, %s, 'pytest-qld-state-gift-second',
                    '{"Gift value":"$300"}', 'resolved', TRUE, %s
                )
                """,
                (
                    donor_id,
                    recipient_id,
                    qld_state_id,
                    source_document_id,
                    Jsonb(
                        {
                            "event_name": "2026 Stafford State By-election",
                            "flow_kind": "qld_gift",
                            "public_amount_counting_role": "single_observation",
                            "source_dataset": "qld_ecq_eds",
                            "transaction_kind": "gift",
                        }
                    ),
                ),
            )
        conn.commit()

    first_page_response = client.get(
        "/api/state-local/records",
        params={"level": "state", "limit": "1"},
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["total_count"] == 2
    assert first_page["record_count"] == 1
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert first_page["records"][0]["amount"] == 300
    assert first_page["records"][0]["source_document_id"] == source_document_id
    assert first_page["records"][0]["source_document_sha256"] == "pytest-qld-sha256"
    assert first_page["records"][0]["public_amount_counting_role"] == "single_observation"

    second_page_response = client.get(
        "/api/state-local/records",
        params={
            "level": "state",
            "cursor": first_page["next_cursor"],
            "limit": "5",
        },
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["record_count"] == 1
    assert second_page["has_more"] is False
    assert second_page["records"][0]["id"] != first_page["records"][0]["id"]
    assert second_page["records"][0]["flow_kind"] == "qld_gift"

    reused_cursor_response = client.get(
        "/api/state-local/records",
        params={"level": "council", "cursor": first_page["next_cursor"]},
    )
    assert reused_cursor_response.status_code == 400

    council_records_response = client.get(
        "/api/state-local/records",
        params={
            "level": "council",
            "flow_kind": "qld_electoral_expenditure",
            "limit": "5",
        },
    )
    assert council_records_response.status_code == 200
    council_records = council_records_response.json()
    assert council_records["total_count"] == 1
    assert council_records["records"][0]["flow_kind"] == "qld_electoral_expenditure"
    assert council_records["records"][0]["local_electorate_name"] == "Whitsunday Regional"

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, metadata
                )
                VALUES (
                    'act_gift_returns_2025_2026',
                    'Elections ACT Gift Returns 2025-2026',
                    'state_financial_disclosure_gift_return_table',
                    'Australian Capital Territory',
                    'https://www.elections.act.gov.au/funding-disclosures-and-registers/gift-returns/gift-returns-2025-2026',
                    now(), 200, 'text/html', 'pytest-act-sha256', '/tmp/act.html', '{}'::jsonb
                )
                RETURNING id
                """
            )
            act_source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Australian Capital Territory', 'state', 'ACT')
                RETURNING id
                """
            )
            act_state_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_raw_name, recipient_raw_name, amount,
                    date_received, date_reported, financial_year, receipt_type,
                    disclosure_category, jurisdiction_id, source_document_id,
                    source_row_ref, original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-act-gift-in-kind', 'Canberra Theatre Centre',
                    'Australian Labor Party (ACT Branch)', 294, DATE '2026-03-08',
                    DATE '2026-03-12', '2025-2026', 'Gift in kind',
                    'act_gift_in_kind', %s, %s, 'act_gift_returns_2025_2026_html:4',
                    '{"description_of_gift_in_kind":"GIK-Theatre Tickets"}',
                    'unresolved', TRUE, %s
                )
                """,
                (
                    act_state_id,
                    act_source_document_id,
                    Jsonb(
                        {
                            "description": "GIK-Theatre Tickets",
                            "flow_kind": "act_gift_in_kind",
                            "public_amount_counting_role": "single_observation",
                            "source_dataset": "act_elections_gift_returns",
                            "transaction_kind": "gift_in_kind",
                        }
                    ),
                ),
            )
        conn.commit()

    act_records_response = client.get(
        "/api/state-local/records",
        params={
            "level": "state",
            "flow_kind": "act_gift_in_kind",
            "limit": "5",
        },
    )
    assert act_records_response.status_code == 200
    act_records = act_records_response.json()
    assert act_records["total_count"] == 1
    assert act_records["records"][0]["source_dataset"] == "act_elections_gift_returns"
    assert act_records["records"][0]["flow_kind"] == "act_gift_in_kind"
    assert act_records["records"][0]["description_of_goods_or_services"] == "GIK-Theatre Tickets"
    assert act_records["records"][0]["source_document_sha256"] == "pytest-act-sha256"

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, metadata
                )
                VALUES (
                    'nt_ntec_annual_returns_gifts_2024_2025',
                    'NTEC Annual Returns Gifts 2024-2025',
                    'state_financial_disclosure_gift_return_table',
                    'Northern Territory',
                    'https://ntec.nt.gov.au/financial-disclosure/published-annual-returns/2024-2025-annual-returns-gifts',
                    now(), 200, 'text/html', 'pytest-nt-sha256', '/tmp/nt.html', '{}'::jsonb
                )
                RETURNING id
                """
            )
            nt_source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, metadata
                )
                VALUES (
                    'nt_ntec_annual_returns_2024_2025',
                    'NTEC Annual Returns 2024-2025',
                    'state_financial_disclosure_annual_return_table',
                    'Northern Territory',
                    'https://ntec.nt.gov.au/financial-disclosure/published-annual-returns/2024-2025-annual-returns',
                    now(), 200, 'text/html', 'pytest-nt-annual-sha256',
                    '/tmp/nt-annual.html', '{}'::jsonb
                )
                RETURNING id
                """
            )
            nt_annual_source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Northern Territory', 'state', 'NT')
                RETURNING id
                """
            )
            nt_state_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_raw_name, recipient_raw_name, amount,
                    date_reported, financial_year, receipt_type,
                    disclosure_category, jurisdiction_id, source_document_id,
                    source_row_ref, original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-nt-annual-gift', 'Example NT Donor',
                    'Example NT Party', 1500, DATE '2025-07-30', '2024-2025',
                    'Gift received over threshold', 'nt_annual_gift', %s, %s,
                    'nt_ntec_annual_returns_gifts_2024_2025_html:t1:r2:abc12345',
                    '{"address":"1 Public Street DARWIN NT 0800"}',
                    'unresolved', TRUE, %s
                )
                RETURNING id
                """,
                (
                    nt_state_id,
                    nt_source_document_id,
                    Jsonb(
                        {
                            "flow_kind": "nt_annual_gift",
                            "public_amount_counting_role": (
                                "jurisdictional_cross_disclosure_observation"
                            ),
                            "source_dataset": "nt_ntec_annual_returns_gifts",
                            "transaction_kind": "gift",
                        }
                    ),
                ),
            )
            nt_money_flow_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_raw_name, recipient_raw_name, amount,
                    date_reported, financial_year, receipt_type,
                    disclosure_category, jurisdiction_id, source_document_id,
                    source_row_ref, original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-nt-annual-receipt', 'Example NT Source',
                    'Example NT Party', 2500, DATE '2025-07-31', '2024-2025',
                    'Receipt over $1,500', 'nt_annual_receipt', %s, %s,
                    'nt_ntec_annual_returns_2024_2025_html:t1:r2:def67890',
                    '{"address":"2 Public Street DARWIN NT 0800"}',
                    'unresolved', TRUE, %s
                )
                RETURNING id
                """,
                (
                    nt_state_id,
                    nt_annual_source_document_id,
                    Jsonb(
                        {
                            "flow_kind": "nt_annual_receipt",
                            "public_amount_counting_role": (
                                "jurisdictional_cross_disclosure_observation"
                            ),
                            "source_dataset": "nt_ntec_annual_returns",
                            "transaction_kind": "receipt",
                        }
                    ),
                ),
            )
            nt_annual_money_flow_id = cur.fetchone()[0]
        conn.commit()
        load_influence_events(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT money_flow_id, amount_status, missing_data_flags
                FROM influence_event
                WHERE money_flow_id IN (%s, %s)
                """,
                (nt_money_flow_id, nt_annual_money_flow_id),
            )
            nt_events = {
                money_flow_id: (amount_status, missing_data_flags)
                for money_flow_id, amount_status, missing_data_flags in cur.fetchall()
            }
    for money_flow_id in (nt_money_flow_id, nt_annual_money_flow_id):
        nt_event_status, nt_flags = nt_events[money_flow_id]
        assert nt_event_status == "not_applicable"
        assert "jurisdictional_cross_disclosure_not_counted_in_reported_total" in nt_flags

    nt_records_response = client.get(
        "/api/state-local/records",
        params={"level": "state", "flow_kind": "nt_annual_gift", "limit": "5"},
    )
    assert nt_records_response.status_code == 200
    nt_records = nt_records_response.json()
    assert nt_records["total_count"] == 1
    assert nt_records["records"][0]["source_dataset"] == "nt_ntec_annual_returns_gifts"
    assert nt_records["records"][0]["amount"] == 1500
    assert nt_records["records"][0]["original_text"] is None
    assert nt_records["records"][0]["public_amount_counting_role"] == (
        "jurisdictional_cross_disclosure_observation"
    )

    nt_annual_records_response = client.get(
        "/api/state-local/records",
        params={"level": "state", "flow_kind": "nt_annual_receipt", "limit": "5"},
    )
    assert nt_annual_records_response.status_code == 200
    nt_annual_records = nt_annual_records_response.json()
    assert nt_annual_records["total_count"] == 1
    assert nt_annual_records["records"][0]["source_dataset"] == "nt_ntec_annual_returns"
    assert nt_annual_records["records"][0]["original_text"] is None

    nt_summary_response = client.get(
        "/api/state-local/summary",
        params={"level": "state", "limit": "10"},
    )
    assert nt_summary_response.status_code == 200
    nt_recent_records = [
        row
        for row in nt_summary_response.json()["recent_records"]
        if row["source_dataset"]
        in {"nt_ntec_annual_returns", "nt_ntec_annual_returns_gifts"}
    ]
    assert {row["source_dataset"] for row in nt_recent_records} == {
        "nt_ntec_annual_returns",
        "nt_ntec_annual_returns_gifts",
    }
    assert all(row["original_text"] is None for row in nt_recent_records)

    invalid_cursor_response = client.get(
        "/api/state-local/records",
        params={"level": "state", "cursor": "not-a-valid-cursor"},
    )
    assert invalid_cursor_response.status_code == 400


def test_waec_contribution_rows_are_served_with_date_and_version_caveats(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO source_document (
                    source_id, source_name, source_type, jurisdiction, url, fetched_at,
                    http_status, content_type, sha256, storage_path, metadata
                )
                VALUES (
                    'waec_ods_political_contributions',
                    'WAEC ODS Published Political Contributions',
                    'state_financial_disclosure_json_grid',
                    'Western Australia',
                    'https://disclosures.elections.wa.gov.au/public-dashboard/',
                    now(), 200, 'application/json', 'pytest-waec-sha256',
                    '/tmp/waec.json', '{}'::jsonb
                )
                RETURNING id
                """
            )
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Western Australia', 'state', 'WA')
                RETURNING id
                """
            )
            wa_state_id = cur.fetchone()[0]
            for external_key, amount, role, version in (
                ("pytest-waec-original", 1000, "single_observation", "Original"),
                (
                    "pytest-waec-amendment",
                    999,
                    "versioned_observation_pending_dedupe",
                    "Amendment",
                ),
            ):
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_raw_name, recipient_raw_name, amount,
                        date_reported, financial_year, receipt_type,
                        disclosure_category, jurisdiction_id, source_document_id,
                        source_row_ref, original_text, confidence, is_current, metadata
                    )
                    VALUES (
                        %s, 'WA Donor Pty Ltd', 'WA Party', %s, DATE '2026-04-27',
                        '2025-2026', 'Gift', 'wa_political_contribution',
                        %s, %s, %s, '{"amount":"$1,000"}', 'unresolved', TRUE, %s
                    )
                    """,
                    (
                        external_key,
                        amount,
                        wa_state_id,
                        source_document_id,
                        external_key,
                        Jsonb(
                            {
                                "date_caveat": (
                                    "WAEC publishes a disclosure-received date for this row."
                                ),
                                "flow_kind": "wa_political_contribution",
                                "public_amount_counting_role": role,
                                "source_dataset": "waec_political_contributions",
                                "transaction_kind": "political_contribution",
                                "version": version,
                            }
                        ),
                    ),
                )
        conn.commit()

    client = TestClient(app)
    summary_response = client.get(
        "/api/state-local/summary",
        params={"level": "state", "limit": "5"},
    )
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["totals_by_level"][0]["jurisdiction_code"] == "WA"
    assert summary["totals_by_level"][0]["gift_or_donation_count"] == 2
    assert summary["totals_by_level"][0]["gift_or_donation_reported_amount_total"] == 1000
    assert summary["top_gift_donors"][0]["reported_amount_total"] == 1000

    records_response = client.get(
        "/api/state-local/records",
        params={"level": "state", "flow_kind": "wa_political_contribution", "limit": "5"},
    )
    assert records_response.status_code == 200
    records = records_response.json()
    assert records["total_count"] == 2
    assert records["records"][0]["source_dataset"] == "waec_political_contributions"
    assert records["records"][0]["flow_kind"] == "wa_political_contribution"
    assert records["records"][0]["date_received"] is None
    assert records["records"][0]["date_reported"] == "2026-04-27"
    assert "disclosure-received date" in records["records"][0]["date_caveat"]
    assert {row["public_amount_counting_role"] for row in records["records"]} == {
        "single_observation",
        "versioned_observation_pending_dedupe",
    }


def test_withdrawn_source_rows_do_not_remain_public_events(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document ORDER BY id LIMIT 1")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction ORDER BY id LIMIT 1")
            jurisdiction_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_entity_id, source_raw_name,
                    recipient_person_id, recipient_raw_name, amount,
                    jurisdiction_id, source_document_id, source_row_ref,
                    original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-withdrawn-money-flow', %s, 'Withdrawn Donor',
                    %s, 'Withdrawn Recipient', 123.00, %s, %s,
                    'withdrawn-row', '{}', 'resolved', FALSE, %s
                )
                RETURNING id
                """,
                (
                    integration_db.entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    source_document_id,
                    Jsonb(
                        {
                            "source_dataset": "pytest_dataset",
                            "source_record_status": "not_in_latest_snapshot",
                        }
                    ),
                ),
            )
            withdrawn_money_flow_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type, source_entity_id,
                    recipient_person_id, jurisdiction_id, money_flow_id, amount,
                    currency, amount_status, disclosure_system, evidence_status,
                    review_status, description, source_document_id,
                    missing_data_flags, metadata
                )
                VALUES (
                    'money_flow:pytest-withdrawn-money-flow', 'money',
                    'donation_or_gift', %s, %s, %s, %s, 123.00, 'AUD',
                    'reported', 'pytest', 'official_record_parsed',
                    'not_required', 'Withdrawn Donor to Withdrawn Recipient',
                    %s, '[]'::jsonb, %s
                )
                RETURNING id
                """,
                (
                    integration_db.entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    withdrawn_money_flow_id,
                    source_document_id,
                    Jsonb({"derived_loader": "load_influence_events_v1"}),
                ),
            )
            withdrawn_event_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO evidence_claim (
                    claim_text, claim_level, evidence_class, subject_person_id,
                    status
                )
                VALUES (
                    'Withdrawn fixture claim', 1, 'source_record',
                    %s, 'draft'
                )
                RETURNING id
                """,
                (integration_db.person_id,),
            )
            claim_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO claim_evidence (
                    claim_id, source_document_id, money_flow_id,
                    influence_event_id, evidence_note
                )
                VALUES (%s, %s, %s, %s, 'preserve referenced event row')
                """,
                (
                    claim_id,
                    source_document_id,
                    withdrawn_money_flow_id,
                    withdrawn_event_id,
                ),
            )

            cur.execute(
                """
                INSERT INTO money_flow (
                    external_key, source_entity_id, source_raw_name,
                    recipient_person_id, recipient_raw_name, amount,
                    jurisdiction_id, source_document_id, source_row_ref,
                    original_text, confidence, is_current, metadata
                )
                VALUES (
                    'pytest-never-current-money-flow', %s, 'Never Current Donor',
                    %s, 'Never Current Recipient', 456.00, %s, %s,
                    'never-current-row', '{}', 'resolved', FALSE, %s
                )
                """,
                (
                    integration_db.entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    source_document_id,
                    Jsonb(
                        {
                            "source_dataset": "pytest_dataset",
                            "source_record_status": "not_in_latest_snapshot",
                        }
                    ),
                ),
            )
        conn.commit()

        summary = load_influence_events(conn)
        assert summary["suppressed_withdrawn_source_record_events"] >= 1

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT review_status, missing_data_flags, metadata->>'source_record_status'
                FROM influence_event
                WHERE external_key = 'money_flow:pytest-withdrawn-money-flow'
                """
            )
            status, flags, source_record_status = cur.fetchone()
            assert status == "rejected"
            assert "source_record_not_in_latest_snapshot" in flags
            assert source_record_status == "not_in_latest_snapshot"

            cur.execute(
                """
                SELECT count(*)
                FROM influence_event
                WHERE external_key = 'money_flow:pytest-never-current-money-flow'
                """
            )
            assert cur.fetchone()[0] == 0


def test_serving_database_quality_gate_reports_pass_and_failures(
    integration_db: IntegrationDatabase,
) -> None:
    config = ServingDatabaseQualityConfig(
        boundary_set="pytest_boundary_set",
        expected_house_boundary_count=2,
    )
    with connect(integration_db.url) as conn:
        passing_summary = run_serving_database_quality_checks(conn, config)
        assert passing_summary["status"] == "pass"

        failing_summary = run_serving_database_quality_checks(
            conn,
            ServingDatabaseQualityConfig(
                boundary_set="pytest_boundary_set",
                expected_house_boundary_count=150,
                min_current_influence_events=999,
            ),
        )
        assert failing_summary["status"] == "fail"
        failed_ids = {
            check["id"] for check in failing_summary["checks"] if check["status"] == "fail"
        }
        assert "house_boundary_count" in failed_ids
        assert "minimum_current_influence_events" in failed_ids


def test_qld_participant_loader_requires_review_for_candidate_name_only_matches(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
) -> None:
    jsonl_path = tmp_path / "qld_participants.jsonl"

    def participant_record(
        *,
        source_id: str,
        source_record_type: str,
        external_id: str,
        display_name: str,
        normalized_name: str,
        entity_type: str,
        identifier_type: str,
    ) -> dict:
        return {
            "schema_version": "qld_ecq_eds_participant_v1",
            "parser_name": "qld_ecq_eds_participant_normalizer",
            "parser_version": "1",
            "source_id": source_id,
            "source_record_type": source_record_type,
            "external_id": external_id,
            "stable_key": f"{source_id}:{source_record_type}:{external_id}",
            "display_name": display_name,
            "normalized_name": normalized_name,
            "entity_type": entity_type,
            "public_sector": "unknown",
            "confidence": "exact_identifier",
            "status": "observed",
            "source_updated_at": None,
            "evidence_note": "Pytest QLD participant lookup record.",
            "identifiers": [
                {
                    "identifier_type": identifier_type,
                    "identifier_value": external_id,
                }
            ],
            "aliases": [],
            "raw_record": {},
            "metadata": {},
        }

    records = [
        participant_record(
            source_id="qld_ecq_eds_api_political_electors",
            source_record_type="political_elector",
            external_id="pytest-elector-1",
            display_name="Jane Candidate",
            normalized_name="jane candidate",
            entity_type="candidate_or_elector",
            identifier_type="qld_ecq_elector_id",
        ),
        participant_record(
            source_id="qld_ecq_eds_api_political_parties",
            source_record_type="political_party",
            external_id="pytest-party-1",
            display_name="Example Party Queensland",
            normalized_name="example party queensland",
            entity_type="political_party",
            identifier_type="qld_ecq_political_party_id",
        ),
    ]
    jsonl_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Queensland', 'state', 'QLD')
                ON CONFLICT (name) DO UPDATE SET code = EXCLUDED.code
                RETURNING id
                """
            )
            qld_jurisdiction_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (canonical_name, normalized_name, entity_type)
                VALUES ('Jane Candidate', 'jane candidate', 'unknown')
                RETURNING id
                """
            )
            candidate_entity_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (canonical_name, normalized_name, entity_type)
                VALUES ('Example Party Queensland', 'example party queensland', 'unknown')
                RETURNING id
                """
            )
            party_entity_id = cur.fetchone()[0]
            for external_key, entity_id, raw_name in (
                ("pytest-qld-candidate-name-only", candidate_entity_id, "Jane Candidate"),
                ("pytest-qld-party-name-only", party_entity_id, "Example Party Queensland"),
            ):
                cur.execute(
                    """
                    INSERT INTO money_flow (
                        external_key, source_entity_id, source_raw_name,
                        recipient_entity_id, recipient_raw_name, amount,
                        receipt_type, disclosure_category, jurisdiction_id,
                        source_document_id, source_row_ref, original_text,
                        confidence, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, 100, 'Gift', 'qld_gift', %s,
                        %s, %s, '{}', 'resolved', %s
                    )
                    """,
                    (
                        external_key,
                        entity_id,
                        raw_name,
                        party_entity_id,
                        "Example Party Queensland",
                        qld_jurisdiction_id,
                        source_document_id,
                        external_key,
                        Jsonb({"source_dataset": "qld_ecq_eds", "flow_kind": "qld_gift"}),
                    ),
                )
        conn.commit()

        summary = load_qld_ecq_eds_participants(conn, jsonl_path=jsonl_path)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT identifier_type
                FROM entity_identifier
                WHERE entity_id = %s
                """,
                (candidate_entity_id,),
            )
            candidate_identifiers = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                SELECT identifier_type
                FROM entity_identifier
                WHERE entity_id = %s
                """,
                (party_entity_id,),
            )
            party_identifiers = [row[0] for row in cur.fetchall()]
            cur.execute(
                """
                SELECT status, match_method
                FROM entity_match_candidate
                WHERE entity_id = %s
                """,
                (candidate_entity_id,),
            )
            candidate_match = cur.fetchone()

    assert summary["auto_accepted_matches"] == 1
    assert summary["candidate_or_elector_name_only_matches_needing_review"] == 1
    assert summary["identifiers_inserted"] == 1
    assert candidate_identifiers == []
    assert party_identifiers == ["qld_ecq_political_party_id"]
    assert candidate_match == (
        "needs_review",
        "qld_ecq_exact_name_requires_participant_context",
    )


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

    # Headline umbrella count must be >= the sum of the family breakdowns surfaced in the
    # frontend "Records Linked To This Representative" panel, so that future SQL changes
    # cannot silently desync the headline from its breakdown. Equality holds for this
    # fixture because the seed only emits money + campaign_support; in production the
    # umbrella may also include private_interest, organisational_role, and other families.
    breakdown_sum = (
        map_properties["current_representative_lifetime_money_event_count"]
        + map_properties["current_representative_lifetime_benefit_event_count"]
        + map_properties["current_representative_lifetime_campaign_support_event_count"]
    )
    assert (
        map_properties["current_representative_lifetime_influence_event_count"]
        >= breakdown_sum
    ), (
        "Headline current_representative_lifetime_influence_event_count must be >= sum of "
        "money + benefit + campaign_support breakdowns shown in the UI."
    )
    assert (
        map_properties["current_representative_lifetime_influence_event_count"]
        == breakdown_sum
    ), (
        "For this controlled fixture (money + campaign_support only), the umbrella headline "
        "must equal the sum of money + benefit + campaign_support breakdowns."
    )

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
    graph_edge_by_type = {edge["type"]: edge for edge in graph_payload["edges"]}
    assert graph_payload["edge_count"] == 2
    assert graph_edge_by_type["disclosed_to_representative"]["reported_amount_total"] == 1250.0
    assert graph_edge_by_type["current_party_representation_context"][
        "allocation_method"
    ] == "no_allocation"
    assert all(edge.get("event_family") != "campaign_support" for edge in graph_payload["edges"])

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


def test_representative_evidence_endpoint_pages_records_without_mixing_campaign_support(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            for (
                external_key,
                family,
                event_type,
                event_subtype,
                amount,
                event_date,
                source_ref,
                missing_flags,
            ) in (
                (
                    "influence:clean-energy:jane-citizen:page-direct-1",
                    "benefit",
                    "gift",
                    "event_ticket_or_pass",
                    "100.00",
                    "2024-01-01",
                    "page-direct-1",
                    [],
                ),
                (
                    "influence:clean-energy:jane-citizen:page-direct-2",
                    "private_interest",
                    "fixture_private_interest",
                    None,
                    None,
                    "2024-01-01",
                    "page-direct-2",
                    [],
                ),
                (
                    "influence:clean-energy:jane-citizen:page-direct-undated",
                    "benefit",
                    "sponsored_travel_or_hospitality",
                    "private_aircraft_or_flight",
                    None,
                    None,
                    "page-direct-undated",
                    ["value_not_disclosed", "event_date_not_disclosed"],
                ),
                (
                    "influence:clean-energy:jane-citizen:page-campaign",
                    "campaign_support",
                    "candidate_or_senate_group_donation",
                    None,
                    "5000.00",
                    "2025-01-01",
                    "page-campaign",
                    [],
                ),
            ):
                cur.execute(
                    """
                    INSERT INTO influence_event (
                        external_key, event_family, event_type, event_subtype,
                        source_entity_id, source_raw_name, recipient_person_id,
                        recipient_raw_name, jurisdiction_id, amount, amount_status, event_date,
                        date_reported, chamber, disclosure_system, evidence_status,
                        extraction_method, review_status, description,
                        source_document_id, source_ref, missing_data_flags, metadata
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, 'Clean Energy Pty Ltd',
                        %s, 'Jane Citizen', %s, %s,
                        CASE WHEN %s::numeric IS NULL THEN 'not_disclosed' ELSE 'reported' END,
                        %s::date, '2024-02-01', 'house', 'pytest fixture',
                        'official_record', 'fixture_seed', 'not_required',
                        'Fixture representative evidence pagination row.',
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        external_key,
                        family,
                        event_type,
                        event_subtype,
                        integration_db.entity_id,
                        integration_db.person_id,
                        jurisdiction_id,
                        amount,
                        amount,
                        event_date,
                        source_document_id,
                        source_ref,
                        Jsonb(missing_flags),
                        Jsonb({"fixture": True}),
                    ),
                )
        conn.commit()

    client = TestClient(app)

    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    benefit_summary = {
        row["event_subtype"]: row for row in representative_payload["benefit_summary"]
    }
    assert benefit_summary["event_ticket_or_pass"]["event_count"] == 1
    assert benefit_summary["event_ticket_or_pass"]["reported_amount_total"] == 100.0
    assert benefit_summary["private_aircraft_or_flight"]["event_count"] == 1
    assert benefit_summary["private_aircraft_or_flight"]["needs_review_event_count"] == 0
    assert benefit_summary["private_aircraft_or_flight"]["missing_data_event_count"] == 1
    assert benefit_summary["private_aircraft_or_flight"]["named_provider_event_count"] == 1
    assert representative_payload["benefit_provider_summary"][0]["provider_name"] == (
        "Clean Energy Pty Ltd"
    )
    assert representative_payload["benefit_provider_summary"][0]["event_count"] == 2
    assert representative_payload["benefit_provider_summary"][0]["needs_review_event_count"] == 0

    first_page_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"limit": "2"},
    )
    assert first_page_response.status_code == 200
    first_page = first_page_response.json()
    assert first_page["group"] == "direct"
    assert first_page["total_count"] == 4
    assert first_page["has_more"] is True
    assert first_page["next_cursor"]
    assert [event["source_ref"] for event in first_page["events"]] == [
        "page-direct-2",
        "page-direct-1",
    ]
    assert all(event["event_family"] != "campaign_support" for event in first_page["events"])
    assert all(event["review_status"] != "rejected" for event in first_page["events"])

    second_page_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"limit": "2", "cursor": first_page["next_cursor"]},
    )
    assert second_page_response.status_code == 200
    second_page = second_page_response.json()
    assert second_page["has_more"] is False
    combined_ids = [event["id"] for event in first_page["events"] + second_page["events"]]
    assert len(combined_ids) == len(set(combined_ids))
    assert [event["source_ref"] for event in second_page["events"]] == [
        "fixture-row-1",
        "page-direct-undated",
    ]

    benefit_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"event_family": "benefit", "limit": "10"},
    )
    assert benefit_response.status_code == 200
    benefit_payload = benefit_response.json()
    assert benefit_payload["total_count"] == 2
    assert {event["source_ref"] for event in benefit_payload["events"]} == {
        "page-direct-1",
        "page-direct-undated",
    }

    campaign_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"group": "campaign_support", "limit": "10"},
    )
    assert campaign_response.status_code == 200
    campaign_payload = campaign_response.json()
    assert campaign_payload["total_count"] == 1
    assert campaign_payload["events"][0]["source_ref"] == "page-campaign"
    assert "not personal receipts" in campaign_payload["caveat"]

    invalid_cursor_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"cursor": "not-a-valid-cursor"},
    )
    assert invalid_cursor_response.status_code == 400


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


def test_candidate_contest_spine_preserves_non_temporal_campaign_context(
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
                    financial_year, date_received, return_type, receipt_type,
                    disclosure_category, jurisdiction_id, source_document_id,
                    source_row_ref, confidence, metadata
                )
                VALUES (
                    'aec-election-candidate:jane-citizen', 'Example Donor Pty Ltd',
                    'Jane Citizen', 3000.00, NULL, '2025-04-14',
                    'Election Candidate Return', 'Donation Received',
                    'election_candidate_or_senate_group_donation_received',
                    %s, %s, 'Candidate Donations.csv:1', 'unresolved', %s
                )
                """,
                (
                    jurisdiction_id,
                    source_document_id,
                    Jsonb(
                        {
                            "source_dataset": "aec_election",
                            "flow_kind": "election_candidate_or_senate_group_donation_received",
                            "event_name": "2025 Federal Election",
                            "candidate_context": {
                                "event_name": "2025 Federal Election",
                                "return_type": "Candidate",
                                "name": "Jane Citizen",
                                "electorate_name": "Melbourne",
                                "electorate_state": "VIC",
                                "party_id": "EX",
                                "party_name": "Example Party",
                                "source_table": "Candidate Return.csv",
                                "source_row_number": "42",
                            },
                        }
                    ),
                ),
            )
        conn.commit()

        link_summary = link_aec_candidate_campaign_money_flows(conn)
        contest_summary = load_aec_candidate_contests(conn)
        load_influence_events(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    money_flow.recipient_person_id,
                    money_flow.candidate_contest_id,
                    money_flow.office_term_id,
                    money_flow.metadata->'candidate_contest'->>'match_status',
                    contest.match_status,
                    contest.match_method,
                    contest.person_id,
                    contest.office_term_id,
                    contest.election_year,
                    contest.chamber,
                    contest.metadata->>'temporal_check',
                    contest.metadata->'input_money_flow_external_keys',
                    contest.metadata->'source_row_refs'
                FROM money_flow
                JOIN candidate_contest contest
                  ON contest.id = money_flow.candidate_contest_id
                WHERE money_flow.external_key = 'aec-election-candidate:jane-citizen'
                """
            )
            money_flow_row = cur.fetchone()
            cur.execute(
                """
                SELECT
                    candidate_contest_id,
                    office_term_id,
                    event_family,
                    event_type,
                    metadata->'base_metadata'->'candidate_contest'->>'match_status'
                FROM influence_event
                WHERE external_key = 'money_flow:aec-election-candidate:jane-citizen'
                """
            )
            event_row = cur.fetchone()

    assert link_summary["candidate_campaign_money_flows_linked"] == 1
    assert contest_summary["candidate_contests"] == 1
    assert contest_summary["candidate_contest_name_context_only"] == 1
    assert money_flow_row[0] == integration_db.person_id
    assert money_flow_row[1] is not None
    assert money_flow_row[2] is None
    assert money_flow_row[3] == "name_context_only"
    assert money_flow_row[4] == "name_context_only"
    assert money_flow_row[5] == (
        "candidate_name_electorate_state_exact_unique_without_temporal_check"
    )
    assert money_flow_row[6] == integration_db.person_id
    assert money_flow_row[7] is None
    assert money_flow_row[8] == 2025
    assert money_flow_row[9] == "house"
    assert money_flow_row[10] == "not_applied"
    assert money_flow_row[11] == ["aec-election-candidate:jane-citizen"]
    assert money_flow_row[12] == ["Candidate Donations.csv:1"]
    assert event_row[0] == money_flow_row[1]
    assert event_row[1] is None
    assert event_row[2] == "campaign_support"
    assert event_row[3] == "candidate_or_senate_group_donation"
    assert event_row[4] == "name_context_only"


def test_candidate_contest_links_are_cleared_when_source_context_disappears(
    integration_db: IntegrationDatabase,
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    source_body_path = tmp_path / "aec-election.csv"
    source_body_path.write_text("fixture\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": "pytest-aec-election-corrected",
                    "name": "Pytest Corrected AEC Election Export",
                    "source_type": "test_fixture",
                    "jurisdiction": "Commonwealth",
                    "url": "https://example.test/aec-election",
                },
                "fetched_at": "20260429T000000Z",
                "http_status": 200,
                "content_type": "text/csv",
                "sha256": "pytest-aec-election-corrected-sha",
                "body_path": str(source_body_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    def write_record(include_candidate_context: bool) -> Path:
        record = {
            "source_dataset": "aec_election",
            "source_table": "Candidate Donations.csv",
            "source_row_number": "1",
            "flow_kind": "election_candidate_or_senate_group_donation_received",
            "financial_year": "",
            "return_type": "Candidate",
            "source_raw_name": "Example Donor Pty Ltd",
            "recipient_raw_name": "Jane Citizen",
            "receipt_type": "Donation Received",
            "date": "14/04/2025",
            "amount_aud": "3000.00",
            "jurisdiction_name": "Commonwealth",
            "jurisdiction_level": "federal",
            "jurisdiction_code": "CWLTH",
            "event_name": "2025 Federal Election",
            "source_metadata_path": str(metadata_path),
            "source_body_path": str(source_body_path),
            "original": {"fixture": "candidate-context-correction"},
        }
        if include_candidate_context:
            record["candidate_context"] = {
                "event_name": "2025 Federal Election",
                "return_type": "Candidate",
                "name": "Jane Citizen",
                "electorate_name": "Melbourne",
                "electorate_state": "VIC",
                "party_id": "EX",
                "party_name": "Example Party",
            }
        jsonl_path = tmp_path / (
            "with_candidate_context.jsonl"
            if include_candidate_context
            else "without_candidate_context.jsonl"
        )
        jsonl_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
        return jsonl_path

    with connect(integration_db.url) as conn:
        first_summary = _load_aec_money_flow_jsonl(
            conn,
            write_record(include_candidate_context=True),
            default_source_dataset="aec_election",
        )
        load_influence_events(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT recipient_person_id, candidate_contest_id, metadata ? 'candidate_contest'
                FROM money_flow
                WHERE source_row_ref = 'Candidate Donations.csv:1'
                  AND metadata->>'source_dataset' = 'aec_election'
                """
            )
            linked_row = cur.fetchone()

        second_summary = _load_aec_money_flow_jsonl(
            conn,
            write_record(include_candidate_context=False),
            default_source_dataset="aec_election",
        )
        load_influence_events(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    recipient_person_id,
                    candidate_contest_id,
                    office_term_id,
                    metadata ? 'candidate_contest',
                    metadata ? 'recipient_person_match'
                FROM money_flow
                WHERE source_row_ref = 'Candidate Donations.csv:1'
                  AND metadata->>'source_dataset' = 'aec_election'
                """
            )
            corrected_row = cur.fetchone()
            cur.execute(
                """
                SELECT recipient_person_id, candidate_contest_id, office_term_id
                FROM influence_event
                WHERE money_flow_id = %s
                """,
                (corrected_row[0],),
            )
            corrected_event = cur.fetchone()

    assert first_summary["candidate_contests"] == 1
    assert linked_row[0] == integration_db.person_id
    assert linked_row[1] is not None
    assert linked_row[2] is True
    assert second_summary["candidate_contests"] == 0
    assert corrected_row[1] is None
    assert corrected_row[2] is None
    assert corrected_row[3] is None
    assert corrected_row[4] is False
    assert corrected_row[5] is False
    assert corrected_event == (None, None, None)


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


def test_lobbyist_register_observations_become_access_context_events(
    integration_db: IntegrationDatabase,
) -> None:
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM source_document WHERE source_id = 'pytest-source'")
            source_document_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO entity (
                    canonical_name, normalized_name, entity_type, country, source_document_id
                )
                VALUES (
                    'Acme Public Affairs Pty Ltd', 'acme public affairs pty ltd',
                    'lobbyist_organisation', 'AU', %s
                )
                RETURNING id
                """,
                (source_document_id,),
            )
            lobbyist_org_entity_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO official_identifier_observation (
                    stable_key, source_document_id, source_id, source_record_type,
                    external_id, display_name, normalized_name, entity_type,
                    public_sector, confidence, status, source_updated_at,
                    evidence_note, identifiers, aliases, raw_record, metadata
                )
                VALUES (
                    'australian_lobbyists_register:lobbyist_organisation:org-1',
                    %s, 'australian_lobbyists_register', 'lobbyist_organisation',
                    'org-1', 'Acme Public Affairs Pty Ltd',
                    'acme public affairs pty ltd', 'lobbyist_organisation',
                    'consulting', 'exact_identifier', 'registered',
                    '2026-04-20T00:00:00Z',
                    'Australian Government Register of Lobbyists organisation.',
                    %s, '[]'::jsonb, %s, '{}'::jsonb
                )
                RETURNING id
                """,
                (
                    source_document_id,
                    Jsonb(
                        [
                            {
                                "identifier_type": "lobbyist_register_organisation_id",
                                "identifier_value": "org-1",
                            }
                        ]
                    ),
                    Jsonb({"displayName": "Acme Public Affairs Pty Ltd", "id": "org-1"}),
                ),
            )
            org_observation_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO official_identifier_observation (
                    stable_key, source_document_id, source_id, source_record_type,
                    external_id, display_name, normalized_name, entity_type,
                    public_sector, confidence, status, source_updated_at,
                    evidence_note, identifiers, aliases, raw_record, metadata
                )
                VALUES (
                    'australian_lobbyists_register:lobbyist_client:org-1:client-1',
                    %s, 'australian_lobbyists_register', 'lobbyist_client',
                    'org-1:client:client-1', 'Clean Energy Pty Ltd',
                    'clean energy pty ltd', 'unknown', 'unknown',
                    'exact_identifier', 'represented_client',
                    '2026-04-21T00:00:00Z',
                    'Client listed for a registered third-party lobbying organisation.',
                    '[]'::jsonb, '[]'::jsonb,
                    %s, %s
                )
                RETURNING id
                """,
                (
                    source_document_id,
                    Jsonb({"displayName": "Clean Energy Pty Ltd", "id": "client-1"}),
                    Jsonb(
                        {
                            "lobbyist_organisation_id": "org-1",
                            "lobbyist_organisation_name": "Acme Public Affairs Pty Ltd",
                        }
                    ),
                ),
            )
            client_observation_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO official_identifier_observation (
                    stable_key, source_document_id, source_id, source_record_type,
                    external_id, display_name, normalized_name, entity_type,
                    public_sector, confidence, status, source_updated_at,
                    evidence_note, identifiers, aliases, raw_record, metadata
                )
                VALUES (
                    'australian_lobbyists_register:lobbyist_person:org-1:person-1',
                    %s, 'australian_lobbyists_register', 'lobbyist_person',
                    'org-1:lobbyist:casey adviser', 'Casey Adviser',
                    'casey adviser', 'individual', 'unknown',
                    'exact_name_context', 'former_representative',
                    '2026-04-22T00:00:00Z',
                    'Individual lobbyist listed for a registered organisation.',
                    '[]'::jsonb, '[]'::jsonb,
                    %s, %s
                )
                RETURNING id
                """,
                (
                    source_document_id,
                    Jsonb(
                        {
                            "displayName": "Casey Adviser",
                            "isFormerRepresentative": True,
                        }
                    ),
                    Jsonb(
                        {
                            "lobbyist_organisation_id": "org-1",
                            "lobbyist_organisation_name": "Acme Public Affairs Pty Ltd",
                            "is_former_representative": True,
                        }
                    ),
                ),
            )
            lobbyist_person_observation_id = cur.fetchone()[0]

            cur.executemany(
                """
                INSERT INTO entity_match_candidate (
                    entity_id, observation_id, match_method, confidence, status,
                    score, evidence_note
                )
                VALUES (%s, %s, %s, %s, 'auto_accepted', 100.00, %s)
                """,
                [
                    (
                        lobbyist_org_entity_id,
                        org_observation_id,
                        "exact_identifier",
                        "exact_identifier",
                        "Fixture official organisation identifier.",
                    ),
                    (
                        integration_db.entity_id,
                        client_observation_id,
                        "exact_identifier",
                        "exact_identifier",
                        "Fixture official client identifier.",
                    ),
                    (
                        lobbyist_org_entity_id,
                        lobbyist_person_observation_id,
                        "organisation_context_fixture",
                        "exact_identifier",
                        "Fixture organisation context for listed lobbyist.",
                    ),
                ],
            )
        conn.commit()

        summary = load_influence_events(conn)
        assert summary["access_events"] == 2
        assert summary["event_family_counts"]["access"] == 2

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    event_type, source_entity_id, recipient_entity_id,
                    source_raw_name, recipient_raw_name, amount_status,
                    date_reported, missing_data_flags, metadata->>'claim_scope',
                    description
                FROM influence_event
                WHERE event_family = 'access'
                ORDER BY event_type, source_raw_name, recipient_raw_name
                """
            )
            rows = cur.fetchall()

    access_by_type = {row[0]: row for row in rows}
    client_row = access_by_type["registered_lobbyist_client_relationship"]
    person_row = access_by_type["registered_lobbyist_person"]
    assert client_row[1] == integration_db.entity_id
    assert client_row[2] == lobbyist_org_entity_id
    assert client_row[3] == "Clean Energy Pty Ltd"
    assert client_row[4] == "Acme Public Affairs Pty Ltd"
    assert client_row[5] == "not_applicable"
    assert str(client_row[6]) == "2026-04-21"
    assert "not evidence of a specific meeting" in client_row[9]
    assert "not a meeting" in client_row[8]
    assert person_row[1] == lobbyist_org_entity_id
    assert person_row[4] == "Casey Adviser"
    assert "listed_lobbyist_is_former_representative" in person_row[7]

    client = TestClient(app)
    entity_response = client.get(f"/api/entities/{lobbyist_org_entity_id}")
    assert entity_response.status_code == 200
    entity_payload = entity_response.json()
    by_family = {row["event_family"]: row for row in entity_payload["as_source_summary"]}
    assert by_family["access"]["event_count"] == 1
    assert "registry context" in entity_payload["caveat"]

    graph_response = client.get(
        "/api/graph/influence",
        params={"entity_id": lobbyist_org_entity_id, "limit": "10"},
    )
    assert graph_response.status_code == 200
    graph_payload = graph_response.json()
    access_edges = [edge for edge in graph_payload["edges"] if edge.get("event_family") == "access"]
    assert len(access_edges) == 2
    assert all(edge.get("reported_amount_total") is None for edge in access_edges)
    assert all("not a meeting" in edge["claim_scope"] for edge in access_edges)
    assert "registry context" in graph_payload["caveat"]


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
            cur.execute(
                """
                INSERT INTO party_entity_link (
                    party_id, entity_id, link_type, method, confidence, review_status,
                    evidence_note, reviewer, reviewed_at, source_document_id
                )
                VALUES (
                    %s, %s, 'associated_entity', 'manual', 'manual_reviewed', 'reviewed',
                    'Fixture second reviewed link type for the same entity.', 'pytest', now(), %s
                )
                """,
                (party_id, party_entity_id, source_document_id),
            )
            cur.execute(
                """
                INSERT INTO entity (
                    canonical_name, normalized_name, entity_type, country, source_document_id
                )
                VALUES ('Second Donor Pty Ltd', 'second donor pty ltd', 'company', 'AU', %s)
                RETURNING id
                """,
                (source_document_id,),
            )
            second_donor_entity_id = cur.fetchone()[0]
            for external_key, review_status, amount, source_id, source_name in (
                (
                    "party-profile:accepted",
                    "not_required",
                    "3000.00",
                    donor_entity_id,
                    "Example Donor Pty Ltd",
                ),
                (
                    "party-profile:second-accepted",
                    "not_required",
                    "2000.00",
                    second_donor_entity_id,
                    "Second Donor Pty Ltd",
                ),
                (
                    "party-profile:rejected",
                    "rejected",
                    "9999.00",
                    donor_entity_id,
                    "Example Donor Pty Ltd",
                ),
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
                        %s, 'money', 'donation_or_gift', %s, %s,
                        %s, 'Example Party Federal Campaign', %s, %s, 'reported',
                        '2024-06-01', '2023-24', 'pytest fixture',
                        'official_record_parsed', 'fixture_seed', %s,
                        'Fixture party disclosure.', %s, 'party-row', '[]'::jsonb, %s
                    )
                    """,
                    (
                        external_key,
                        source_id,
                        source_name,
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
    assert payload["money_summary"][0]["reported_amount_total"] == 5000.0
    assert payload["top_sources"][0]["source_label"] == "Example Donor Pty Ltd"
    assert payload["recent_events"][0]["review_status"] == "not_required"

    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    party_exposure = representative_payload["party_exposure_summary"][0]
    assert party_exposure["party_name"] == "Example Party"
    assert party_exposure["event_count"] == 2
    assert party_exposure["party_context_reported_amount_total"] == 5000.0
    assert party_exposure["modelled_amount_total"] == 1250.0
    assert party_exposure["allocation_method"] == "equal_current_representative_share"
    assert (
        party_exposure["allocation_basis"]
        == "loaded_period_reviewed_party_entity_receipts_divided_by_current_party_representatives"
    )
    assert party_exposure["event_period_scope"] == "all_loaded_reviewed_party_entity_receipts"
    assert party_exposure["representative_scope"] == "current_office_term_party_membership"
    assert party_exposure["allocation_denominator"] == 4
    assert party_exposure["input_source_document_count"] == 1
    assert "not a disclosed personal receipt" in party_exposure["claim_scope"]
    assert "term-bounded total" in party_exposure["claim_scope"]
    assert "not disclosed personal receipts" in representative_payload["party_exposure_caveat"]
    assert "not term-bounded" in representative_payload["party_exposure_caveat"]

    direct_money_summary = [
        row for row in representative_payload["event_summary"] if row["event_family"] == "money"
    ][0]
    assert direct_money_summary["event_count"] == 1
    assert direct_money_summary["reported_amount_total"] == 1250.0
    assert len(representative_payload["recent_events"]) == 1
    assert representative_payload["recent_events"][0]["source_raw_name"] == "Clean Energy Pty Ltd"
    assert all(
        event["source_raw_name"] not in {"Example Donor Pty Ltd", "Second Donor Pty Ltd"}
        for event in representative_payload["recent_events"]
    )

    direct_evidence_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"limit": "10"},
    )
    assert direct_evidence_response.status_code == 200
    direct_evidence_payload = direct_evidence_response.json()
    assert direct_evidence_payload["total_count"] == 1
    assert direct_evidence_payload["events"][0]["source_raw_name"] == "Clean Energy Pty Ltd"
    assert all(
        event["source_raw_name"] not in {"Example Donor Pty Ltd", "Second Donor Pty Ltd"}
        for event in direct_evidence_payload["events"]
    )

    person_graph_response = client.get(
        "/api/graph/influence",
        params={"person_id": integration_db.person_id, "limit": "1"},
    )
    assert person_graph_response.status_code == 200
    person_graph_payload = person_graph_response.json()
    person_edge_types = {edge["type"] for edge in person_graph_payload["edges"]}
    assert "money_to_reviewed_party_entities" in person_edge_types
    assert "reviewed_party_entity_link" in person_edge_types
    assert "modelled_party_money_exposure" in person_edge_types
    modelled_edges = [
        edge
        for edge in person_graph_payload["edges"]
        if edge["type"] == "modelled_party_money_exposure"
    ]
    assert modelled_edges[0]["evidence_tier"] == "modelled_allocation"
    assert modelled_edges[0]["allocation_method"] == "equal_current_representative_share"
    assert modelled_edges[0]["allocation_denominator"] == 4
    assert modelled_edges[0].get("reported_amount_total") is None
    assert modelled_edges[0]["party_context_reported_amount_total"] == 5000.0
    assert modelled_edges[0]["modelled_amount_total"] == 1250.0
    assert (
        modelled_edges[0]["model_name"]
        == "loaded_period_equal_current_representative_party_exposure"
    )
    assert (
        modelled_edges[0]["event_period_scope"]
        == "all_loaded_reviewed_party_entity_receipts"
    )
    assert modelled_edges[0]["input_event_ids"]
    assert modelled_edges[0]["input_source_document_ids"]
    assert "not a disclosed personal receipt" in modelled_edges[0]["claim_scope"]
    assert "term-bounded total" in modelled_edges[0]["claim_scope"]


def test_dual_linked_party_entity_receipt_stays_out_of_direct_representative_surfaces(
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
                    'Example Party Campaign Account',
                    'example party campaign account',
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
                VALUES ('Dual Linked Donor Pty Ltd', 'dual linked donor pty ltd', 'company', 'AU', %s)
                RETURNING id
                """,
                (source_document_id,),
            )
            donor_entity_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO party_entity_link (
                    party_id, entity_id, link_type, method, confidence,
                    review_status, reviewer, reviewed_at, source_document_id, evidence_note
                )
                VALUES (
                    %s, %s, 'party_branch', 'manual', 'manual_reviewed',
                    'reviewed', 'pytest', now(), %s,
                    'Fixture reviewed party/entity link.'
                )
                """,
                (party_id, party_entity_id, source_document_id),
            )
            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type, source_entity_id,
                    source_raw_name, recipient_entity_id, recipient_person_id,
                    recipient_raw_name, jurisdiction_id, amount, amount_status,
                    event_date, reporting_period, disclosure_system, evidence_status,
                    extraction_method, review_status, description, source_document_id,
                    source_ref, missing_data_flags, metadata
                )
                VALUES (
                    'party-entity:dual-linked-person-row', 'money', 'donation_or_gift',
                    %s, 'Dual Linked Donor Pty Ltd', %s, %s,
                    'Example Party Campaign Account', %s, 7000.00, 'reported',
                    '2024-07-01', '2023-24', 'pytest fixture',
                    'official_record_parsed', 'fixture_seed', 'not_required',
                    'Fixture broad party/entity receipt that is also person-linked.',
                    %s, 'dual-linked-row', '[]'::jsonb, %s
                )
                """,
                (
                    donor_entity_id,
                    party_entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    source_document_id,
                    Jsonb({"return_type": "Political Party Return"}),
                ),
            )
        conn.commit()

    client = TestClient(app)
    representative_response = client.get(f"/api/representatives/{integration_db.person_id}")
    assert representative_response.status_code == 200
    representative_payload = representative_response.json()
    direct_money_summary = [
        row for row in representative_payload["event_summary"] if row["event_family"] == "money"
    ][0]
    assert direct_money_summary["event_count"] == 1
    assert direct_money_summary["reported_amount_total"] == 1250.0
    assert len(representative_payload["recent_events"]) == 1
    assert representative_payload["recent_events"][0]["source_raw_name"] == "Clean Energy Pty Ltd"

    evidence_response = client.get(
        f"/api/representatives/{integration_db.person_id}/evidence",
        params={"limit": "10"},
    )
    assert evidence_response.status_code == 200
    evidence_payload = evidence_response.json()
    assert evidence_payload["total_count"] == 1
    assert evidence_payload["events"][0]["source_raw_name"] == "Clean Energy Pty Ltd"

    map_response = client.get(
        "/api/map/electorates",
        params={"chamber": "house", "include_geometry": "false"},
    )
    assert map_response.status_code == 200
    map_payload = map_response.json()
    melbourne = next(
        feature
        for feature in map_payload["features"]
        if feature["properties"]["electorate_id"] == integration_db.electorate_id
    )
    properties = melbourne["properties"]
    assert properties["current_representative_lifetime_money_event_count"] == 1
    assert properties["current_representative_lifetime_reported_amount_total"] == 1250.0


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
