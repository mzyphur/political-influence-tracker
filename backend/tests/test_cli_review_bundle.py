from __future__ import annotations

import json
from pathlib import Path

from au_politics_money import cli


class DummyConnection:
    pass


class DummyConnect:
    def __enter__(self) -> DummyConnection:
        return DummyConnection()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_prepare_review_bundle_exports_all_release_review_queues(
    monkeypatch,
    tmp_path: Path,
) -> None:
    exported_queues: list[tuple[str, int | None]] = []

    def fake_export_review_queue(conn, queue_name: str, limit: int | None = None) -> Path:
        exported_queues.append((queue_name, limit))
        return tmp_path / f"{queue_name}.summary.json"

    monkeypatch.setattr(cli, "AUDIT_DIR", tmp_path)
    monkeypatch.setattr(cli, "connect", lambda: DummyConnect())
    monkeypatch.setattr(
        cli,
        "materialize_party_entity_link_candidates",
        lambda conn, limit_per_party=None: {
            "status": "ok",
            "limit_per_party": limit_per_party,
        },
    )
    monkeypatch.setattr(cli, "export_review_queue", fake_export_review_queue)
    monkeypatch.setattr(
        cli,
        "export_sector_policy_link_suggestions",
        lambda limit=None: tmp_path / "sector-policy-suggestions.summary.json",
    )

    assert cli.prepare_review_bundle_command(limit=25, limit_per_party=3) == 0

    assert exported_queues == [
        ("official-match-candidates", 25),
        ("benefit-events", 25),
        ("entity-classifications", 25),
        ("party-entity-links", 25),
        ("sector-policy-links", 25),
    ]
    manifests = list((tmp_path / "review_bundles").glob("federal_review_bundle_*.summary.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["benefit_event_queue_summary_path"].endswith(
        "benefit-events.summary.json"
    )
    assert manifest["official_match_queue_summary_path"].endswith(
        "official-match-candidates.summary.json"
    )
    assert manifest["entity_classification_queue_summary_path"].endswith(
        "entity-classifications.summary.json"
    )
    assert manifest["party_entity_queue_summary_path"].endswith(
        "party-entity-links.summary.json"
    )
    assert manifest["sector_policy_queue_summary_path"].endswith(
        "sector-policy-links.summary.json"
    )
    assert manifest["party_entity_materialize_summary"]["limit_per_party"] == 3
