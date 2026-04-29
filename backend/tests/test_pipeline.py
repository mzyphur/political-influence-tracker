from au_politics_money.pipeline import PipelineManifest, run_federal_foundation_pipeline


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
