import pytest

from au_politics_money.pipeline import (
    PipelineManifest,
    run_federal_foundation_pipeline,
    run_state_local_pipeline,
)


def test_pipeline_manifest_records_reproducibility_fields() -> None:
    manifest = PipelineManifest(
        pipeline_name="test",
        run_id="test_20260427T000000Z",
        status="running",
        started_at="2026-04-27T00:00:00+00:00",
        parameters={"smoke": True},
    )
    assert manifest.au_politics_money_version
    assert manifest.python_version
    assert manifest.parameters["smoke"] is True


def test_pipeline_refresh_mode_refetches_cached_update_sensitive_sources(monkeypatch) -> None:
    postcodes = ["2000"]
    calls: dict[str, object] = {}

    monkeypatch.setattr("au_politics_money.pipeline._seed_postcodes", lambda: postcodes)
    monkeypatch.setattr(
        "au_politics_money.pipeline._postcode_seed_metadata",
        lambda values: {"postcode_seed_count": len(values)},
    )
    monkeypatch.setattr("au_politics_money.pipeline._git_commit", lambda: "abc123")
    monkeypatch.setattr("au_politics_money.pipeline._dependency_versions", lambda: {})

    def fake_write_manifest(manifest):
        calls["manifest_parameters"] = manifest.parameters
        calls["step_outputs"] = {step.name: step.output for step in manifest.steps}
        return "manifest.json"

    monkeypatch.setattr("au_politics_money.pipeline._write_manifest", fake_write_manifest)
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_source",
        lambda source: f"fetch:{source.source_id}",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline._discover_source_links",
        lambda source_id: f"discover:{source_id}",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline._fetch_discovered",
        lambda source_id, link_type=None, limit=None: {
            "source_id": source_id,
            "link_type": link_type,
            "limit": limit,
        },
    )
    monkeypatch.setattr("au_politics_money.pipeline.build_current_parliament_roster", lambda: "roster")
    monkeypatch.setattr("au_politics_money.pipeline.summarize_aec_annual_zip", lambda: "annual-summary")
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_aec_annual_money_flows",
        lambda: "annual-normalized",
    )
    monkeypatch.setattr("au_politics_money.pipeline.summarize_aec_election_zip", lambda: "election-summary")
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_aec_election_money_flows",
        lambda: "election-normalized",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_aec_public_funding",
        lambda: "public-funding",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_aec_electorate_finder_postcodes",
        lambda values, *, refetch=False: calls.setdefault(
            "postcode_fetch",
            {"values": values, "refetch": refetch},
        ),
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_aec_electorate_finder_postcodes",
        lambda values: "postcode-normalized",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_current_aec_boundary_zip",
        lambda *, refetch=False: calls.setdefault("boundary_refetch", refetch),
    )
    monkeypatch.setattr("au_politics_money.pipeline.extract_current_aec_boundaries", lambda: "boundaries")
    monkeypatch.setattr("au_politics_money.pipeline.fetch_aims_australian_coastline_zip", lambda: "aims")
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_aims_australian_coastline_land_mask",
        lambda: "aims-mask",
    )
    monkeypatch.setattr("au_politics_money.pipeline.fetch_natural_earth_admin0_zip", lambda: "ne-admin")
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_natural_earth_physical_land_zip",
        lambda: "ne-land",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_natural_earth_country_land_mask",
        lambda: "ne-country",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_natural_earth_physical_land_mask",
        lambda: "ne-physical",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_aph_decision_record_index",
        lambda source_id: f"aph-index:{source_id}",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_aph_decision_record_documents",
        lambda *, only_missing, limit: calls.setdefault(
            "aph_documents",
            {"only_missing": only_missing, "limit": limit},
        ),
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_official_aph_divisions",
        lambda: "aph-divisions",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_senate_interest_statements",
        lambda limit=None: f"senate-fetch:{limit}",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.extract_senate_interest_records",
        lambda: "senate-records",
    )
    monkeypatch.setattr("au_politics_money.pipeline.classify_entity_names", lambda: "classified")
    monkeypatch.setattr(
        "au_politics_money.pipeline.discover_official_identifier_sources",
        lambda: "identifier-sources",
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_official_identifier_bulk_resources",
        lambda *, extract_limit_per_source=None: calls.setdefault(
            "official_identifier_bulk_limit",
            extract_limit_per_source,
        ),
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_lobbyist_register_snapshot",
        lambda limit=None: f"lobbyists:{limit}",
    )

    run_federal_foundation_pipeline(
        smoke=True,
        refresh_existing_sources=True,
        skip_house_pdfs=True,
        skip_pdf_text=True,
        include_official_identifier_bulk=True,
    )

    assert calls["manifest_parameters"]["refresh_existing_sources"] is True
    assert calls["manifest_parameters"]["include_official_identifier_bulk"] is True
    assert calls["postcode_fetch"] == {"values": postcodes, "refetch": True}
    assert calls["boundary_refetch"] is True
    assert calls["aph_documents"] == {"only_missing": False, "limit": 10}
    assert calls["official_identifier_bulk_limit"] == 25


def test_state_local_qld_pipeline_records_reproducible_steps(monkeypatch, tmp_path) -> None:
    calls: dict[str, object] = {}
    export_summary_path = tmp_path / "qld-export-summary.json"
    export_summary_path.write_text(
        """
        {
          "outputs": [
            {
              "source_id": "qld_ecq_eds_map_export_csv",
              "metadata_path": "/tmp/qld-map-metadata.json"
            },
            {
              "source_id": "qld_ecq_eds_expenditure_export_csv",
              "metadata_path": "/tmp/qld-expenditure-metadata.json"
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    monkeypatch.setattr("au_politics_money.pipeline._git_commit", lambda: "def456")
    monkeypatch.setattr("au_politics_money.pipeline._dependency_versions", lambda: {})

    def fake_write_manifest(manifest):
        calls["manifest"] = manifest
        return "manifest.json"

    monkeypatch.setattr("au_politics_money.pipeline._write_manifest", fake_write_manifest)
    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_source",
        lambda source: f"fetch:{source.source_id}",
    )

    def fake_fetch_qld_exports(*, page_metadata_paths):
        calls["export_page_metadata_paths"] = sorted(page_metadata_paths)
        return export_summary_path

    def fake_normalize_qld_money(*, export_metadata_paths):
        calls["money_export_metadata_paths"] = sorted(export_metadata_paths)
        return "qld-money-flow-summary"

    def fake_normalize_qld_participants(*, lookup_metadata_paths):
        calls["participant_lookup_metadata_paths"] = sorted(lookup_metadata_paths)
        return "qld-participant-summary"

    def fake_normalize_qld_contexts(*, lookup_metadata_paths):
        calls["context_lookup_metadata_paths"] = sorted(lookup_metadata_paths)
        return "qld-context-summary"

    monkeypatch.setattr(
        "au_politics_money.pipeline.fetch_qld_ecq_eds_exports",
        fake_fetch_qld_exports,
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_qld_ecq_eds_money_flows",
        fake_normalize_qld_money,
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_qld_ecq_eds_participants",
        fake_normalize_qld_participants,
    )
    monkeypatch.setattr(
        "au_politics_money.pipeline.normalize_qld_ecq_eds_contexts",
        fake_normalize_qld_contexts,
    )

    assert run_state_local_pipeline(jurisdiction="Queensland", smoke=True) == "manifest.json"

    manifest = calls["manifest"]
    assert manifest.pipeline_name == "state_local"
    assert manifest.git_commit == "def456"
    assert manifest.parameters["jurisdiction"] == "qld"
    assert manifest.parameters["source_family"] == "qld_ecq_eds"
    assert manifest.parameters["loads_database"] is False
    assert manifest.parameters["smoke"] is True

    assert [step.name for step in manifest.steps] == [
        "fetch_qld_ecq_form_and_lookup_sources",
        "fetch_qld_ecq_eds_exports",
        "normalize_qld_ecq_eds_money_flows",
        "normalize_qld_ecq_eds_participants",
        "normalize_qld_ecq_eds_contexts",
    ]
    fetched_sources = set(manifest.steps[0].output["metadata_paths"].values())
    assert "fetch:qld_ecq_eds_public_map" in fetched_sources
    assert "fetch:qld_ecq_eds_expenditures" in fetched_sources
    assert "fetch:qld_ecq_eds_api_political_parties" in fetched_sources
    assert "fetch:qld_ecq_eds_api_local_electorates" in fetched_sources
    assert calls["export_page_metadata_paths"] == [
        "qld_ecq_eds_expenditures",
        "qld_ecq_eds_public_map",
    ]
    assert calls["money_export_metadata_paths"] == [
        "qld_ecq_eds_expenditure_export_csv",
        "qld_ecq_eds_map_export_csv",
    ]
    assert "qld_ecq_eds_api_political_parties" in calls["participant_lookup_metadata_paths"]
    assert "qld_ecq_eds_api_local_electorates" in calls["context_lookup_metadata_paths"]


def test_state_local_pipeline_rejects_unsupported_jurisdiction() -> None:
    with pytest.raises(ValueError, match="Unsupported state/local jurisdiction"):
        run_state_local_pipeline(jurisdiction="nsw")
