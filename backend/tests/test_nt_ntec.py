import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.nt_ntec import normalize_nt_ntec_annual_gifts


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_normalize_nt_ntec_annual_gifts_extracts_recipient_side_gifts(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "ntec.html"
    body_path.write_text(
        """
        <html><body>
          <h1>2024-2025 annual returns - gifts</h1>
          <h3>Political Parties - Return details</h3>
          <table>
            <tr><th>Name</th><th>Date received</th></tr>
            <tr><td>Australian Labor Party NT Branch</td><td>29 Jul 2025</td></tr>
          </table>
          <h3>
            Australian Labor Party NT Branch -
            Gifts received over the threshold in the disclosure period
          </h3>
          <table>
            <tr><th>Received from</th><th>Address</th><th>Amount</th></tr>
            <tr>
              <td>Tamboran Resources</td>
              <td>Lvl 39 Barangaroo NSW 2000</td>
              <td>$50,000.00</td>
            </tr>
            <tr><td>Totals</td><td></td><td>$50,000.00</td></tr>
          </table>
          <p>Last updated: 08 October 2025</p>
        </body></html>
        """,
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "sha256": sha256_path(body_path),
                "source": {"source_id": "nt_ntec_annual_returns_gifts_2024_2025"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    summary_path = normalize_nt_ntec_annual_gifts(
        metadata_path=metadata_path,
        processed_dir=tmp_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["source_dataset"] == "nt_ntec_annual_returns_gifts"
    assert summary["total_count"] == 1
    assert summary["flow_kind_counts"] == {"nt_annual_gift": 1}

    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["source_raw_name"] == "Tamboran Resources"
    assert records[0]["recipient_raw_name"] == "Australian Labor Party NT Branch"
    assert records[0]["amount_aud"] == "50000.00"
    assert records[0]["date"] == ""
    assert records[0]["date_reported"] == "2025-07-29"
    assert records[0]["doc_last_updated"] == "2025-10-08"
    assert "not gift transaction date" in records[0]["date_caveat"]
    assert records[0]["public_amount_counting_role"] == (
        "jurisdictional_cross_disclosure_observation"
    )
    assert records[0]["source_table_total_validated"] is True
    assert records[0]["source_table_total_aud"] == "50000.00"


def test_normalize_nt_ntec_annual_gifts_rejects_total_mismatch(
    tmp_path: Path,
) -> None:
    body_path = tmp_path / "ntec.html"
    body_path.write_text(
        """
        <html><body>
          <h3>Political Parties - Return details</h3>
          <table>
            <tr><th>Name</th><th>Date received</th></tr>
            <tr><td>NT Greens</td><td>30 Jul 2025</td></tr>
          </table>
          <h3>NT Greens - Gifts received over the threshold in the disclosure period</h3>
          <table>
            <tr><th>Received from</th><th>Address</th><th>Amount</th></tr>
            <tr><td>Example Donor</td><td>Darwin NT 0800</td><td>$1,500.00</td></tr>
            <tr><td>Totals</td><td></td><td>$2,000.00</td></tr>
          </table>
        </body></html>
        """,
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "sha256": sha256_path(body_path),
                "source": {"source_id": "nt_ntec_annual_returns_gifts_2024_2025"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="table total mismatch"):
        normalize_nt_ntec_annual_gifts(metadata_path=metadata_path, processed_dir=tmp_path)
