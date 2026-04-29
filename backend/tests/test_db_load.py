from datetime import date
import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.db import load as load_module
from au_politics_money.db.load import (
    MAX_COASTLINE_REPAIR_BUFFER_METERS,
    _can_create_house_interest_person,
    _senate_interest_extraction_confidence,
    act_annual_return_path_from_pipeline_manifest,
    act_gift_return_path_from_pipeline_manifest,
    apply_schema,
    classify_interest_event,
    classify_money_event_type,
    is_campaign_support_money_flow,
    is_direct_representative_return_type,
    is_public_funding_context_money_flow,
    is_state_source_receipt_context_money_flow,
    is_state_return_summary_money_flow,
    load_act_elections_from_pipeline_manifest,
    load_official_aph_divisions,
    load_official_parliamentary_decision_record_documents,
    load_official_parliamentary_decision_records,
    load_electorate_boundary_display_geometries,
    load_processed_artifacts,
    missing_interest_flags,
    normalize_electorate_name,
    normalize_name,
    normalize_representative_return_name,
    nt_ntec_annual_gifts_path_from_pipeline_manifest,
    nt_ntec_annual_returns_path_from_pipeline_manifest,
    nsw_aggregate_context_path_from_pipeline_manifest,
    parse_aec_money_flow_date,
    parse_date,
    parse_datetime,
    parse_financial_year_bounds,
    qld_ecq_eds_paths_from_pipeline_manifest,
    sa_ecsa_return_summary_path_from_pipeline_manifest,
    senate_api_name_to_canonical,
    tas_tec_donation_path_from_pipeline_manifest,
    vic_vec_funding_register_path_from_pipeline_manifest,
    waec_political_contribution_path_from_pipeline_manifest,
)
from au_politics_money.ingest.tas_tec import _declaration_source_id


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
        include_nsw_aggregates=False,
        reapply_reviews=False,
    )

    assert calls == ["official_identifiers", "influence_events"]
    assert list(summary) == ["schema_applied", "official_identifiers", "influence_events"]


def test_qld_pipeline_manifest_selects_exact_processed_artifacts(tmp_path) -> None:
    money_jsonl = tmp_path / "money.jsonl"
    participants_jsonl = tmp_path / "participants.jsonl"
    contexts_jsonl = tmp_path / "contexts.jsonl"
    qld_boundaries_geojson = tmp_path / "qld-state-boundaries.geojson"
    qld_members_jsonl = tmp_path / "qld-current-members.jsonl"
    money_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_map_export_csv"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_expenditure_export_csv"}) + "\n",
        encoding="utf-8",
    )
    participants_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_api_political_electors"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_political_parties"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_associated_entities"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_local_groups"}) + "\n",
        encoding="utf-8",
    )
    contexts_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_api_political_events"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_local_electorates"}) + "\n",
        encoding="utf-8",
    )
    qld_boundaries_geojson.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"division_name": "Algester"},
                        "geometry": None,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    qld_members_jsonl.write_text(
        json.dumps({"electorate": "Algester", "display_name": "Hon Leeanne Enoch"}) + "\n",
        encoding="utf-8",
    )

    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_raw_metadata(name: str, body_text: str) -> Path:
        body_path = tmp_path / f"{name}.body"
        body_path.write_text(body_text, encoding="utf-8")
        metadata_path = tmp_path / f"{name}.metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "body_path": str(body_path),
                    "sha256": sha256_path(body_path),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return metadata_path

    qld_boundary_metadata = write_raw_metadata("qld-boundary", '{"source": "boundary"}\n')
    qld_members_metadata = write_raw_metadata("qld-members", "member source\n")

    def write_summary(
        name: str,
        jsonl_path: Path,
        *,
        count_field: str,
        counts: dict[str, int],
    ) -> Path:
        summary_path = tmp_path / f"{name}.summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "normalizer_name": name,
                    "jsonl_path": str(jsonl_path),
                    "jsonl_sha256": sha256_path(jsonl_path),
                    "total_count": sum(counts.values()),
                    count_field: counts,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return summary_path

    def write_artifact_summary(
        name: str,
        *,
        parser_name: str,
        path_field: str,
        sha256_field: str,
        artifact_path: Path,
        source_id: str,
        count_field: str,
        count: int,
        names_field: str,
        names: list[str],
        raw_metadata_path: Path,
        extra: dict[str, str] | None = None,
    ) -> Path:
        raw_metadata = json.loads(raw_metadata_path.read_text(encoding="utf-8"))
        summary_path = tmp_path / f"{name}.summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    **(extra or {}),
                    count_field: count,
                    "parser_name": parser_name,
                    path_field: str(artifact_path),
                    sha256_field: sha256_path(artifact_path),
                    "source_id": source_id,
                    names_field: names,
                    "raw_metadata_path": str(raw_metadata_path),
                    "raw_metadata_sha256": sha256_path(raw_metadata_path),
                    "raw_sha256": raw_metadata["sha256"],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return summary_path

    money_summary = write_summary(
        "qld_ecq_eds_money_flow_normalizer",
        money_jsonl,
        count_field="table_counts",
        counts={
            "qld_ecq_eds_map_export_csv": 1,
            "qld_ecq_eds_expenditure_export_csv": 1,
        },
    )
    participants_summary = write_summary(
        "qld_ecq_eds_participant_normalizer",
        participants_jsonl,
        count_field="source_counts",
        counts={
            "qld_ecq_eds_api_political_electors": 1,
            "qld_ecq_eds_api_political_parties": 1,
            "qld_ecq_eds_api_associated_entities": 1,
            "qld_ecq_eds_api_local_groups": 1,
        },
    )
    contexts_summary = write_summary(
        "qld_ecq_eds_context_normalizer",
        contexts_jsonl,
        count_field="source_counts",
        counts={
            "qld_ecq_eds_api_political_events": 1,
            "qld_ecq_eds_api_local_electorates": 1,
        },
    )
    qld_boundaries_summary = write_artifact_summary(
        "qld_state_electorate_boundaries",
        parser_name="qld_state_electorate_boundaries_arcgis_geojson_v1",
        path_field="geojson_path",
        sha256_field="geojson_sha256",
        artifact_path=qld_boundaries_geojson,
        source_id="qld_state_electoral_boundaries_arcgis",
        count_field="feature_count",
        count=1,
        names_field="division_names",
        names=["Algester"],
        raw_metadata_path=qld_boundary_metadata,
        extra={"boundary_set": "qld_state_2017_current"},
    )
    qld_members_summary = write_artifact_summary(
        "qld_parliament_current_members",
        parser_name="qld_parliament_current_members_mail_merge_xlsx_v1",
        path_field="jsonl_path",
        sha256_field="jsonl_sha256",
        artifact_path=qld_members_jsonl,
        source_id="qld_parliament_members_mail_merge_xlsx",
        count_field="electorate_count",
        count=1,
        names_field="electorates",
        names=["Algester"],
        raw_metadata_path=qld_members_metadata,
    )
    manifest_path = tmp_path / "state_local_qld_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "qld_ecq_eds",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_qld_ecq_eds_money_flows",
                        "status": "succeeded",
                        "output": str(money_summary),
                        "output_sha256": sha256_path(money_summary),
                    },
                    {
                        "name": "normalize_qld_ecq_eds_participants",
                        "status": "succeeded",
                        "output": str(participants_summary),
                        "output_sha256": sha256_path(participants_summary),
                    },
                    {
                        "name": "normalize_qld_ecq_eds_contexts",
                        "status": "succeeded",
                        "output": str(contexts_summary),
                        "output_sha256": sha256_path(contexts_summary),
                    },
                    {
                        "name": "normalize_qld_state_boundaries",
                        "status": "succeeded",
                        "output": str(qld_boundaries_summary),
                        "output_sha256": sha256_path(qld_boundaries_summary),
                    },
                    {
                        "name": "normalize_qld_current_members",
                        "status": "succeeded",
                        "output": str(qld_members_summary),
                        "output_sha256": sha256_path(qld_members_summary),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert qld_ecq_eds_paths_from_pipeline_manifest(manifest_path) == {
        "money_flows": money_jsonl,
        "participants": participants_jsonl,
        "contexts": contexts_jsonl,
        "state_boundaries": qld_boundaries_geojson,
        "current_members": qld_members_jsonl,
    }

    failed_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failed_manifest["status"] = "failed"
    failed_manifest_path = tmp_path / "state_local_qld_failed_status_manifest.json"
    failed_manifest_path.write_text(
        json.dumps(failed_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Pipeline manifest did not succeed"):
        qld_ecq_eds_paths_from_pipeline_manifest(failed_manifest_path)

    missing_normalize_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_normalize_manifest["steps"] = [
        step
        for step in missing_normalize_manifest["steps"]
        if step["name"] != "normalize_qld_state_boundaries"
    ]
    missing_normalize_manifest["steps"].append(
        {
            "name": "fetch_qld_state_boundaries",
            "status": "succeeded",
            "output": "/tmp/qld-boundary-metadata.json",
        }
    )
    missing_normalize_manifest_path = tmp_path / "state_local_qld_missing_normalize.json"
    missing_normalize_manifest_path.write_text(
        json.dumps(missing_normalize_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="boundary fetch without boundary normalization"):
        qld_ecq_eds_paths_from_pipeline_manifest(missing_normalize_manifest_path)

    partial_map_roster_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    partial_map_roster_manifest["steps"] = [
        step
        for step in partial_map_roster_manifest["steps"]
        if step["name"] != "normalize_qld_current_members"
    ]
    partial_map_roster_manifest_path = tmp_path / "state_local_qld_partial_map_roster.json"
    partial_map_roster_manifest_path.write_text(
        json.dumps(partial_map_roster_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must include both boundaries and current members"):
        qld_ecq_eds_paths_from_pipeline_manifest(partial_map_roster_manifest_path)

    mismatched_members_summary = write_artifact_summary(
        "qld_parliament_current_members_mismatch",
        parser_name="qld_parliament_current_members_mail_merge_xlsx_v1",
        path_field="jsonl_path",
        sha256_field="jsonl_sha256",
        artifact_path=qld_members_jsonl,
        source_id="qld_parliament_members_mail_merge_xlsx",
        count_field="electorate_count",
        count=1,
        names_field="electorates",
        names=["Ashgrove"],
        raw_metadata_path=qld_members_metadata,
    )
    mismatched_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for step in mismatched_manifest["steps"]:
        if step["name"] == "normalize_qld_current_members":
            step["output"] = str(mismatched_members_summary)
            step["output_sha256"] = sha256_path(mismatched_members_summary)
    mismatched_manifest_path = tmp_path / "state_local_qld_mismatched_roster.json"
    mismatched_manifest_path.write_text(
        json.dumps(mismatched_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="electorate sets do not match"):
        qld_ecq_eds_paths_from_pipeline_manifest(mismatched_manifest_path)

    original_boundary_metadata = qld_boundary_metadata.read_text(encoding="utf-8")
    qld_boundary_metadata.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="raw metadata hash mismatch"):
        qld_ecq_eds_paths_from_pipeline_manifest(manifest_path)
    qld_boundary_metadata.write_text(original_boundary_metadata, encoding="utf-8")

    qld_boundaries_geojson.write_text('{"changed": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        qld_ecq_eds_paths_from_pipeline_manifest(manifest_path)


def test_qld_pipeline_manifest_replays_legacy_unhashed_artifacts(tmp_path) -> None:
    money_jsonl = tmp_path / "money.jsonl"
    participants_jsonl = tmp_path / "participants.jsonl"
    contexts_jsonl = tmp_path / "contexts.jsonl"
    money_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_map_export_csv"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_expenditure_export_csv"}) + "\n",
        encoding="utf-8",
    )
    participants_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_api_political_electors"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_political_parties"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_associated_entities"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_local_groups"}) + "\n",
        encoding="utf-8",
    )
    contexts_jsonl.write_text(
        json.dumps({"source_id": "qld_ecq_eds_api_political_events"}) + "\n"
        + json.dumps({"source_id": "qld_ecq_eds_api_local_electorates"}) + "\n",
        encoding="utf-8",
    )

    def write_legacy_summary(
        name: str,
        jsonl_path: Path,
        *,
        count_field: str,
        counts: dict[str, int],
    ) -> Path:
        summary_path = tmp_path / f"{name}.summary.json"
        summary_path.write_text(
            json.dumps(
                {
                    "normalizer_name": name,
                    "jsonl_path": str(jsonl_path),
                    "total_count": sum(counts.values()),
                    count_field: counts,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return summary_path

    money_summary = write_legacy_summary(
        "qld_ecq_eds_money_flow_normalizer",
        money_jsonl,
        count_field="table_counts",
        counts={
            "qld_ecq_eds_map_export_csv": 1,
            "qld_ecq_eds_expenditure_export_csv": 1,
        },
    )
    participants_summary = write_legacy_summary(
        "qld_ecq_eds_participant_normalizer",
        participants_jsonl,
        count_field="source_counts",
        counts={
            "qld_ecq_eds_api_political_electors": 1,
            "qld_ecq_eds_api_political_parties": 1,
            "qld_ecq_eds_api_associated_entities": 1,
            "qld_ecq_eds_api_local_groups": 1,
        },
    )
    contexts_summary = write_legacy_summary(
        "qld_ecq_eds_context_normalizer",
        contexts_jsonl,
        count_field="source_counts",
        counts={
            "qld_ecq_eds_api_political_events": 1,
            "qld_ecq_eds_api_local_electorates": 1,
        },
    )
    manifest_path = tmp_path / "state_local_qld_legacy_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "qld_ecq_eds",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_qld_ecq_eds_money_flows",
                        "status": "succeeded",
                        "output": str(money_summary),
                    },
                    {
                        "name": "normalize_qld_ecq_eds_participants",
                        "status": "succeeded",
                        "output": str(participants_summary),
                    },
                    {
                        "name": "normalize_qld_ecq_eds_contexts",
                        "status": "succeeded",
                        "output": str(contexts_summary),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert qld_ecq_eds_paths_from_pipeline_manifest(manifest_path) == {
        "money_flows": money_jsonl,
        "participants": participants_jsonl,
        "contexts": contexts_jsonl,
    }


def test_qld_pipeline_manifest_rejects_tampered_summary(tmp_path) -> None:
    jsonl_path = tmp_path / "money.jsonl"
    jsonl_path.write_text(json.dumps({"source_id": "qld_ecq_eds_map_export_csv"}) + "\n", encoding="utf-8")
    summary_path = tmp_path / "money.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "qld_ecq_eds_money_flow_normalizer",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
                "total_count": 1,
                "table_counts": {
                    "qld_ecq_eds_map_export_csv": 1,
                    "qld_ecq_eds_expenditure_export_csv": 0,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_qld_manifest.json"
    bad_summary_hash = "0" * 64
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "qld_ecq_eds",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_qld_ecq_eds_money_flows",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": bad_summary_hash,
                    },
                    {
                        "name": "normalize_qld_ecq_eds_participants",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": bad_summary_hash,
                    },
                    {
                        "name": "normalize_qld_ecq_eds_contexts",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": bad_summary_hash,
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Summary hash mismatch"):
        qld_ecq_eds_paths_from_pipeline_manifest(manifest_path)


def test_qld_pipeline_manifest_rejects_failed_steps(tmp_path) -> None:
    manifest_path = tmp_path / "state_local_qld_failed.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "qld_ecq_eds",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_qld_ecq_eds_money_flows",
                        "status": "failed",
                        "output": "/tmp/money.summary.json",
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="did not succeed"):
        qld_ecq_eds_paths_from_pipeline_manifest(manifest_path)


def test_nsw_pipeline_manifest_selects_aggregate_context_artifact(tmp_path) -> None:
    source_body_path = tmp_path / "nsw-heatmap.html"
    source_body_path.write_text("<html>fixture</html>", encoding="utf-8")
    source_body_sha256 = hashlib.sha256(source_body_path.read_bytes()).hexdigest()
    source_metadata_path = tmp_path / "metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body_path),
                "sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_sha256 = hashlib.sha256(source_metadata_path.read_bytes()).hexdigest()
    jsonl_path = tmp_path / "nsw-aggregates.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "nsw_2023_state_election_donation_heatmap",
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "nsw-aggregates.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "nsw_pre_election_donor_location_heatmap_normalizer",
                "source_dataset": "nsw_electoral_disclosures",
                "source_id": "nsw_2023_state_election_donation_heatmap",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": hashlib.sha256(jsonl_path.read_bytes()).hexdigest(),
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_nsw_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "nsw_electoral_disclosures",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_nsw_pre_election_donor_location_heatmap",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert nsw_aggregate_context_path_from_pipeline_manifest(manifest_path) == jsonl_path

    source_body_path.write_text("<html>changed</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="Source body hash mismatch"):
        nsw_aggregate_context_path_from_pipeline_manifest(manifest_path)


def test_act_pipeline_manifest_selects_gift_return_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_body_path = tmp_path / "act-gift-returns.html"
    source_body_path.write_text("<html>fixture</html>", encoding="utf-8")
    source_body_sha256 = sha256_path(source_body_path)
    source_metadata_path = tmp_path / "metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body_path),
                "sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_sha256 = sha256_path(source_metadata_path)
    jsonl_path = tmp_path / "act-gift-returns.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "act_gift_returns_2025_2026",
                "source_dataset": "act_elections_gift_returns",
                "normalizer_name": "act_gift_return_html_normalizer",
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "act-gift-returns.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "act_gift_return_html_normalizer",
                "source_dataset": "act_elections_gift_returns",
                "source_id": "act_gift_returns_2025_2026",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": sha256_path(jsonl_path),
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "source_counts": {"act_gift_returns_2025_2026": 1},
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_act_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "act_elections_gift_returns",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_act_gift_returns",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert act_gift_return_path_from_pipeline_manifest(manifest_path) == jsonl_path

    source_body_path.write_text("<html>changed</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="Source body hash mismatch"):
        act_gift_return_path_from_pipeline_manifest(manifest_path)


def test_act_state_manifest_selects_annual_return_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_body_path = tmp_path / "act-annual-returns.html"
    source_body_path.write_text("<html>fixture</html>", encoding="utf-8")
    source_metadata_path = tmp_path / "act-annual.metadata.json"
    source_metadata_path.write_text(
        json.dumps({"body_path": str(source_body_path)}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    jsonl_path = tmp_path / "act-annual-returns.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "act_annual_returns_2024_2025",
                "source_dataset": "act_elections_annual_returns",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "act-annual-returns.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "act_annual_return_receipt_html_normalizer",
                "source_dataset": "act_elections_annual_returns",
                "source_id": "act_annual_returns_2024_2025",
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": sha256_path(source_metadata_path),
                "source_body_path": str(source_body_path),
                "source_body_sha256": sha256_path(source_body_path),
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": sha256_path(jsonl_path),
                "source_counts": {"act_annual_returns_2024_2025": 1},
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_act_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "act_elections_state_disclosures",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_act_annual_return_receipts",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert act_annual_return_path_from_pipeline_manifest(manifest_path) == jsonl_path

    jsonl_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSONL hash mismatch"):
        act_annual_return_path_from_pipeline_manifest(manifest_path)


def test_act_state_manifest_validates_annual_before_loading_gifts(tmp_path, monkeypatch) -> None:
    manifest_path = tmp_path / "state_local_act_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "act_elections_state_disclosures",
                    "loads_database": False,
                },
                "steps": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    monkeypatch.setattr(
        load_module,
        "act_gift_return_path_from_pipeline_manifest",
        lambda path: calls.append("validate_gift") or (tmp_path / "gift.jsonl"),
    )

    def fail_annual(path):
        calls.append("validate_annual")
        raise ValueError("annual artifact invalid")

    def load_gift(*args, **kwargs):
        calls.append("load_gift")
        return {"money_flows": 1}

    monkeypatch.setattr(load_module, "act_annual_return_path_from_pipeline_manifest", fail_annual)
    monkeypatch.setattr(load_module, "load_act_gift_return_money_flows", load_gift)

    with pytest.raises(ValueError, match="annual artifact invalid"):
        load_act_elections_from_pipeline_manifest(
            object(),
            manifest_path,
            include_influence_events=False,
        )

    assert calls == ["validate_gift", "validate_annual"]


def test_vic_pipeline_manifest_selects_funding_register_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    doc_body_path = tmp_path / "vec-funding.docx"
    doc_body_path.write_bytes(b"docx bytes")
    doc_metadata_path = tmp_path / "metadata.json"
    doc_metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(doc_body_path),
                "sha256": sha256_path(doc_body_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    document_summary_path = tmp_path / "documents.summary.json"
    document_summary_path.write_text(
        json.dumps(
            {
                "source_dataset": "vic_vec_funding_register",
                "documents": [
                    {
                        "title": "VEC funding register fixture",
                        "source_id": "vic_vec_funding_register__fixture",
                        "metadata_path": str(doc_metadata_path),
                        "metadata_sha256": sha256_path(doc_metadata_path),
                        "body_path": str(doc_body_path),
                        "body_sha256": sha256_path(doc_body_path),
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    jsonl_path = tmp_path / "vic-funding.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "vic_vec_funding_register__fixture",
                "source_dataset": "vic_vec_funding_register",
                "normalizer_name": "vic_vec_funding_register_docx_normalizer",
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "vic-funding.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "vic_vec_funding_register_docx_normalizer",
                "source_dataset": "vic_vec_funding_register",
                "source_id": "vic_vec_funding_register",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": sha256_path(jsonl_path),
                "document_summary_path": str(document_summary_path),
                "document_summary_sha256": sha256_path(document_summary_path),
                "source_counts": {"vic_vec_funding_register__fixture": 1},
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_vic_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "vic_vec_funding_register",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_vic_vec_funding_registers",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert vic_vec_funding_register_path_from_pipeline_manifest(manifest_path) == jsonl_path

    doc_body_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="Source body hash mismatch"):
        vic_vec_funding_register_path_from_pipeline_manifest(manifest_path)


def test_nt_pipeline_manifest_selects_annual_gift_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_body_path = tmp_path / "nt-gifts.html"
    source_body_path.write_text("<html>fixture</html>", encoding="utf-8")
    source_body_sha256 = sha256_path(source_body_path)
    source_metadata_path = tmp_path / "metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body_path),
                "sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_sha256 = sha256_path(source_metadata_path)
    jsonl_path = tmp_path / "nt-gifts.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "nt_ntec_annual_returns_gifts_2024_2025",
                "source_dataset": "nt_ntec_annual_returns_gifts",
                "normalizer_name": "nt_ntec_annual_gift_html_normalizer",
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "nt-gifts.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "nt_ntec_annual_gift_html_normalizer",
                "source_dataset": "nt_ntec_annual_returns_gifts",
                "source_id": "nt_ntec_annual_returns_gifts_2024_2025",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": sha256_path(jsonl_path),
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "source_counts": {"nt_ntec_annual_returns_gifts_2024_2025": 1},
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_nt_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "nt_ntec_annual_returns_gifts",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_nt_ntec_annual_gifts",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert nt_ntec_annual_gifts_path_from_pipeline_manifest(manifest_path) == jsonl_path

    source_body_path.write_text("<html>changed</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="Source body hash mismatch"):
        nt_ntec_annual_gifts_path_from_pipeline_manifest(manifest_path)


def test_nt_pipeline_manifest_selects_annual_return_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    source_body_path = tmp_path / "nt-annual.html"
    source_body_path.write_text("<html>fixture</html>", encoding="utf-8")
    source_body_sha256 = sha256_path(source_body_path)
    source_metadata_path = tmp_path / "metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(source_body_path),
                "sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_sha256 = sha256_path(source_metadata_path)
    jsonl_path = tmp_path / "nt-annual.jsonl"
    jsonl_path.write_text(
        json.dumps(
            {
                "source_id": "nt_ntec_annual_returns_2024_2025",
                "source_dataset": "nt_ntec_annual_returns",
                "normalizer_name": "nt_ntec_annual_return_financial_html_normalizer",
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_path = tmp_path / "nt-annual.summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "normalizer_name": "nt_ntec_annual_return_financial_html_normalizer",
                "source_dataset": "nt_ntec_annual_returns",
                "source_id": "nt_ntec_annual_returns_2024_2025",
                "jsonl_path": str(jsonl_path),
                "jsonl_sha256": sha256_path(jsonl_path),
                "source_metadata_path": str(source_metadata_path),
                "source_metadata_sha256": source_metadata_sha256,
                "source_body_path": str(source_body_path),
                "source_body_sha256": source_body_sha256,
                "source_counts": {"nt_ntec_annual_returns_2024_2025": 1},
                "total_count": 1,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_nt_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "nt_ntec_annual_returns",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_nt_ntec_annual_returns",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert nt_ntec_annual_returns_path_from_pipeline_manifest(manifest_path) == jsonl_path

    source_body_path.write_text("<html>changed</html>", encoding="utf-8")
    with pytest.raises(ValueError, match="Source body hash mismatch"):
        nt_ntec_annual_returns_path_from_pipeline_manifest(manifest_path)


def test_sa_pipeline_manifest_selects_return_summary_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    jsonl_path = tmp_path / "sa-return-summaries.jsonl"
    jsonl_path.write_text(
        json.dumps({"source_id": "sa_ecsa_funding2024_return_records"}) + "\n",
        encoding="utf-8",
    )
    source_body_path = tmp_path / "sa-body.json"
    source_body_path.write_text(
        json.dumps(
            {
                "source_id": "sa_ecsa_funding2024_return_records",
                "complete_page_coverage": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_path = tmp_path / "sa-metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "source": {"source_id": "sa_ecsa_funding2024_return_records"},
                "body_path": str(source_body_path),
                "sha256": sha256_path(source_body_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_data = {
        "normalizer_name": "sa_ecsa_funding_return_index_normalizer",
        "source_dataset": "sa_ecsa_funding_returns",
        "source_id": "sa_ecsa_funding2024_return_records",
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": sha256_path(jsonl_path),
        "source_metadata_path": str(source_metadata_path),
        "source_metadata_sha256": sha256_path(source_metadata_path),
        "source_body_path": str(source_body_path),
        "source_body_sha256": sha256_path(source_body_path),
        "portal_record_count_reported": 1,
        "complete_page_coverage": True,
        "source_counts": {"sa_ecsa_funding2024_return_records": 1},
        "total_count": 1,
    }
    summary_path = tmp_path / "sa-return-summaries.summary.json"
    summary_path.write_text(
        json.dumps(summary_data, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_sa_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "sa_ecsa_funding_returns",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_sa_ecsa_return_index",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert sa_ecsa_return_summary_path_from_pipeline_manifest(manifest_path) == jsonl_path

    incomplete_summary_path = tmp_path / "sa-return-summaries-incomplete.summary.json"
    incomplete_summary_path.write_text(
        json.dumps({**summary_data, "complete_page_coverage": False}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    incomplete_manifest_path = tmp_path / "state_local_sa_incomplete_manifest.json"
    incomplete_manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "sa_ecsa_funding_returns",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_sa_ecsa_return_index",
                        "status": "succeeded",
                        "output": str(incomplete_summary_path),
                        "output_sha256": sha256_path(incomplete_summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not complete"):
        sa_ecsa_return_summary_path_from_pipeline_manifest(incomplete_manifest_path)

    jsonl_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="JSONL hash mismatch"):
        sa_ecsa_return_summary_path_from_pipeline_manifest(manifest_path)
    jsonl_path.write_text(
        json.dumps({"source_id": "sa_ecsa_funding2024_return_records"}) + "\n",
        encoding="utf-8",
    )

    source_body_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source body hash mismatch"):
        sa_ecsa_return_summary_path_from_pipeline_manifest(manifest_path)


def test_waec_pipeline_manifest_selects_complete_contribution_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    jsonl_path = tmp_path / "waec-contributions.jsonl"
    jsonl_path.write_text(
        json.dumps({"source_id": "waec_ods_political_contributions"}) + "\n",
        encoding="utf-8",
    )
    source_body_path = tmp_path / "waec-body.json"
    source_body_path.write_text(
        json.dumps(
            {
                "source_id": "waec_ods_political_contributions",
                "complete_page_coverage": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    source_metadata_path = tmp_path / "waec-metadata.json"
    source_metadata_path.write_text(
        json.dumps(
            {
                "source": {"source_id": "waec_ods_political_contributions"},
                "body_path": str(source_body_path),
                "sha256": sha256_path(source_body_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    summary_data = {
        "normalizer_name": "waec_ods_political_contribution_grid_normalizer",
        "source_dataset": "waec_political_contributions",
        "source_id": "waec_ods_political_contributions",
        "jsonl_path": str(jsonl_path),
        "jsonl_sha256": sha256_path(jsonl_path),
        "source_metadata_path": str(source_metadata_path),
        "source_metadata_sha256": sha256_path(source_metadata_path),
        "source_body_path": str(source_body_path),
        "source_body_sha256": sha256_path(source_body_path),
        "complete_page_coverage": True,
        "source_counts": {"waec_ods_political_contributions": 1},
        "total_count": 1,
    }
    summary_path = tmp_path / "waec-contributions.summary.json"
    summary_path.write_text(
        json.dumps(summary_data, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "state_local_wa_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "waec_political_contributions",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_waec_political_contributions",
                        "status": "succeeded",
                        "output": str(summary_path),
                        "output_sha256": sha256_path(summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    assert waec_political_contribution_path_from_pipeline_manifest(manifest_path) == jsonl_path

    incomplete_summary_path = tmp_path / "waec-contributions-incomplete.summary.json"
    incomplete_summary_path.write_text(
        json.dumps({**summary_data, "complete_page_coverage": False}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    incomplete_manifest_path = tmp_path / "state_local_wa_incomplete_manifest.json"
    incomplete_manifest_path.write_text(
        json.dumps(
            {
                "pipeline_name": "state_local",
                "parameters": {
                    "source_family": "waec_political_contributions",
                    "loads_database": False,
                },
                "steps": [
                    {
                        "name": "normalize_waec_political_contributions",
                        "status": "succeeded",
                        "output": str(incomplete_summary_path),
                        "output_sha256": sha256_path(incomplete_summary_path),
                    },
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not complete"):
        waec_political_contribution_path_from_pipeline_manifest(incomplete_manifest_path)

    source_metadata_path.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source metadata hash mismatch"):
        waec_political_contribution_path_from_pipeline_manifest(manifest_path)


def test_tas_tec_pipeline_manifest_selects_donation_artifact(tmp_path) -> None:
    def sha256_path(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def write_jsonl(urls: list[str]) -> None:
        rows = [
            {
                "source_id": source_id,
                "supporting_document_urls": urls if index == 0 else [],
            }
            for index, source_id in enumerate(source_ids)
        ]
        jsonl_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    def write_summary(
        *,
        support_urls: list[str],
        attempts: dict[str, dict[str, object]],
        hashes: dict[str, dict[str, object]],
    ) -> None:
        summary_path.write_text(
            json.dumps(
                {
                    "normalizer_name": "tas_tec_reportable_donation_table_normalizer",
                    "source_dataset": "tas_tec_donations",
                    "source_ids": list(source_ids),
                    "jsonl_path": str(jsonl_path),
                    "jsonl_sha256": sha256_path(jsonl_path),
                    "source_counts": {source_id: 1 for source_id in source_ids},
                    "source_hashes": source_hashes,
                    "supporting_document_url_count": len(set(support_urls)),
                    "supporting_document_attempts": attempts,
                    "supporting_document_hashes": hashes,
                    "total_count": 3,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    def write_manifest() -> None:
        manifest_path.write_text(
            json.dumps(
                {
                    "pipeline_name": "state_local",
                    "parameters": {
                        "source_family": "tas_tec_donations",
                        "loads_database": False,
                    },
                    "steps": [
                        {
                            "name": "normalize_tas_tec_donations",
                            "status": "succeeded",
                            "output": str(summary_path),
                            "output_sha256": sha256_path(summary_path),
                        },
                    ],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    source_ids = (
        "tas_tec_donations_monthly_table",
        "tas_tec_donations_seven_day_ha25_table",
        "tas_tec_donations_seven_day_lc26_table",
    )
    jsonl_path = tmp_path / "tas-donations.jsonl"
    source_hashes: dict[str, dict[str, str]] = {}
    for source_id in source_ids:
        body_path = tmp_path / f"{source_id}.html"
        body_path.write_text(f"<table>{source_id}</table>\n", encoding="utf-8")
        metadata_path = tmp_path / f"{source_id}.metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source": {"source_id": source_id},
                    "body_path": str(body_path),
                    "sha256": sha256_path(body_path),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        source_hashes[source_id] = {
            "metadata_path": str(metadata_path),
            "metadata_sha256": sha256_path(metadata_path),
            "body_path": str(body_path),
            "body_sha256": sha256_path(body_path),
        }
    declaration_url = "https://www.tec.tas.gov.au/example-declaration.pdf"
    declaration_source_id = _declaration_source_id(declaration_url)
    declaration_body_path = tmp_path / "tas-declaration.pdf"
    declaration_body_bytes = b"%PDF-1.4\nfixture\n%%EOF\n"
    declaration_body_path.write_bytes(declaration_body_bytes)
    declaration_metadata_path = tmp_path / "tas-declaration.metadata.json"
    declaration_metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": declaration_source_id,
                    "url": declaration_url,
                },
                "body_path": str(declaration_body_path),
                "final_url": declaration_url,
                "sha256": sha256_path(declaration_body_path),
                "ok": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    declaration_attempt = {
        "archive_source_id": declaration_source_id,
        "archive_metadata_path": str(declaration_metadata_path),
        "archive_metadata_sha256": sha256_path(declaration_metadata_path),
        "archived": True,
    }
    declaration_hash = {
        **declaration_attempt,
        "archive_body_path": str(declaration_body_path),
        "archive_body_sha256": sha256_path(declaration_body_path),
    }
    summary_path = tmp_path / "tas-donations.summary.json"
    write_jsonl([declaration_url])
    write_summary(
        support_urls=[declaration_url],
        attempts={declaration_url: declaration_attempt},
        hashes={declaration_url: declaration_hash},
    )
    manifest_path = tmp_path / "state_local_tas_manifest.json"
    write_manifest()

    assert tas_tec_donation_path_from_pipeline_manifest(manifest_path) == jsonl_path

    second_declaration_url = "https://www.tec.tas.gov.au/second-declaration.pdf"
    write_jsonl([declaration_url, second_declaration_url])
    write_summary(
        support_urls=[declaration_url, second_declaration_url],
        attempts={declaration_url: declaration_attempt},
        hashes={declaration_url: declaration_hash},
    )
    write_manifest()
    with pytest.raises(ValueError, match="supporting document attempt URL scope mismatch"):
        tas_tec_donation_path_from_pipeline_manifest(manifest_path)

    write_jsonl([declaration_url])
    wrong_declaration_url = "https://www.tec.tas.gov.au/wrong-declaration.pdf"
    write_jsonl([wrong_declaration_url])
    write_summary(
        support_urls=[wrong_declaration_url],
        attempts={wrong_declaration_url: declaration_attempt},
        hashes={wrong_declaration_url: declaration_hash},
    )
    write_manifest()
    with pytest.raises(ValueError, match="source_id does not match URL"):
        tas_tec_donation_path_from_pipeline_manifest(manifest_path)

    write_jsonl([declaration_url])
    write_summary(
        support_urls=[declaration_url],
        attempts={declaration_url: declaration_attempt},
        hashes={declaration_url: declaration_hash},
    )
    write_manifest()
    declaration_body_path.write_bytes(b"%PDF-1.4\ntampered\n%%EOF\n")
    with pytest.raises(ValueError, match="supporting document body hash mismatch"):
        tas_tec_donation_path_from_pipeline_manifest(manifest_path)
    declaration_body_path.write_bytes(declaration_body_bytes)

    first_body = Path(source_hashes[source_ids[0]]["body_path"])
    first_body.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source body hash mismatch"):
        tas_tec_donation_path_from_pipeline_manifest(manifest_path)


def test_money_flow_loader_prefers_stable_observation_key(tmp_path, monkeypatch) -> None:
    jsonl_path = tmp_path / "tas-donations.jsonl"
    record = {
        "source_dataset": "tas_tec_donations",
        "source_metadata_path": str(tmp_path / "metadata.json"),
        "source_body_path": str(tmp_path / "body.html"),
        "source_table": "reportable_donation_tables",
        "source_row_number": "tas_tec_donations_monthly_table:r17",
        "observation_key": "tas_tec_donations_monthly_table:donor-recipient-doc-123",
        "jurisdiction_name": "Tasmania",
        "jurisdiction_level": "state",
        "jurisdiction_code": "TAS",
        "source_raw_name": "Example Donor Pty Ltd",
        "recipient_raw_name": "Example Party",
        "amount_aud": "1000.00",
        "date": "2025-07-04",
        "date_reported": "",
        "financial_year": "2025-2026",
        "return_type": "TEC reportable political donation monthly disclosure",
        "receipt_type": "Reportable political donation",
        "flow_kind": "tas_reportable_donation",
        "original": {"name_of_donor": "Example Donor Pty Ltd"},
    }
    jsonl_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")

    monkeypatch.setattr(load_module, "_validate_money_flow_source_hashes", lambda record: None)
    monkeypatch.setattr(load_module, "_begin_money_flow_source_refresh", lambda conn, source: 0)
    monkeypatch.setattr(load_module, "upsert_source_document", lambda conn, path: 10)
    monkeypatch.setattr(load_module, "get_or_create_entity", lambda conn, name: 20)
    monkeypatch.setattr(load_module, "get_or_create_jurisdiction", lambda conn, *args: 30)
    monkeypatch.setattr(load_module, "link_aec_direct_representative_money_flows", lambda conn: {})
    monkeypatch.setattr(load_module, "link_aec_candidate_campaign_money_flows", lambda conn: {})
    monkeypatch.setattr(load_module, "as_jsonb", lambda value: value)

    conn = StatementRecordingConnection()
    summary = load_module._load_aec_money_flow_jsonl(
        conn,
        jsonl_path,
        default_source_dataset="tas_tec_donations",
    )

    assert summary["money_flows"] == 1
    insert_params = conn.cursor_instance.executed_params[0]
    assert (
        insert_params[0]
        == "tas_tec_donations:tas_tec_donations_monthly_table:donor-recipient-doc-123"
    )
    assert insert_params[14] == "reportable_donation_tables:tas_tec_donations_monthly_table:r17"


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
    assert classify_money_event_type("act_gift_in_kind", "Gift in kind") == "gift_in_kind"
    assert classify_money_event_type("vic_public_funding_payment", "") == (
        "vic_public_funding_payment"
    )
    assert is_public_funding_context_money_flow(
        {"source_dataset": "vic_vec_funding_register", "flow_kind": "vic_public_funding_payment"}
    )
    assert not is_campaign_support_money_flow(
        {"source_dataset": "vic_vec_funding_register", "flow_kind": "vic_public_funding_payment"}
    )
    assert is_state_return_summary_money_flow(
        {
            "source_dataset": "sa_ecsa_funding_returns",
            "transaction_kind": "return_summary",
            "flow_kind": "sa_political_party_return_summary",
        }
    )
    assert is_state_source_receipt_context_money_flow(
        {
            "source_dataset": "act_elections_annual_returns",
            "flow_kind": "act_annual_receipt",
            "public_amount_counting_role": "state_source_receipt_context_not_consolidated",
        }
    )
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
