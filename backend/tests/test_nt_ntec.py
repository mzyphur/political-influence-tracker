import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.nt_ntec import (
    normalize_nt_ntec_annual_gifts,
    normalize_nt_ntec_annual_returns,
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def annual_return_metadata(tmp_path: Path, body: str) -> Path:
    body_path = tmp_path / "ntec-annual.html"
    body_path.write_text(body, encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "sha256": sha256_path(body_path),
                "source": {"source_id": "nt_ntec_annual_returns_2024_2025"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


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


def test_normalize_nt_ntec_annual_returns_extracts_financial_rows(
    tmp_path: Path,
) -> None:
    metadata_path = annual_return_metadata(
        tmp_path,
        """
        <html><body>
          <h3>Political Parties - Return details</h3>
          <table>
            <tr><th>Name</th><th>Date received</th></tr>
            <tr><td>Australian Labor Party NT Branch</td><td>29 Jul 2025</td></tr>
          </table>
          <h4>Australian Labor Party NT Branch - Receipts of $1500 or more</h4>
          <table>
            <tr>
              <th>Received from</th><th>Address</th><th>Receipt type</th><th>Amount</th>
            </tr>
            <tr>
              <td>Example Union</td><td>Darwin NT 0800</td><td>Receipt</td><td>$2,000.00</td>
            </tr>
            <tr><td>Totals</td><td></td><td></td><td>$2,000.00</td></tr>
          </table>
          <h4>ALP Investment Trust Fund - Debts of $1500 or more</h4>
          <table>
            <tr><th>Name</th><th>Address</th><th>Amount</th></tr>
            <tr><td>Example Creditor</td><td>Darwin NT 0800</td><td>$1,600.00</td></tr>
            <tr><td>Totals</td><td></td><td>$1,600.00</td></tr>
          </table>
          <h4>Example Donor - Donations made to political parties and candidates</h4>
          <table>
            <tr><th>Name</th><th>Date</th><th>Amount</th></tr>
            <tr><td>NT Greens</td><td>2024/2025</td><td>$1,500.00</td></tr>
            <tr><td>Totals</td><td></td><td>$1,500.00</td></tr>
          </table>
          <p>Last updated: 08 October 2025</p>
        </body></html>
        """,
    )

    summary_path = normalize_nt_ntec_annual_returns(
        metadata_path=metadata_path,
        processed_dir=tmp_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["source_dataset"] == "nt_ntec_annual_returns"
    assert summary["flow_kind_counts"] == {
        "nt_annual_debt": 1,
        "nt_annual_receipt": 1,
        "nt_donor_return_donation": 1,
    }

    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    by_kind = {record["flow_kind"]: record for record in records}
    assert by_kind["nt_annual_receipt"]["source_raw_name"] == "Example Union"
    assert by_kind["nt_annual_receipt"]["date_reported"] == "2025-07-29"
    assert by_kind["nt_annual_debt"]["transaction_kind"] == "debt"
    assert by_kind["nt_donor_return_donation"]["reporting_period"] == "2024/2025"
    assert "annual period" in by_kind["nt_donor_return_donation"]["date_caveat"]
    assert all(
        record["public_amount_counting_role"]
        == "jurisdictional_cross_disclosure_observation"
        for record in records
    )
    assert all(record["source_table_total_validated"] is True for record in records)


def test_normalize_nt_ntec_annual_returns_rejects_missing_table_total(
    tmp_path: Path,
) -> None:
    metadata_path = annual_return_metadata(
        tmp_path,
        """
        <html><body>
          <h4>Example Party - Receipts of $1500 or more</h4>
          <table>
            <tr>
              <th>Received from</th><th>Address</th><th>Receipt type</th><th>Amount</th>
            </tr>
            <tr>
              <td>Example Donor</td><td>Darwin NT 0800</td><td>Receipt</td><td>$2,000.00</td>
            </tr>
          </table>
        </body></html>
        """,
    )

    with pytest.raises(ValueError, match="table total missing"):
        normalize_nt_ntec_annual_returns(metadata_path=metadata_path, processed_dir=tmp_path)


def test_normalize_nt_ntec_annual_returns_rejects_total_mismatch(
    tmp_path: Path,
) -> None:
    metadata_path = annual_return_metadata(
        tmp_path,
        """
        <html><body>
          <h4>Example Party - Receipts of $1500 or more</h4>
          <table>
            <tr>
              <th>Received from</th><th>Address</th><th>Receipt type</th><th>Amount</th>
            </tr>
            <tr>
              <td>Example Donor</td><td>Darwin NT 0800</td><td>Receipt</td><td>$2,000.00</td>
            </tr>
            <tr><td>Totals</td><td></td><td></td><td>$2,001.00</td></tr>
          </table>
        </body></html>
        """,
    )

    with pytest.raises(ValueError, match="table total mismatch"):
        normalize_nt_ntec_annual_returns(metadata_path=metadata_path, processed_dir=tmp_path)
