import json
from pathlib import Path

from au_politics_money.ingest.discovered_sources import child_source_id
from au_politics_money.ingest.discovery import write_discovered_links
from au_politics_money.ingest.pdf_text import latest_metadata_by_source_prefix
from au_politics_money.models import DiscoveredLink, SourceRecord


def _write_metadata(raw_dir: Path, source_id: str, run_id: str) -> Path:
    target_dir = raw_dir / source_id / run_id
    target_dir.mkdir(parents=True)
    body_path = target_dir / "body.pdf"
    body_path.write_bytes(b"%PDF-1.7\nfixture\n%%EOF")
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "ok": True,
                "body_path": str(body_path),
                "source": {"source_id": source_id, "name": source_id, "url": "https://example.test/file.pdf"},
                "sha256": "pytest",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_latest_pdf_metadata_uses_latest_discovered_manifest(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    parent = SourceRecord(
        source_id="aph_members_interests_48",
        name="House interests",
        jurisdiction="Commonwealth",
        level="federal",
        source_type="register_index",
        url="https://example.test/interests",
        expected_format="html",
        update_frequency="when_changed",
        priority="high",
        notes="pytest",
    )
    active_link = DiscoveredLink(
        parent_source_id=parent.source_id,
        title="Active PDF",
        url="https://example.test/active.pdf",
        link_type="pdf",
    )
    stale_link = DiscoveredLink(
        parent_source_id=parent.source_id,
        title="Withdrawn PDF",
        url="https://example.test/withdrawn.pdf",
        link_type="pdf",
    )
    active_source_id = child_source_id(parent.source_id, active_link)
    stale_source_id = child_source_id(parent.source_id, stale_link)
    _write_metadata(raw_dir, active_source_id, "20260429T000000Z")
    _write_metadata(raw_dir, stale_source_id, "20260429T000000Z")
    write_discovered_links(parent, [active_link], processed_dir=processed_dir)

    metadata_paths, selection = latest_metadata_by_source_prefix(
        "aph_members_interests_48__",
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    assert [path.parent.parent.name for path in metadata_paths] == [active_source_id]
    assert selection["restricted_to_latest_discovery"] is True
    assert selection["active_discovered_source_count"] == 1
    assert selection["inactive_cached_source_count"] == 1
