import csv
import io
import json
import zipfile
from pathlib import Path

from au_politics_money.ingest.aec_election import (
    normalize_aec_election_money_flows,
    summarize_aec_election_zip,
)


def _write_csv(zip_file: zipfile.ZipFile, name: str, rows: list[dict[str, str]]) -> None:
    if not rows:
        zip_file.writestr(name, "")
        return

    fieldnames = list(rows[0])
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    zip_file.writestr(name, buffer.getvalue())


def _write_source_zip(raw_dir: Path) -> None:
    source_dir = raw_dir / "aec_download_all_election_data" / "20260428T000000Z"
    source_dir.mkdir(parents=True)
    zip_path = source_dir / "body.zip"
    with zipfile.ZipFile(zip_path, "w") as zip_file:
        _write_csv(
            zip_file,
            "Donor Donations Made.csv",
            [
                {
                    "Event": "2025 Federal Election",
                    "Donor Code": "DON123",
                    "Donor Name": "Example Holdings Pty Ltd",
                    "Donated To": "Example Party",
                    "Donated To Date Of Gift": "14/04/2025",
                    "Donated To Gift Value": "$1,200",
                }
            ],
        )
        _write_csv(
            zip_file,
            "Media Advertisement Details.csv",
            [
                {
                    "Event": "2025 Federal Election",
                    "Media ID": "MED99",
                    "Name": "Example Media",
                    "Business Name": "Example Media Pty Ltd",
                    "Return Type": "Broadcaster",
                    "Advertiser": "Example Party",
                    "Advertiser Type": "Political Party",
                    "Date Run": "18/04/2025",
                    "Amount": "$2,500.50",
                }
            ],
        )
        _write_csv(
            zip_file,
            "Senate Groups and Candidate Discretionary Benefits.csv",
            [
                {
                    "Event": "2025 Federal Election",
                    "Return Type (Candidate/Senate Group)": "Candidate",
                    "Name": "Candidate Example",
                    "Discretionary Benefits Received From": "Benefit Provider Pty Ltd",
                    "Date": "21/04/2025",
                    "Amount": "300",
                }
            ],
        )
        _write_csv(
            zip_file,
            "Senate Groups and Candidate Donations.csv",
            [
                {
                    "Event": "2025 Federal Election",
                    "Return Type (Candidate/Senate Group)": "Candidate",
                    "Name": "Example Party",
                    "Donor Name": "Example Holdings Pty Ltd",
                    "Date Of Gift": "14/04/2025",
                    "Gift Value": "$1,200",
                }
            ],
        )
        _write_csv(
            zip_file,
            "Donor Return.csv",
            [
                {
                    "Event": "2025 Federal Election",
                    "Donor Code": "DON123",
                    "Donor Name": "Example Holdings Pty Ltd",
                }
            ],
        )

    metadata = {
        "body_path": str(zip_path),
        "source": {
            "source_id": "aec_download_all_election_data",
            "name": "AEC election data",
        },
        "fetched_at": "20260428T000000Z",
    }
    (source_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")


def test_summarize_aec_election_zip_marks_normalized_tables(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_source_zip(raw_dir)

    summary_path = summarize_aec_election_zip(raw_dir=raw_dir, processed_dir=processed_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert "Donor Donations Made.csv" in summary["normalized_tables"]
    assert summary["table_count"] == 5


def test_normalize_aec_election_money_flows_excludes_aggregate_tables(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_source_zip(raw_dir)

    summary_path = normalize_aec_election_money_flows(raw_dir=raw_dir, processed_dir=processed_dir)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    jsonl_path = Path(summary["jsonl_path"])
    records = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert summary["total_count"] == 4
    assert summary["duplicate_transaction_group_count"] == 1
    assert summary["duplicate_observation_count"] == 1
    assert "Donor Return.csv" in summary["aggregate_tables_intentionally_not_normalized"]
    assert {record["source_table"] for record in records} == {
        "Donor Donations Made.csv",
        "Media Advertisement Details.csv",
        "Senate Groups and Candidate Discretionary Benefits.csv",
        "Senate Groups and Candidate Donations.csv",
    }
    donor_made = next(record for record in records if record["source_table"] == "Donor Donations Made.csv")
    candidate_donation = next(
        record for record in records if record["source_table"] == "Senate Groups and Candidate Donations.csv"
    )
    assert donor_made["canonical_transaction_key"] == candidate_donation["canonical_transaction_key"]
    assert donor_made["public_amount_counting_role"] == "duplicate_observation"
    assert candidate_donation["public_amount_counting_role"] == "primary_transaction"
    benefit = next(
        record
        for record in records
        if record["source_table"] == "Senate Groups and Candidate Discretionary Benefits.csv"
    )
    assert benefit["flow_kind"] == "election_candidate_or_senate_group_discretionary_benefit"
    assert benefit["receipt_type"] == "Discretionary Benefit"
    media = next(
        record for record in records if record["source_table"] == "Media Advertisement Details.csv"
    )
    assert media["receipt_type"] == "Media Advertisement"
    assert media["amount_aud"] == "2500.50"
