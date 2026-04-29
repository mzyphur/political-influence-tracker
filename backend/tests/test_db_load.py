from datetime import date
import json

import pytest

from au_politics_money.db import load as load_module
from au_politics_money.db.load import (
    MAX_COASTLINE_REPAIR_BUFFER_METERS,
    _can_create_house_interest_person,
    _senate_interest_extraction_confidence,
    apply_schema,
    classify_interest_event,
    classify_money_event_type,
    is_direct_representative_return_type,
    load_official_aph_divisions,
    load_official_parliamentary_decision_record_documents,
    load_official_parliamentary_decision_records,
    load_electorate_boundary_display_geometries,
    load_processed_artifacts,
    missing_interest_flags,
    normalize_electorate_name,
    normalize_name,
    normalize_representative_return_name,
    parse_aec_money_flow_date,
    parse_date,
    parse_datetime,
    parse_financial_year_bounds,
    senate_api_name_to_canonical,
)


class RecordingCursor:
    def __init__(self) -> None:
        self.executed_sql = ""

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str) -> None:
        self.executed_sql = sql


class RecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = RecordingCursor()
        self.committed = False

    def cursor(self) -> RecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


def test_normalize_name_is_stable_for_entity_matching() -> None:
    assert normalize_name("Example Pty. Ltd.") == "example pty ltd"
    assert normalize_name("  A.B.C.  Holdings  ") == "a b c holdings"


def test_normalize_representative_return_name_strips_titles_and_postnominals() -> None:
    assert normalize_representative_return_name("Ms Zali Steggall OAM MP") == "zali steggall"
    assert normalize_representative_return_name("Hon Andrew Hastie MP") == "andrew hastie"
    assert normalize_representative_return_name("Senator Penny Allman-Payne") == "penny allman payne"
    assert is_direct_representative_return_type("Member of HOR Return")
    assert is_direct_representative_return_type("Senator Return")
    assert not is_direct_representative_return_type("Political Party Return")


def test_parse_date_accepts_aec_common_formats() -> None:
    assert parse_date("31/12/2025") == date(2025, 12, 31)
    assert parse_date("2025-12-31") == date(2025, 12, 31)
    assert parse_date("8/14/2025 1:31:50 PM") == date(2025, 8, 14)
    assert parse_date("") is None
    assert parse_date("not supplied") is None


def test_parse_aec_money_flow_date_validates_financial_year_bounds() -> None:
    assert parse_financial_year_bounds("2015-16") == (date(2015, 7, 1), date(2016, 6, 30))

    parsed, validation = parse_aec_money_flow_date("14/04/2016", "2015-16")
    assert parsed == date(2016, 4, 14)
    assert validation["status"] == "accepted"

    parsed, validation = parse_aec_money_flow_date("14/04/2106", "2015-16")
    assert parsed is None
    assert validation["status"] == "outside_financial_year"
    assert validation["parsed_date"] == "2106-04-14"


def test_senate_api_name_to_canonical() -> None:
    assert senate_api_name_to_canonical("Allman-Payne, Penny") == "Penny Allman-Payne"
    assert senate_api_name_to_canonical("Alex Antic") == "Alex Antic"


def test_senate_interest_subject_provider_requires_review_gate() -> None:
    assert (
        _senate_interest_extraction_confidence(
            {"counterparty_extraction": {"method": "subject_provider_verb:provided"}}
        )
        == "official_api_structured_provider_heuristic"
    )
    assert (
        _senate_interest_extraction_confidence(
            {"counterparty_extraction": {"method": "explicit_provider_phrase:provided by"}}
        )
        == "official_api_structured"
    )


def test_normalize_electorate_name_strips_ocr_old_suffix() -> None:
    assert normalize_electorate_name("KENNEDY OLD") == "kennedy"
    assert normalize_electorate_name("Farrer") == "farrer"


def test_house_interest_person_fallback_requires_real_electorate() -> None:
    assert _can_create_house_interest_person(
        {
            "member_name": "Sussan Ley",
            "given_names": "Sussan",
            "family_name": "Ley",
            "electorate": "Farrer",
            "state": "New South Wales",
        }
    )
    assert not _can_create_house_interest_person(
        {
            "member_name": "= ANTHONY ALBANESE |",
            "given_names": "= ANTHONY",
            "family_name": "ALBANESE |",
            "electorate": "I",
            "state": "NSW",
        }
    )


def test_apply_schema_loads_backend_schema() -> None:
    conn = RecordingConnection()

    apply_schema(conn)

    assert "CREATE TABLE source_document" in conn.cursor_instance.executed_sql
    assert "CREATE TABLE influence_event" in conn.cursor_instance.executed_sql
    assert "CREATE TABLE official_parliamentary_decision_record" in conn.cursor_instance.executed_sql
    assert "CREATE TABLE official_parliamentary_decision_record_document" in conn.cursor_instance.executed_sql
    assert "CREATE TABLE sector_policy_topic_link" in conn.cursor_instance.executed_sql
    assert "'sector_policy_topic_link'" in conn.cursor_instance.executed_sql
    assert "CREATE OR REPLACE VIEW person_policy_vote_summary" in conn.cursor_instance.executed_sql
    assert conn.committed is True


def test_default_load_refreshes_official_identifiers_before_influence_events(monkeypatch) -> None:
    calls: list[str] = []

    class ContextConnection:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(load_module, "connect", lambda database_url=None: ContextConnection())
    monkeypatch.setattr(
        load_module,
        "load_official_identifiers",
        lambda conn: calls.append("official_identifiers") or {"official_identifier_records": 1},
    )
    monkeypatch.setattr(
        load_module,
        "load_influence_events",
        lambda conn: calls.append("influence_events") or {"events": 1},
    )

    summary = load_processed_artifacts(
        include_roster=False,
        include_money_flows=False,
        include_qld_ecq=False,
        include_house_interests=False,
        include_senate_interests=False,
        include_electorate_boundaries=False,
        include_influence_events=True,
        include_entity_classifications=False,
        include_official_identifiers=True,
        include_official_decision_records=False,
        include_official_decision_record_documents=False,
        include_official_aph_divisions=False,
        include_vote_divisions=False,
        include_postcode_crosswalk=False,
        include_party_entity_links=False,
        reapply_reviews=False,
    )

    assert calls == ["official_identifiers", "influence_events"]
    assert list(summary) == ["schema_applied", "official_identifiers", "influence_events"]


def test_display_geometry_repair_buffer_validates_range() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        load_electorate_boundary_display_geometries(
            object(),
            coastline_repair_buffer_meters=-1,
        )

    with pytest.raises(ValueError, match="no greater than"):
        load_electorate_boundary_display_geometries(
            object(),
            coastline_repair_buffer_meters=MAX_COASTLINE_REPAIR_BUFFER_METERS + 1,
        )


def test_money_event_classifier_keeps_donations_visible() -> None:
    assert classify_money_event_type("gift", "receipts") == "donation_or_gift"
    assert classify_money_event_type("election_media_advertising_expenditure", "") == (
        "campaign_expenditure"
    )
    assert classify_money_event_type("", "Discretionary Benefit") == "discretionary_benefit"
    assert classify_money_event_type("loan", "") == "loan"
    assert classify_money_event_type("", "") == "money_flow"


def test_interest_event_classifier_tracks_small_benefit_forms() -> None:
    assert classify_interest_event(
        "Sponsored travel or hospitality",
        "Qatar Airways upgrade to business class",
    ) == ("benefit", "sponsored_travel_or_hospitality", "private_aircraft_or_flight")
    assert classify_interest_event(
        "Sponsored travel or hospitality",
        "Private jet flight from Sydney to Canberra provided by Example Pty Ltd",
    ) == ("benefit", "sponsored_travel_or_hospitality", "private_aircraft_or_flight")
    assert classify_interest_event(
        "Sponsored travel or hospitality",
        "Detail Of Travel Hospitality: Lounge memberships for Qantas and Virgin Australia",
    ) == ("benefit", "sponsored_travel_or_hospitality", "membership_or_lounge_access")
    assert classify_interest_event(
        "Gifts",
        "AFL Grand Final tickets at invitation of Commonwealth Bank",
    ) == ("benefit", "gift", "event_ticket_or_pass")
    assert classify_interest_event(
        "Other interests",
        "Bangarra Tickets x 5 provided by Arts & Culture Trust WA",
    ) == ("benefit", "other_declared_benefit", "event_ticket_or_pass")
    assert classify_interest_event(
        "Other interests",
        "Associate member Queensland Teachers Union",
    ) == ("organisational_role", "membership", None)
    assert classify_interest_event(
        "Other interests",
        "Member Chairman's Lounge Qantas",
    ) == ("benefit", "other_declared_benefit", "membership_or_lounge_access")
    assert classify_interest_event("Shareholdings", "BHP Group") == (
        "private_interest",
        "shareholding",
        None,
    )


def test_interest_missing_flags_document_disclosure_gaps() -> None:
    flags = missing_interest_flags(
        source_raw_name="",
        amount=None,
        date_received=None,
        date_reported=None,
        extraction_method="pdf_section_line_heuristic",
    )

    assert "provider_not_disclosed_or_not_extracted" in flags
    assert "value_not_disclosed" in flags
    assert "event_date_not_disclosed" in flags
    assert "reported_date_not_disclosed" in flags
    assert "parsed_from_pdf_heuristic" in flags


def test_parse_datetime_accepts_raw_fetch_timestamp_format() -> None:
    parsed = parse_datetime("20260427T000000Z")

    assert parsed is not None
    assert parsed.date() == date(2026, 4, 27)


class StatementRecordingCursor:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.executed_params: list[object] = []
        self.rowcount = 1

    def __enter__(self) -> "StatementRecordingCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params=None) -> "StatementRecordingCursor":
        self.executed_sql.append(sql)
        self.executed_params.append(params)
        return self

    def fetchone(self) -> tuple[int]:
        return (7,)


class StatementRecordingConnection:
    def __init__(self) -> None:
        self.cursor_instance = StatementRecordingCursor()
        self.committed = False

    def cursor(self) -> StatementRecordingCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


class MissingDecisionCursor(StatementRecordingCursor):
    def fetchone(self):
        return None


class MissingDecisionConnection(StatementRecordingConnection):
    def __init__(self) -> None:
        self.cursor_instance = MissingDecisionCursor()
        self.committed = False


def test_load_official_decision_record_index_upserts_rows(tmp_path) -> None:
    jsonl_path = tmp_path / "records.jsonl"
    jsonl_path.write_text(
        (
            '{"external_key":"aph_house_votes_and_proceedings:test",'
            '"source_id":"aph_house_votes_and_proceedings","chamber":"house",'
            '"record_type":"votes_and_proceedings","record_kind":"parlinfo_html",'
            '"parliament_label":"48th Parliament","year":"2026","month":"February",'
            '"day_label":"3","record_date":"2026-02-03",'
            '"title":"House Votes and Proceedings 2026-02-03","link_text":"3",'
            '"url":"https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p;'
            'query=Id%3A%22chamber/votes/test/0000%22",'
            '"evidence_status":"official_record_index",'
            '"parser_name":"aph_decision_record_index_v1","parser_version":"1",'
            '"schema_version":"aph_decision_record_index_v1","metadata":{}}\n'
        ),
        encoding="utf-8",
    )
    conn = StatementRecordingConnection()

    summary = load_official_parliamentary_decision_records(conn, [jsonl_path])

    assert summary["records_seen"] == 1
    assert summary["records_inserted_or_updated"] == 1
    assert summary["source_counts"] == {"aph_house_votes_and_proceedings": 1}
    assert conn.committed is True
    assert any(
        "INSERT INTO official_parliamentary_decision_record" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "UPDATE official_parliamentary_decision_record" in sql
        and "is_current = FALSE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "UPDATE official_parliamentary_decision_record_document document" in sql
        and "parent_not_in_latest_official_index" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "is_current = TRUE" in sql and "withdrawn_at = NULL" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "- 'source_record_status'" in sql and "- 'source_record_withdrawn_at'" in sql
        for sql in conn.cursor_instance.executed_sql
    )


def test_load_official_aph_divisions_marks_latest_snapshot_current(
    tmp_path,
    monkeypatch,
) -> None:
    jsonl_path = tmp_path / "official_divisions.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "external_id": "aph:house:2026-02-03:1",
                "chamber": "house",
                "division_date": "2026-02-03",
                "division_number": 1,
                "title": "Fixture Division",
                "aye_count": 1,
                "no_count": 0,
                "possible_turnout": 1,
                "source_metadata_path": str(tmp_path / "metadata.json"),
                "official_decision_record_external_key": "aph_house_votes_and_proceedings:test",
                "metadata": {"vote_count_matches": True},
                "votes": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "au_politics_money.db.load.upsert_source_document",
        lambda conn, path: 42,
    )
    monkeypatch.setattr(
        "au_politics_money.db.load._current_chamber_vote_person_index",
        lambda conn, chamber: {},
    )
    conn = StatementRecordingConnection()

    summary = load_official_aph_divisions(conn, jsonl_path)

    assert summary["divisions_seen"] == 1
    assert summary["votes_seen"] == 0
    assert summary["divisions_deactivated_before_reload"] == 1
    assert summary["official_vote_rows_deactivated_before_reload"] == 1
    assert conn.committed is True
    assert any(
        "UPDATE person_vote vote" in sql and "is_current = FALSE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "UPDATE vote_division" in sql and "is_current = FALSE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "INSERT INTO vote_division" in sql
        and "is_current" in sql
        and "withdrawn_at = NULL" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "JOIN official_parliamentary_decision_record_document document" in sql
        and "record.is_current IS TRUE" in sql
        and "document.is_current IS TRUE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "- 'source_record_status'" in sql and "- 'source_record_withdrawn_at'" in sql
        for sql in conn.cursor_instance.executed_sql
    )


def test_load_official_decision_record_documents_links_source_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "fetched_at": "20260427T000000Z",
                "sha256": "abc123",
            }
        ),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "status": "fetched",
                        "source_id": "aph_house_votes_and_proceedings__decision_record__test",
                        "decision_record_external_key": "aph_house_votes_and_proceedings:test",
                        "representation_kind": "parlinfo_html",
                        "representation_url": (
                            "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p"
                        ),
                        "official_decision_record": {
                            "external_key": "aph_house_votes_and_proceedings:test",
                            "source_id": "aph_house_votes_and_proceedings",
                            "source_name": "House Votes and Proceedings",
                            "chamber": "house",
                            "record_type": "votes_and_proceedings",
                            "record_date": "2026-02-03",
                            "title": "House Votes and Proceedings 2026-02-03",
                            "index_url": (
                                "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p"
                            ),
                        },
                        "official_decision_record_representation": {
                            "url": "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p",
                            "record_kind": "parlinfo_html",
                        },
                        "validation": {"validation": "html_signature"},
                        "metadata_path": str(metadata_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "au_politics_money.db.load.upsert_source_document",
        lambda conn, path: 42,
    )
    conn = StatementRecordingConnection()

    summary = load_official_parliamentary_decision_record_documents(conn, summary_path)

    assert summary["documents_seen"] == 1
    assert summary["documents_linked"] == 1
    assert summary["representation_counts"] == {"parlinfo_html": 1}
    assert conn.committed is True
    assert any(
        "SELECT id" in sql and "official_parliamentary_decision_record" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "WHERE external_key = %s" in sql and "is_current IS TRUE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "INSERT INTO official_parliamentary_decision_record_document" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert summary["documents_deactivated_before_reload"] == 1
    assert any(
        "UPDATE official_parliamentary_decision_record_document" in sql
        and "is_current = FALSE" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "is_current = TRUE" in sql and "withdrawn_at = NULL" in sql
        for sql in conn.cursor_instance.executed_sql
    )
    assert any(
        "- 'source_record_status'" in sql and "- 'source_record_withdrawn_at'" in sql
        for sql in conn.cursor_instance.executed_sql
    )


def test_load_official_decision_record_documents_skips_without_parent_before_source_upsert(
    tmp_path,
    monkeypatch,
) -> None:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps({"fetched_at": "20260427T000000Z", "sha256": "abc123"}),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "status": "fetched",
                        "source_id": "aph_house_votes_and_proceedings__decision_record__test",
                        "decision_record_external_key": "aph_house_votes_and_proceedings:test",
                        "representation_kind": "parlinfo_html",
                        "representation_url": (
                            "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p"
                        ),
                        "official_decision_record": {
                            "external_key": "aph_house_votes_and_proceedings:test",
                        },
                        "official_decision_record_representation": {
                            "url": "https://parlinfo.aph.gov.au/parlInfo/search/display/display.w3p",
                            "record_kind": "parlinfo_html",
                        },
                        "metadata_path": str(metadata_path),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    called = {"upsert_source_document": 0}

    def fake_upsert(conn, path):
        called["upsert_source_document"] += 1
        return 42

    monkeypatch.setattr("au_politics_money.db.load.upsert_source_document", fake_upsert)
    conn = MissingDecisionConnection()

    summary = load_official_parliamentary_decision_record_documents(conn, summary_path)

    assert summary["documents_seen"] == 1
    assert summary["documents_linked"] == 0
    assert summary["skipped_missing_decision_record"] == 1
    assert called["upsert_source_document"] == 0
