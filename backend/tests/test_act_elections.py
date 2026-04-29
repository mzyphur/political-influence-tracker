import hashlib
import json
from pathlib import Path

import pytest

from au_politics_money.ingest.act_elections import (
    normalize_act_annual_return_receipts,
    normalize_act_gift_returns,
)


ACT_HEADERS = """
<thead>
  <tr>
    <th>From</th>
    <th>Date reported to Elections ACT</th>
    <th>Date gift received</th>
    <th>Amount</th>
    <th>Type</th>
    <th>Description of gift-in-kind</th>
  </tr>
</thead>
"""


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_act_metadata(tmp_path: Path, body: str, *, source_id: str = "act_gift_returns_2025_2026") -> Path:
    body_path = tmp_path / "body.html"
    body_path.write_text(body, encoding="utf-8")
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "sha256": sha256_path(body_path),
                "source": {
                    "source_id": source_id,
                    "name": "Elections ACT Gift Returns 2025-2026",
                    "url": "https://www.elections.act.gov.au/funding-disclosures-and-registers/gift-returns/gift-returns-2025-2026",
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_act_annual_return_receipts_extracts_mla_gift_in_kind(
    tmp_path: Path,
) -> None:
    html = """
    <html><body>
      <h1>2024/2025 annual returns</h1>
      <h2>MLAs</h2>
      <h3>MLAs - Receipts totalling $1,000 or more</h3>
      <h4>Barr, Andrew - Receipts totalling $1,000 or more</h4>
      <table><thead><tr>
        <th>Received from</th>
        <th>Address</th>
        <th>Receipt type</th>
        <th>Amount</th>
      </tr></thead><tbody>
        <tr>
          <td>Tennis Australia ABN: 61006281125</td>
          <td>Olympic Boulevard MELBOURNE PARK VIC 3000</td>
          <td>Gift in kind</td>
          <td>$2,269.00</td>
        </tr>
        <tr><th>Totals</th><th></th><th></th><th>$2,269.00</th></tr>
      </tbody></table>
      <h2>Political Parties</h2>
      <h3>Political Parties - Receipts totalling $1,000 or more</h3>
      <h4>Australian Labor Party (ACT Branch) - Receipts totalling $1,000 or more</h4>
      <table><thead><tr>
        <th>Received from</th>
        <th>Address</th>
        <th>Receipt type</th>
        <th>Amount</th>
      </tr></thead><tbody>
        <tr>
          <td>Canberra Labor Club ABN: 92 008 546 030</td>
          <td>BELCONNEN ACT 2617</td>
          <td>Free facilities use</td>
          <td>$13,668.50</td>
        </tr>
      </tbody></table>
    </body></html>
    """
    metadata_path = write_act_metadata(
        tmp_path,
        html,
        source_id="act_annual_returns_2024_2025",
    )

    summary_path = normalize_act_annual_return_receipts(
        metadata_path=metadata_path,
        raw_dir=tmp_path,
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["source_dataset"] == "act_elections_annual_returns"
    assert summary["source_id"] == "act_annual_returns_2024_2025"
    assert summary["total_count"] == 2
    assert summary["flow_kind_counts"] == {
        "act_annual_free_facilities_use": 1,
        "act_annual_gift_in_kind": 1,
    }
    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[0]["recipient_raw_name"] == "Barr, Andrew"
    assert records[0]["source_raw_name"] == "Tennis Australia"
    assert records[0]["source_abn_or_acn"]["value"] == "61006281125"
    assert records[0]["flow_kind"] == "act_annual_gift_in_kind"
    assert records[0]["amount_aud"] == "2269.00"
    assert records[0]["recipient_context"] == "MLAs"
    assert records[1]["flow_kind"] == "act_annual_free_facilities_use"
    assert "not claims of wrongdoing" in records[1]["claim_boundary"]


def test_normalize_act_gift_returns_extracts_money_and_gift_in_kind(tmp_path: Path) -> None:
    html = f"""
    <html><body>
      <h2>Gifts received by Australian Labor Party (ACT Branch)</h2>
      <table>{ACT_HEADERS}<tbody>
        <tr>
          <td>Example Donor Pty Ltd<br>Canberra ACT 2600</td>
          <td>2 July 2025</td>
          <td>1 July 2025</td>
          <td>$1,500.00</td>
          <td>Gift of money</td>
          <td></td>
        </tr>
      </tbody></table>
      <h2>Gifts received by Emerson, Thomas</h2>
      <table>{ACT_HEADERS}<tbody>
        <tr>
          <td>Events Company<br>PO Box 1<br>Canberra ACT 2601</td>
          <td>4 August 2025</td>
          <td>3 August 2025</td>
          <td>$2,250</td>
          <td>Gift in kind</td>
          <td>GIK-Event Tickets</td>
        </tr>
      </tbody></table>
    </body></html>
    """
    metadata_path = write_act_metadata(tmp_path, html)

    summary_path = normalize_act_gift_returns(
        metadata_path=metadata_path,
        raw_dir=tmp_path,
        processed_dir=tmp_path / "processed",
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["source_dataset"] == "act_elections_gift_returns"
    assert summary["source_id"] == "act_gift_returns_2025_2026"
    assert summary["total_count"] == 2
    assert summary["source_counts"] == {"act_gift_returns_2025_2026": 2}
    assert summary["flow_kind_counts"] == {
        "act_gift_in_kind": 1,
        "act_gift_of_money": 1,
    }
    assert summary["source_body_sha256"] == sha256_path(Path(json.loads(metadata_path.read_text())["body_path"]))
    assert summary["source_metadata_sha256"] == sha256_path(metadata_path)
    assert summary["jsonl_sha256"] == sha256_path(Path(summary["jsonl_path"]))

    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert records[0]["source_raw_name"] == "Example Donor Pty Ltd"
    assert records[0]["recipient_raw_name"] == "Australian Labor Party (ACT Branch)"
    assert records[0]["amount_aud"] == "1500.00"
    assert records[0]["flow_kind"] == "act_gift_of_money"
    assert records[0]["date"] == "2025-07-01"
    assert records[0]["date_reported"] == "2025-07-02"
    assert records[1]["source_raw_name"] == "Events Company"
    assert records[1]["recipient_raw_name"] == "Emerson, Thomas"
    assert records[1]["amount_aud"] == "2250"
    assert records[1]["flow_kind"] == "act_gift_in_kind"
    assert records[1]["description"] == "GIK-Event Tickets"
    assert "PO Box 1" in records[1]["donor_address_public"]
    assert "non-cash benefit" in records[1]["claim_boundary"]
    assert "cumulative gifts from one donor" in records[1]["disclosure_threshold"]


def test_normalize_act_gift_returns_fails_when_no_rows(tmp_path: Path) -> None:
    metadata_path = write_act_metadata(tmp_path, "<html><body><h1>No rows</h1></body></html>")

    with pytest.raises(ValueError, match="No ACT gift-return rows extracted"):
        normalize_act_gift_returns(
            metadata_path=metadata_path,
            raw_dir=tmp_path,
            processed_dir=tmp_path / "processed",
        )


def test_normalize_act_gift_returns_verifies_body_hash(tmp_path: Path) -> None:
    metadata_path = write_act_metadata(tmp_path, "<html><body><h2>Changed later</h2></body></html>")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    Path(metadata["body_path"]).write_text("<html>tampered</html>", encoding="utf-8")

    with pytest.raises(ValueError, match="body hash mismatch"):
        normalize_act_gift_returns(
            metadata_path=metadata_path,
            raw_dir=tmp_path,
            processed_dir=tmp_path / "processed",
        )


def test_normalize_act_gift_returns_rejects_changed_headers(tmp_path: Path) -> None:
    html = """
    <html><body>
      <h2>Gifts received by The ACT Greens</h2>
      <table><thead><tr><th>Unexpected</th></tr></thead><tbody>
        <tr>
          <td>Example Donor</td>
          <td>2 July 2025</td>
          <td>1 July 2025</td>
          <td>$500</td>
          <td>Gift of money</td>
          <td></td>
        </tr>
      </tbody></table>
    </body></html>
    """
    metadata_path = write_act_metadata(tmp_path, html)

    with pytest.raises(ValueError, match="Unexpected ACT gift-return table headers"):
        normalize_act_gift_returns(
            metadata_path=metadata_path,
            raw_dir=tmp_path,
            processed_dir=tmp_path / "processed",
        )
