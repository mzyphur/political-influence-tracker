from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.sa_ecsa import (
    BASE_URL,
    SOURCE_ID,
    normalize_sa_ecsa_return_index,
)


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture_metadata(tmp_path: Path, *, body_html: str, reported_count: int) -> Path:
    page_path = tmp_path / "page_001.html"
    page_path.write_text(body_html, encoding="utf-8")
    body_manifest_path = tmp_path / "body.json"
    body_manifest = {
        "source_id": SOURCE_ID,
        "portal_record_count_reported": reported_count,
        "expected_page_count": 1,
        "fetched_page_count": 1,
        "complete_page_coverage": True,
        "pages": [
            {
                "page": 1,
                "url": BASE_URL,
                "sha256": _sha256_path(page_path),
                "body_path": str(page_path),
            }
        ],
    }
    body_manifest_path.write_text(
        json.dumps(body_manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata = {
        "source": {"source_id": SOURCE_ID},
        "body_path": str(body_manifest_path),
        "sha256": _sha256_path(body_manifest_path),
        **body_manifest,
    }
    metadata_path.write_text(json.dumps(metadata, sort_keys=True) + "\n", encoding="utf-8")
    return metadata_path


def _return_index_html(*, rows: str) -> str:
    return f"""
    <html>
      <body>
        <p>2 records returned</p>
        <table>
          <tr>
            <th>Return Type</th>
            <th>Date Lodged</th>
            <th>Submitter</th>
            <th>For</th>
            <th>Recipient</th>
            <th>From</th>
            <th>To</th>
            <th>Value</th>
            <th>Reports</th>
          </tr>
          {rows}
        </table>
      </body>
    </html>
    """


def test_normalize_sa_ecsa_return_index_extracts_return_summary_rows(tmp_path) -> None:
    metadata_path = _write_fixture_metadata(
        tmp_path,
        reported_count=2,
        body_html=_return_index_html(
            rows="""
            <tr>
              <td>Candidate Campaign Donations Return</td>
              <td>24-04-2026</td>
              <td>Ross Kassebaum</td>
              <td>Craig Haslam</td>
              <td>Craig Haslam</td>
              <td>01/01/2026</td>
              <td>31/01/2026</td>
              <td>$12,527.00</td>
              <td><a href="view.php?ID=1038">View</a></td>
            </tr>
            <tr>
              <td>Political Party Return</td>
              <td>15/04/2026</td>
              <td>Party Agent</td>
              <td>Example Party</td>
              <td></td>
              <td>01/07/2025</td>
              <td>31/12/2025</td>
              <td>$1,000.50</td>
              <td><a href="view.php?ID=1040">View</a></td>
            </tr>
            """,
        ),
    )

    summary_path = normalize_sa_ecsa_return_index(
        metadata_path=metadata_path,
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_count"] == 2
    assert summary["portal_record_count_reported"] == 2
    assert summary["reported_amount_total"] == "13527.50"
    assert summary["flow_kind_counts"] == {
        "sa_candidate_campaign_donations_return_summary": 1,
        "sa_political_party_return_summary": 1,
    }
    rows = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["amount_aud"] == "12527.00"
    assert rows[0]["date_reported"] == "2026-04-24"
    assert rows[0]["reporting_period_start"] == "2026-01-01"
    assert rows[0]["report_url"] == f"{BASE_URL.rsplit('/', 1)[0]}/view.php?ID=1038"
    assert rows[0]["public_amount_counting_role"] == (
        "jurisdictional_cross_disclosure_observation"
    )
    assert rows[0]["source_actor_role"] == "submitter_or_agent"
    assert "not an individual donor-to-recipient transaction" in rows[0]["claim_boundary"]


def test_normalize_sa_ecsa_return_index_fails_closed_on_row_count_mismatch(tmp_path) -> None:
    metadata_path = _write_fixture_metadata(
        tmp_path,
        reported_count=2,
        body_html=_return_index_html(
            rows="""
            <tr>
              <td>Donor Return</td>
              <td>24-04-2026</td>
              <td>Donor Name</td>
              <td>Recipient Name</td>
              <td>Recipient Name</td>
              <td>01/01/2026</td>
              <td>31/01/2026</td>
              <td>$500.00</td>
              <td><a href="view.php?ID=1039">View</a></td>
            </tr>
            """,
        ),
    )

    with pytest.raises(ValueError, match="row count mismatch"):
        normalize_sa_ecsa_return_index(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )
