from __future__ import annotations

from dataclasses import asdict
import json

import pytest

from au_politics_money.ingest.nsw_electoral import (
    HEATMAP_SOURCE_ID,
    normalize_nsw_pre_election_donor_location_heatmap,
)
from au_politics_money.ingest.sources import get_source


def _write_metadata(tmp_path, body: str):
    body_path = tmp_path / "body.html"
    body_path.write_text(body, encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": asdict(get_source(HEATMAP_SOURCE_ID)),
                "fetched_at": "20260429T000000Z",
                "ok": True,
                "http_status": 200,
                "final_url": get_source(HEATMAP_SOURCE_ID).url,
                "content_type": "text/html",
                "content_length": len(body.encode("utf-8")),
                "sha256": "fixture",
                "body_path": str(body_path),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_nsw_heatmap_extracts_donor_location_aggregates(tmp_path) -> None:
    widget = {
        "x": {
            "data": [
                ["Sydney", "Interstate"],
                [1047419.07, 416040.48],
                [487, 201],
            ],
            "container": (
                "<table><thead><tr><th>District</th><th>Amount</th>"
                "<th>Count</th></tr></thead></table>"
            ),
        }
    }
    body = (
        "<html><body><script type=\"application/json\" data-for=\"widget\">"
        f"{json.dumps(widget)}"
        "</script></body></html>"
    )
    summary_path = normalize_nsw_pre_election_donor_location_heatmap(
        metadata_path=_write_metadata(tmp_path, body),
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_count"] == 2
    assert summary["donation_count_total"] == 688
    assert summary["reported_amount_total"] == "1463459.55"
    assert summary["jsonl_sha256"]

    rows = [
        json.loads(line)
        for line in open(summary["jsonl_path"], encoding="utf-8")
        if line.strip()
    ]
    assert rows[0]["geography_name"] == "Sydney"
    assert rows[0]["amount_aud"] == "1047419.07"
    assert rows[0]["donation_count"] == 487
    assert rows[0]["attribution_scope"] == "aggregate_context_not_recipient_attribution"
    assert rows[1]["geography_type"] == "interstate_donor_location"


def test_normalize_nsw_heatmap_fails_without_district_table(tmp_path) -> None:
    metadata_path = _write_metadata(tmp_path, "<html><body>No table</body></html>")

    with pytest.raises(ValueError, match="Could not find NSW heatmap district"):
        normalize_nsw_pre_election_donor_location_heatmap(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )
