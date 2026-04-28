from __future__ import annotations

import json

from au_politics_money.ingest.aec_public_funding import normalize_aec_public_funding


def test_normalize_aec_public_funding_payment_tables(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    source_dir = raw_dir / "aec_2025_federal_election_funding_finalised" / "20260428T000000Z"
    source_dir.mkdir(parents=True)
    body_path = source_dir / "body.html"
    body_path.write_text(
        """
        <html>
          <head><title>2025 federal election: election funding payments finalised</title></head>
          <body>
            <h1>2025 federal election: election funding payments finalised</h1>
            <p>Updated: 27 November 2025</p>
            <h2>Political parties</h2>
            <table>
              <tr><th>Political Party</th><th>Total Election Funding Paid</th></tr>
              <tr><td>Australian Labor Party (Federal)</td><td>$36,999,384.08</td></tr>
              <tr><td>Total</td><td>$90,500,451.00</td></tr>
            </table>
            <h2>Independent Candidates</h2>
            <table>
              <tr><th>Independent Candidate</th><th>Total Election Funding Paid</th></tr>
              <tr><td>Zali Steggall</td><td>$154,367.74</td></tr>
            </table>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    metadata_path = source_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps({"body_path": str(body_path), "source": {"source_id": "fixture"}}),
        encoding="utf-8",
    )

    summary_path = normalize_aec_public_funding(raw_dir=raw_dir, processed_dir=processed_dir)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["total_count"] == 2
    assert summary["event_name"] == "2025 Federal Election"
    assert summary["updated_date"] == "27/11/2025"

    records = [
        json.loads(line)
        for line in summary_path.with_suffix("").with_suffix(".jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    party_record = records[0]
    assert party_record["flow_kind"] == "election_public_funding_paid"
    assert party_record["recipient_role"] == "political_party"
    assert party_record["recipient_raw_name"] == "Australian Labor Party (Federal)"
    assert party_record["amount_aud"] == "36999384.08"
    assert party_record["campaign_support_attribution"]["tier"] == (
        "party_aggregate_public_funding_paid"
    )
    independent_record = records[1]
    assert independent_record["recipient_role"] == "independent_candidate"
    assert independent_record["amount_aud"] == "154367.74"
