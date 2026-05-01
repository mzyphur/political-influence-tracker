"""Integration tests for the AEC Register loader (Batch C PR 2).

These tests run against the real Postgres integration DB (the same one
used by `test_postgres_integration.py`) and assert the dev's C-rule
behaviour end-to-end:

- An associatedentity row whose AssociatedParties names a state ALP branch
  produces exactly one reviewed party_entity_link to canonical ALP, with
  method='official', confidence='exact_identifier', reviewer set to the
  system reviewer string, and metadata recording the resolver rule, raw
  AEC segment, and attribution-limit caveat.
- An associatedentity row with multiple branch segments produces one
  idempotent party_entity_link per uniquely-resolved party (the loader
  must be safe to re-run).
- An AssociatedParties segment that names an individual (e.g. 'Allegra
  Spender') does NOT produce a party_entity_link of any kind.
- A significantthirdparty row whose AssociatedParties is populated still
  does NOT produce a party_entity_link (per the C-rule).
- A politicalparty register row whose ClientName does not match any
  existing party.id becomes an aec_register_of_entities_observation row
  with resolver_status='unresolved_no_match'; the local party table is
  NOT mutated to add a new canonical row.
- Direct representative money totals (the umbrella headline + the per-
  family breakdown) are unchanged across a load: the loader must not
  touch influence_event or current_representative_lifetime_money_event_count.
- The loader is idempotent: a second invocation against the same artefact
  produces the same row counts and link counts.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


# Re-use the integration_db fixture and helpers from the main file.
pytestmark = pytest.mark.skipif(
    os.environ.get("AUPOL_RUN_POSTGRES_INTEGRATION") != "1"
    and os.environ.get("CI") != "true",
    reason="Set AUPOL_RUN_POSTGRES_INTEGRATION=1 to run Postgres integration tests locally.",
)


from au_politics_money.db.aec_register_loader import (  # noqa: E402
    SYSTEM_REVIEWER,
    load_aec_register_of_entities,
)
from au_politics_money.db.load import connect  # noqa: E402
from au_politics_money.ingest.aec_register_entities import (  # noqa: E402
    SOURCE_ID_BY_CLIENT_TYPE,
)
from tests.test_postgres_integration import (  # noqa: E402
    IntegrationDatabase,
    integration_db,  # noqa: F401
)


_AEC_RAW_FIELDS_TEMPLATE = {
    "ViewName": "Register of entities: Political parties",
    "FCRMClientId": None,
    "RegisterOfPolitcalParties": "Register - Test Entity",
    "LinkToRegisterOfPolitcalParties": "https://www.aec.gov.au/example",
    "ShowInPoliticalPartyRegister": None,
    "ShowInAssociatedEntityRegister": None,
    "ShowInSignificantThirdPartyRegister": None,
    "ShowInThirdPartyRegister": None,
    "IsNonRegisteredBranch": "Registered",
    "ClientType": "associatedentity",
    "ClientTypeDescription": None,
    "ClientContactFirstName": "Pat",
    "ClientContactLastName": "Citizen",
    "ClientContactFullName": "Pat Citizen",
    "FinancialYear": "",
    "FinancialYearStartDate": None,
    "ReturnId": None,
    "ReturnType": None,
    "AssociatedParties": "",
    "RegisteredAsAssociatedEntity": "Yes",
    "RegisteredAsSignificantThirdParty": "No",
    "AmmendmentNumber": None,
    "ReturnStatus": None,
}


def _seed_canonical_alp_party(conn) -> int:
    """Ensure a single canonical ALP party row exists in the test schema."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM party WHERE name = 'Australian Labor Party'")
        existing = cur.fetchone()
        if existing:
            return int(existing[0])
        cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
        jurisdiction_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO party (name, short_name, jurisdiction_id)
            VALUES ('Australian Labor Party', 'ALP', %s)
            RETURNING id
            """,
            (jurisdiction_id,),
        )
        return int(cur.fetchone()[0])


def _write_artefacts(
    tmp_path: Path,
    client_type: str,
    rows: list[dict],
    *,
    timestamp: str,
) -> tuple[Path, Path]:
    source_id = SOURCE_ID_BY_CLIENT_TYPE[client_type]
    raw_dir = tmp_path / "raw" / source_id / timestamp
    raw_dir.mkdir(parents=True, exist_ok=True)
    body_path = raw_dir / "client_details_read_page_001.json"
    body_path.write_text(json.dumps({"Data": [], "Total": 0}), encoding="utf-8")
    metadata_path = raw_dir / "client_details_read_page_001.json.metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": source_id,
                    "name": f"AEC Register fixture ({client_type})",
                    "source_type": "aec_register_of_entities_api",
                    "jurisdiction": "Commonwealth",
                    "url": f"https://transparency.aec.gov.au/RegisterOfEntities?clientType={client_type}",
                },
                "fetched_at": timestamp,
                "phase": "client_details_read_post",
                "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
                "final_url": (
                    f"https://transparency.aec.gov.au/RegisterOfEntities?"
                    f"clientType={client_type}"
                ),
                "body_path": str(body_path.resolve()),
                "http_status": 200,
                "http_response_headers": {},
                "cookies_after_response": [],
                "content_type": "application/json; charset=utf-8",
                "content_length": 0,
                "sha256": f"fixture-{client_type}-{timestamp}",
                "request_params_redacted": {
                    "clientType": client_type,
                    "__RequestVerificationToken": "__redacted_anti_forgery_token__",
                },
                "page_index_within_session": 1,
                "redaction": {
                    "anti_forgery_token": "redacted_in_archive_metadata",
                    "cookie_values": "redacted_in_archive_metadata",
                    "cookie_request_header": "never_persisted",
                },
            }
        ),
        encoding="utf-8",
    )

    processed_dir = tmp_path / "processed" / "aec_register_of_entities" / client_type
    processed_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = processed_dir / f"{timestamp}.jsonl"
    summary_path = processed_dir / f"{timestamp}.summary.json"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for index, raw in enumerate(rows):
            full_raw = {**_AEC_RAW_FIELDS_TEMPLATE, **raw}
            full_raw["ClientType"] = client_type
            client_identifier = str(full_raw.get("ClientIdentifier") or "")
            assert client_identifier, "fixture row must set ClientIdentifier"
            associated_parties_raw = full_raw.get("AssociatedParties") or ""
            associated_party_segments = [
                segment.strip()
                for segment in associated_parties_raw.split(";")
                if segment.strip()
            ]
            observation_fingerprint = (
                f"fixture-{client_type}-{client_identifier}-{index}"
            )
            row = {
                "schema_version": "aec_register_of_entities_observation_v1",
                "parser_name": "aec_register_of_entities_v1",
                "parser_version": "1",
                "source_id": SOURCE_ID_BY_CLIENT_TYPE[client_type],
                "source_metadata_path": str(metadata_path.resolve()),
                "source_body_path": str(body_path.resolve()),
                "client_type": client_type,
                "client_identifier": client_identifier,
                "client_name": full_raw.get("ClientName"),
                "client_contact_full_name": full_raw.get("ClientContactFullName"),
                "view_name": full_raw.get("ViewName"),
                "return_id": full_raw.get("ReturnId"),
                "financial_year": full_raw.get("FinancialYear"),
                "return_type": full_raw.get("ReturnType"),
                "return_status": full_raw.get("ReturnStatus"),
                "ammendment_number": full_raw.get("AmmendmentNumber"),
                "is_non_registered_branch": full_raw.get("IsNonRegisteredBranch"),
                "associated_parties_raw": associated_parties_raw,
                "associated_party_segments": associated_party_segments,
                "show_in_political_party_register": full_raw.get(
                    "ShowInPoliticalPartyRegister"
                ),
                "show_in_associated_entity_register": full_raw.get(
                    "ShowInAssociatedEntityRegister"
                ),
                "show_in_significant_third_party_register": full_raw.get(
                    "ShowInSignificantThirdPartyRegister"
                ),
                "show_in_third_party_register": full_raw.get("ShowInThirdPartyRegister"),
                "registered_as_associated_entity": full_raw.get(
                    "RegisteredAsAssociatedEntity"
                ),
                "registered_as_significant_third_party": full_raw.get(
                    "RegisteredAsSignificantThirdParty"
                ),
                "register_of_political_parties_label": full_raw.get(
                    "RegisterOfPolitcalParties"
                ),
                "link_to_register_of_political_parties": full_raw.get(
                    "LinkToRegisterOfPolitcalParties"
                ),
                "page_index": 1,
                "row_index_in_page": index,
                "observation_fingerprint": observation_fingerprint,
                "raw_row_field_names": sorted(full_raw.keys()),
                "raw_row": full_raw,
            }
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema_version": "aec_register_of_entities_summary_v1",
        "parser_name": "aec_register_of_entities_v1",
        "parser_version": "1",
        "source_id": SOURCE_ID_BY_CLIENT_TYPE[client_type],
        "client_type": client_type,
        "generated_at": timestamp,
        "raw_dir": str(raw_dir.resolve()),
        "raw_page_metadata_path": str(metadata_path.resolve()),
        "raw_post_metadata_paths": [str(metadata_path.resolve())],
        "jsonl_path": str(jsonl_path.resolve()),
        "row_count": len(rows),
        "upstream_total": len(rows),
        "page_index_count": 1,
        "page_size_used": 200,
        "completeness_note": "fixture",
        "redaction_policy": "fixture",
        "source_attribution_caveat": "fixture",
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return jsonl_path, summary_path


def _direct_money_totals(conn, person_id: int) -> dict:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT
                count(*) AS event_count,
                count(*) FILTER (WHERE event_family = 'money') AS money_event_count,
                count(*) FILTER (WHERE event_family = 'benefit') AS benefit_event_count,
                count(*) FILTER (WHERE event_family = 'campaign_support')
                    AS campaign_support_event_count,
                sum(amount) FILTER (
                    WHERE amount_status = 'reported'
                      AND event_family <> 'campaign_support'
                ) AS reported_amount_total
            FROM influence_event
            WHERE recipient_person_id = %s
              AND review_status <> 'rejected'
            """,
            (person_id,),
        )
        return cur.fetchone()


# ---------- The integration tests ----------


def test_associatedentity_state_branch_creates_reviewed_link(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        alp_party_id = _seed_canonical_alp_party(conn)
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70001",
                    "ClientName": "Fixture ACT Holdings Pty Ltd",
                    "AssociatedParties": "Australian Labor Party (ACT Branch); ",
                }
            ],
            timestamp="20260430T160000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    assert result["observations_upserted"] == 1
    assert result["entities_upserted"] == 1
    assert result["reviewed_party_entity_links_upserted"] == 1
    assert result["resolver_status_counts"]["resolved_branch"] == 1

    with connect(integration_db.url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT pel.party_id, pel.method, pel.confidence, pel.review_status,
                       pel.reviewer, pel.evidence_note, pel.metadata
                FROM party_entity_link pel
                JOIN entity ON entity.id = pel.entity_id
                WHERE entity.canonical_name = 'Fixture ACT Holdings Pty Ltd'
                """
            )
            rows = cur.fetchall()
    assert len(rows) == 1
    link = rows[0]
    assert link["party_id"] == alp_party_id
    assert link["method"] == "official"
    assert link["confidence"] == "exact_identifier"
    assert link["review_status"] == "reviewed"
    assert link["reviewer"] == SYSTEM_REVIEWER
    assert "Australian Labor Party (ACT Branch)" in link["evidence_note"]
    assert "not proof of personal receipt" in link["evidence_note"]
    metadata = link["metadata"]
    assert metadata["matched_via_rule_id"] == (
        "alp_state_or_territory_branch_to_alp_parent_v1"
    )
    assert metadata["resolver_status"] == "resolved_branch"
    assert metadata["aec_register_client_identifier"] == "70001"


def test_individual_segment_does_not_create_link(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70002",
                    "ClientName": "Fixture Independent Campaigner Pty Ltd",
                    "AssociatedParties": "Allegra Spender;",
                }
            ],
            timestamp="20260430T011000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    assert result["reviewed_party_entity_links_upserted"] == 0
    assert result["individual_segments_skipped"] == 1
    assert result["observations_upserted"] == 1

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM party_entity_link pel
                JOIN entity ON entity.id = pel.entity_id
                WHERE entity.canonical_name = 'Fixture Independent Campaigner Pty Ltd'
                """
            )
            assert cur.fetchone()[0] == 0


def test_significantthirdparty_with_associated_parties_does_not_link(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "significantthirdparty",
            [
                {
                    "ClientIdentifier": "70003",
                    "ClientName": "Fixture Big Donor Trust",
                    "AssociatedParties": "Australian Labor Party (NSW Branch); ",
                }
            ],
            timestamp="20260430T012000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="significantthirdparty",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    # significantthirdparty rows must NEVER auto-create a party_entity_link
    # even when AssociatedParties is populated.
    assert result["reviewed_party_entity_links_upserted"] == 0
    assert result["observations_upserted"] == 1

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM party_entity_link pel
                JOIN entity ON entity.id = pel.entity_id
                WHERE entity.canonical_name = 'Fixture Big Donor Trust'
                """
            )
            assert cur.fetchone()[0] == 0


def test_thirdparty_does_not_link_or_create_party(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        # Capture initial party-table identity to ensure we don't add new
        # party rows from thirdparty ingestion.
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM party")
            party_count_before = cur.fetchone()[0]
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "thirdparty",
            [
                {
                    "ClientIdentifier": "70004",
                    "ClientName": "Fixture 100% Renewable Coalition",
                    "AssociatedParties": None,
                }
            ],
            timestamp="20260430T013000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="thirdparty",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    assert result["reviewed_party_entity_links_upserted"] == 0
    assert result["observations_upserted"] == 1

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM party")
            party_count_after = cur.fetchone()[0]
    assert party_count_after == party_count_before


def test_politicalparty_unknown_to_local_does_not_create_party_row(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM party")
            party_count_before = cur.fetchone()[0]
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "politicalparty",
            [
                {
                    "ClientIdentifier": "70005",
                    "ClientName": "Fixture New Federalist Party",
                }
            ],
            timestamp="20260430T014000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="politicalparty",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    assert result["reviewed_party_entity_links_upserted"] == 0
    assert result["observations_upserted"] == 1

    with connect(integration_db.url) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(*) FROM party")
            party_count_after = cur.fetchone()["count"]
            cur.execute(
                """
                SELECT resolver_status
                FROM aec_register_of_entities_observation
                WHERE client_identifier = '70005'
                """
            )
            observation = cur.fetchone()
    assert party_count_after == party_count_before, (
        "politicalparty register row must not auto-create a canonical party.id"
    )
    assert observation["resolver_status"] == "unresolved_no_match"


def test_loader_is_idempotent(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70006",
                    "ClientName": "Fixture Idempotent Holdings Pty Ltd",
                    "AssociatedParties": "Australian Labor Party (ACT Branch); ",
                }
            ],
            timestamp="20260430T015000Z",
        )
        first = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
        second = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
    assert first["reviewed_party_entity_links_upserted"] == 1
    # Second invocation does NOT add a duplicate link (idempotent on
    # (party_id, entity_id, link_type)).
    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM party_entity_link pel
                JOIN entity ON entity.id = pel.entity_id
                WHERE entity.canonical_name = 'Fixture Idempotent Holdings Pty Ltd'
                """
            )
            assert cur.fetchone()[0] == 1
    # The observation row remains a single fingerprinted row across reloads.
    assert second["observations_upserted"] == 1


def test_loader_does_not_change_direct_representative_money_totals(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Cross-cut invariant per the dev's standing rule: loaders that create
    party/entity links MUST NOT change direct-representative money totals."""
    with connect(integration_db.url) as conn:
        _seed_canonical_alp_party(conn)
        # Seed a baseline direct money event for the fixture rep.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM source_document WHERE source_id = 'pytest-source'"
            )
            source_document_id = cur.fetchone()[0]
            cur.execute("SELECT id FROM jurisdiction WHERE code = 'CWLTH'")
            jurisdiction_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type, source_entity_id,
                    source_raw_name, recipient_person_id, recipient_raw_name,
                    jurisdiction_id, amount, amount_status, event_date, chamber,
                    disclosure_system, evidence_status, extraction_method,
                    review_status, description, source_document_id, source_ref,
                    missing_data_flags, metadata
                )
                VALUES (
                    'influence:fixture-direct-money-baseline',
                    'money', 'donation', %s, 'Fixture Donor', %s, 'Jane Citizen',
                    %s, 4242.42, 'reported', '2025-05-01', 'house',
                    'pytest fixture', 'official_record_parsed', 'fixture_seed',
                    'not_required', 'Fixture direct money baseline.',
                    %s, 'fixture-baseline-row', '[]'::jsonb, %s
                )
                """,
                (
                    integration_db.entity_id,
                    integration_db.person_id,
                    jurisdiction_id,
                    source_document_id,
                    Jsonb({"fixture": True}),
                ),
            )
        conn.commit()
        before = _direct_money_totals(conn, integration_db.person_id)

        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70007",
                    "ClientName": "Fixture Cross-Cut Holdings Pty Ltd",
                    "AssociatedParties": "Australian Labor Party (Tasmanian Branch); ",
                }
            ],
            timestamp="20260430T020000Z",
        )
        load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
        after = _direct_money_totals(conn, integration_db.person_id)

    assert after == before, (
        "AEC Register loader changed direct-representative money totals; "
        "this would silently leak party-mediated context into direct receipts."
    )


def _seed_qld_alp_party(conn) -> int:
    """Add a second `Australian Labor Party` row in the QLD state
    jurisdiction. Returns the new id.

    This mirrors the live local DB state where state-level QLD ECQ
    ingestion legitimately creates a separate ALP row in the state
    jurisdiction. The federal-jurisdiction Commonwealth row from
    `_seed_canonical_alp_party` continues to coexist.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM jurisdiction
            WHERE level = 'state' AND (code = 'QLD' OR LOWER(name) = 'queensland')
            """
        )
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO jurisdiction (name, level, code)
                VALUES ('Queensland', 'state', 'QLD')
                RETURNING id
                """
            )
            jurisdiction_id = int(cur.fetchone()[0])
        else:
            jurisdiction_id = int(row[0])
        cur.execute(
            """
            SELECT id FROM party
            WHERE name = 'Australian Labor Party'
              AND jurisdiction_id = %s
            """,
            (jurisdiction_id,),
        )
        existing = cur.fetchone()
        if existing:
            return int(existing[0])
        cur.execute(
            """
            INSERT INTO party (name, short_name, jurisdiction_id)
            VALUES ('Australian Labor Party', 'ALP', %s)
            RETURNING id
            """,
            (jurisdiction_id,),
        )
        return int(cur.fetchone()[0])


def test_personality_vehicle_party_row_surfaces_flag_in_api(
    integration_db: IntegrationDatabase,  # noqa: F811
) -> None:
    """Regression guard for the candidate-vehicle / personality-
    registered-name party seed (migration 037), updated in Batch H to
    use the now-wired API flag.

    Migration 037 adds federal canonical `party` rows for personality
    vehicles ("Dai Le & Frank Carbone W.S.C.", "Kim for Canberra",
    "Tammy Tyrrell for Tasmania", and "votefusion.org for big ideas")
    with explicit `metadata->>'is_personality_vehicle'` and
    `metadata->>'affiliated_person_hint'` keys.

    Batch H wired both keys through
    `_representative_party_exposure_summary` so a future loader
    legitimately linking an MP's `office_term` to a personality-vehicle
    row no longer renders that party as if it were ideological. This
    test now asserts the wiring: when an office_term references a
    personality-vehicle party, the API surfaces the flag so the
    frontend can render a distinct chip.
    """
    from au_politics_money.api.queries import (
        _representative_party_exposure_summary,
    )

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            # Seed a personality-vehicle party row + an office_term that
            # references it, so the API surface is exercised end-to-end.
            cur.execute(
                "SELECT id FROM jurisdiction WHERE code = 'CWLTH'"
            )
            cwlth_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO party (name, short_name, jurisdiction_id, metadata)
                VALUES (
                    'Pytest Personality Vehicle Party',
                    'PYTEST-PV',
                    %s,
                    jsonb_build_object(
                        'seed_source',
                        'schema/037_seed_candidate_vehicle_party_rows.sql',
                        'is_personality_vehicle', true,
                        'affiliated_person_hint', 'Pytest McTestface'
                    )
                )
                RETURNING id
                """,
                (cwlth_id,),
            )
            personality_party_id = int(cur.fetchone()[0])

            # Seed a separate non-personality party row so the API
            # surface clearly differentiates the two cases.
            cur.execute(
                """
                INSERT INTO party (name, short_name, jurisdiction_id, metadata)
                VALUES (
                    'Pytest Ideological Party',
                    'PYTEST-IP',
                    %s,
                    jsonb_build_object(
                        'seed_source', 'pytest_inline_ideological',
                        'is_personality_vehicle', false
                    )
                )
                RETURNING id
                """,
                (cwlth_id,),
            )
            int(cur.fetchone()[0])  # ideological control row, not asserted on directly

            # Re-point the existing fixture office_term at the
            # personality-vehicle party so the API surface returns it.
            cur.execute(
                "UPDATE office_term SET party_id = %s WHERE person_id = %s",
                (personality_party_id, integration_db.person_id),
            )
            conn.commit()

            # We need at least one reviewed party_entity_link + one
            # influence_event so `_representative_party_exposure_summary`
            # returns the row (it filters out parties with no events).
            # The integration_db fixture already seeded a baseline event
            # — we just need a party_entity_link to that event's entity.
            cur.execute(
                """
                INSERT INTO party_entity_link (
                    party_id, entity_id, link_type, method, confidence,
                    review_status, reviewer, reviewed_at,
                    evidence_note, metadata
                )
                VALUES (
                    %s, %s, 'exact_party_entity', 'official',
                    'exact_identifier', 'reviewed',
                    'pytest:personality_vehicle_test', now(),
                    'Pytest fixture link', '{}'::jsonb
                )
                ON CONFLICT (party_id, entity_id, link_type) DO NOTHING
                """,
                (personality_party_id, integration_db.entity_id),
            )

            # `_party_reviewed_money_summary` joins on
            # `influence_event.recipient_entity_id` — the integration
            # fixture's existing event uses the entity on the SOURCE
            # side, so add a recipient-side event so the summary surface
            # has something to roll up.
            cur.execute(
                "SELECT id FROM jurisdiction WHERE code = 'CWLTH'"
            )
            cwlth_id = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT id FROM source_document
                WHERE source_id = 'pytest-source' LIMIT 1
                """
            )
            source_document_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type,
                    recipient_entity_id, recipient_raw_name,
                    jurisdiction_id, amount, amount_status, event_date,
                    chamber, disclosure_system, evidence_status,
                    extraction_method, review_status,
                    description, source_document_id, source_ref,
                    missing_data_flags, metadata
                )
                VALUES (
                    'pytest:personality-vehicle:recipient-event',
                    'money', 'donation_or_gift',
                    %s, 'Pytest Personality Vehicle Party',
                    %s, 4242.42, 'reported', '2026-04-01', 'house',
                    'pytest fixture', 'official_record_parsed',
                    'fixture_seed', 'not_required',
                    'Pytest fixture event with party as recipient.',
                    %s, 'pytest-pv-recipient', '[]'::jsonb, '{}'::jsonb
                )
                """,
                (integration_db.entity_id, cwlth_id, source_document_id),
            )
            conn.commit()

        summary = _representative_party_exposure_summary(
            conn, person_id=integration_db.person_id
        )

    assert summary, (
        "_representative_party_exposure_summary returned no rows for the "
        "personality-vehicle party; the API surface is not picking up "
        "the seeded row even though an office_term references it."
    )
    pv_rows = [
        row for row in summary if int(row.get("party_id") or 0) == personality_party_id
    ]
    assert pv_rows, (
        f"Personality-vehicle party id {personality_party_id} is "
        "missing from the API response."
    )
    pv = pv_rows[0]
    assert pv.get("is_personality_vehicle") is True, (
        "API response is missing or has the wrong value for "
        "is_personality_vehicle on a personality-vehicle row. "
        f"Got: {pv.get('is_personality_vehicle')!r}. Without this flag "
        "the frontend cannot distinguish a personal electoral vehicle "
        "from an ideological party."
    )
    assert pv.get("affiliated_person_hint") == "Pytest McTestface", (
        "API response is missing or has the wrong "
        "affiliated_person_hint. Frontend chip text relies on this."
    )


def test_federal_party_exposure_does_not_include_state_jurisdiction_rows(
    integration_db: IntegrationDatabase,  # noqa: F811
) -> None:
    """Sub-national rollout regression guard (Batch R PR 3).

    The `_representative_party_exposure_summary` query is anchored on
    `office_term.party_id`. For a federal MP, `office_term.party_id`
    points at a FEDERAL canonical party row; the function MUST NOT
    return any state-jurisdiction party rows on the federal MP's
    profile, regardless of any state-jurisdiction party_entity_link
    rows that may have been emitted by the dual-call resolver loader.

    This test seeds:
      * A federal canonical ALP row + an office_term linking the MP to
        it (federal exposure surface).
      * A QLD-jurisdiction ALP row + a party_entity_link from that
        QLD row to the same entity the federal row also links to. (As
        the dual-call resolver would emit.)
      * A recipient-side influence_event tied to that entity.

    Then asserts that the API surface for the federal MP returns the
    federal row and does NOT return the QLD row.

    The new `party_jurisdiction_code` field on each row MUST equal
    'CWLTH' for the federal row.
    """
    from au_politics_money.api.queries import (
        _representative_party_exposure_summary,
    )

    with connect(integration_db.url) as conn:
        federal_alp_id = _seed_canonical_alp_party(conn)
        qld_alp_id = _seed_qld_alp_party(conn)
        with conn.cursor() as cur:
            # Re-point the integration fixture's office_term at the
            # FEDERAL ALP so the surface returns it.
            cur.execute(
                "UPDATE office_term SET party_id = %s WHERE person_id = %s",
                (federal_alp_id, integration_db.person_id),
            )
            # Add party_entity_link rows for BOTH federal AND QLD ALP
            # parties pointing at the same entity (as the dual-call
            # resolver would emit).
            for party_id in (federal_alp_id, qld_alp_id):
                cur.execute(
                    """
                    INSERT INTO party_entity_link (
                        party_id, entity_id, link_type, method, confidence,
                        review_status, reviewer, reviewed_at,
                        evidence_note, metadata
                    )
                    VALUES (
                        %s, %s, 'exact_party_entity', 'official',
                        'exact_identifier', 'reviewed',
                        'pytest:state-rollout-regression', now(),
                        'Pytest dual-call simulation', '{}'::jsonb
                    )
                    ON CONFLICT (party_id, entity_id, link_type) DO NOTHING
                    """,
                    (party_id, integration_db.entity_id),
                )

            # Add a recipient-side event so
            # `_party_reviewed_money_summary` returns a non-empty roll-up
            # for both party rows.
            cur.execute(
                "SELECT id FROM jurisdiction WHERE code = 'CWLTH'"
            )
            cwlth_id = int(cur.fetchone()[0])
            cur.execute(
                "SELECT id FROM source_document WHERE source_id = 'pytest-source' LIMIT 1"
            )
            source_document_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO influence_event (
                    external_key, event_family, event_type,
                    recipient_entity_id, recipient_raw_name,
                    jurisdiction_id, amount, amount_status, event_date,
                    chamber, disclosure_system, evidence_status,
                    extraction_method, review_status,
                    description, source_document_id, source_ref,
                    missing_data_flags, metadata
                )
                VALUES (
                    'pytest:state-rollout:recipient-event',
                    'money', 'donation_or_gift',
                    %s, 'Australian Labor Party',
                    %s, 4242.42, 'reported', '2026-04-15', 'house',
                    'pytest fixture', 'official_record_parsed',
                    'fixture_seed', 'not_required',
                    'Pytest fixture event with party-linked entity as recipient.',
                    %s, 'pytest-state-rollout', '[]'::jsonb, '{}'::jsonb
                )
                """,
                (integration_db.entity_id, cwlth_id, source_document_id),
            )
            conn.commit()

        summary = _representative_party_exposure_summary(
            conn, person_id=integration_db.person_id
        )

    surfaced_party_ids = {int(row["party_id"]) for row in summary}
    assert federal_alp_id in surfaced_party_ids, (
        "Federal MP's profile should surface the federal canonical ALP "
        "row via office_term."
    )
    assert qld_alp_id not in surfaced_party_ids, (
        "Federal MP's profile MUST NOT include the QLD-jurisdiction ALP "
        "row, even though a party_entity_link to that entity exists. "
        "This is the load-bearing 'no cross-jurisdiction conflation' "
        "guarantee for the sub-national rollout."
    )

    # The new party_jurisdiction_code field must reach the API response.
    federal_row = next(
        row for row in summary if int(row["party_id"]) == federal_alp_id
    )
    assert federal_row["party_jurisdiction_code"] == "CWLTH", (
        f"Federal ALP row should have party_jurisdiction_code='CWLTH'; "
        f"got {federal_row['party_jurisdiction_code']!r}"
    )
    assert federal_row["party_jurisdiction_level"] == "federal", (
        f"Federal ALP row should have party_jurisdiction_level='federal'; "
        f"got {federal_row['party_jurisdiction_level']!r}"
    )


def test_get_or_create_party_preserves_curated_short_name_post_dedup(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Regression test for the federal-jurisdiction party-row consolidation
    introduced in migration `034_consolidate_federal_party_duplicates`.

    Post-migration, the canonical ALP row has `name='Australian Labor
    Party'` and `short_name='ALP'`. The federal roster / TVFY ingestors
    call `get_or_create_party('Australian Labor Party', cwlth_id)` on
    every run, which must NOT clobber the curated `short_name`. Without
    the COALESCE guard on the ON CONFLICT clause, the long-form name
    would silently overwrite the short-form code on every pipeline run,
    breaking every consumer that filters by `short_name='ALP'`.
    """
    from au_politics_money.db.load import get_or_create_party

    with connect(integration_db.url) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM jurisdiction WHERE code = 'CWLTH'"
            )
            cwlth_id = int(cur.fetchone()[0])
            cur.execute(
                """
                INSERT INTO party (name, short_name, jurisdiction_id)
                VALUES ('Curated Test Party Long Name', 'CTPLN', %s)
                ON CONFLICT (name, jurisdiction_id) DO UPDATE SET
                    short_name = EXCLUDED.short_name
                RETURNING id
                """,
                (cwlth_id,),
            )
            curated_id = int(cur.fetchone()[0])
            conn.commit()

            # Simulate the pipeline running again with only the long-form
            # name available, exactly as the federal roster ingestor does.
            same_id = get_or_create_party(
                conn, "Curated Test Party Long Name", cwlth_id
            )
            assert same_id == curated_id, (
                "get_or_create_party must hit the existing row by "
                "(name, jurisdiction_id), not insert a new one."
            )
            conn.commit()

            cur.execute(
                "SELECT short_name FROM party WHERE id = %s",
                (curated_id,),
            )
            short_name_after = cur.fetchone()[0]

    assert short_name_after == "CTPLN", (
        "get_or_create_party clobbered the curated short_name "
        f"({short_name_after!r}); the COALESCE guard on the ON CONFLICT "
        "clause is missing or broken. Without it, every pipeline run "
        "would silently break short_name-driven UI filters."
    )


def test_source_jurisdiction_disambiguates_federal_vs_state_alp_rows(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    """End-to-end check that the loader's source-jurisdiction
    disambiguation correctly picks the federal-jurisdiction ALP row when
    both a federal-jurisdiction and a state-jurisdiction
    `Australian Labor Party` row exist with the same canonical name.
    Mirrors the live local DB state where QLD ECQ ingestion creates a
    parallel state-jurisdiction ALP row.
    """
    with connect(integration_db.url) as conn:
        federal_alp_id = _seed_canonical_alp_party(conn)
        qld_alp_id = _seed_qld_alp_party(conn)
        assert federal_alp_id != qld_alp_id, (
            "Test must seed two distinct ALP rows in different jurisdictions"
        )
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70042",
                    "ClientName": "Fixture Disambiguation Holdings Pty Ltd",
                    "AssociatedParties": "Australian Labor Party (NSW Branch); ",
                }
            ],
            timestamp="20260430T030000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT party_id, review_status, method, reviewer
                FROM party_entity_link
                WHERE reviewer = %s
                  AND review_status = 'reviewed'
                  AND method = 'official'
                """,
                (SYSTEM_REVIEWER,),
            )
            links = cur.fetchall()

    assert result["reviewed_party_entity_links_upserted"] >= 1, (
        "Loader should have created at least one reviewed link via the "
        "federal-jurisdiction ALP row."
    )
    assert links, "No reviewed links were created"
    federal_link_party_ids = {link[0] for link in links}
    # The federal canonical ALP must be present.
    assert federal_alp_id in federal_link_party_ids, (
        f"Reviewed links must include the federal-jurisdiction ALP row "
        f"(id={federal_alp_id}); got {federal_link_party_ids}"
    )
    # As of the state-rollout dual-call, the QLD-jurisdiction row may
    # also be linked when the segment carries a state-branch suffix.
    # The "(NSW Branch)" segment in this fixture is detected as NSW, so
    # NO QLD link is expected — only the federal one. (Assert this
    # explicitly to guard against false-positive cross-jurisdiction
    # fan-out.)
    assert qld_alp_id not in federal_link_party_ids, (
        f"NSW-branch segment should NOT produce a link to the QLD-"
        f"jurisdiction ALP row (id={qld_alp_id}); got {federal_link_party_ids}"
    )


def test_qld_state_branch_emits_dual_links_to_federal_and_state_alp(
    integration_db: IntegrationDatabase,  # noqa: F811
    tmp_path: Path,
) -> None:
    """Dual-call regression guard for the sub-national rollout (Batch R).

    When a register-row segment names "Australian Labor Party (State of
    Queensland)", the loader's dual-call resolver must emit TWO
    reviewed `party_entity_link` rows:
      1. One to the federal canonical ALP row (existing behaviour).
      2. One to the QLD-jurisdiction ALP row (new behaviour).

    The federal link is the unchanged pre-rollout output; the QLD link
    is the new state-side fan-out. Both are reviewed/official links
    pointing at the SAME entity, just with different `party_id`s.

    The unique-constraint on `party_entity_link` is
    `(party_id, entity_id, link_type)`, so the two rows coexist
    cleanly. The result counters distinguish them via
    `reviewed_party_entity_links_upserted` (federal) and
    `state_party_entity_links_upserted` (state).

    Crucially this DOES NOT change direct-money totals — that
    invariant is guarded by
    test_loader_does_not_change_direct_representative_money_totals
    elsewhere in this file.
    """
    with connect(integration_db.url) as conn:
        federal_alp_id = _seed_canonical_alp_party(conn)
        qld_alp_id = _seed_qld_alp_party(conn)
        assert federal_alp_id != qld_alp_id, (
            "Test must seed two distinct ALP rows in different jurisdictions"
        )
        conn.commit()
        jsonl_path, summary_path = _write_artefacts(
            tmp_path,
            "associatedentity",
            [
                {
                    "ClientIdentifier": "70043",
                    "ClientName": "Fixture QLD Dual Link Holdings Pty Ltd",
                    "AssociatedParties": "Australian Labor Party (State of Queensland); ",
                }
            ],
            timestamp="20260501T000000Z",
        )
        result = load_aec_register_of_entities(
            conn,
            client_type="associatedentity",
            jsonl_path=jsonl_path,
            summary_path=summary_path,
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT party_id
                FROM party_entity_link
                WHERE reviewer = %s
                  AND review_status = 'reviewed'
                  AND method = 'official'
                  AND metadata->>'aec_register_client_identifier' = '70043'
                """,
                (SYSTEM_REVIEWER,),
            )
            party_ids = {int(row[0]) for row in cur.fetchall()}

    # The federal canonical ALP link must exist (pre-rollout invariant).
    assert federal_alp_id in party_ids, (
        f"Expected federal canonical ALP row (id={federal_alp_id}) in the "
        f"reviewed party_entity_link rows for this entity; got {party_ids}"
    )
    # The QLD-jurisdiction ALP link must also exist (state-rollout fan-out).
    assert qld_alp_id in party_ids, (
        f"Expected QLD-jurisdiction ALP row (id={qld_alp_id}) in the "
        f"reviewed party_entity_link rows; the dual-call resolver did not "
        f"fan out the state-side link. Got {party_ids}"
    )
    # Result counters must reflect the two separate fan-outs.
    assert result["reviewed_party_entity_links_upserted"] >= 1, (
        "Federal-side link counter not incremented"
    )
    assert result["state_party_entity_links_upserted"] >= 1, (
        "State-side link counter not incremented; the dual-call did not "
        "emit a state link as expected."
    )
