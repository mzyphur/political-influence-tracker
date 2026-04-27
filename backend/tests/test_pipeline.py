from au_politics_money.pipeline import PipelineManifest


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

