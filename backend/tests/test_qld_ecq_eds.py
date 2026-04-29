import json
from pathlib import Path

from au_politics_money.ingest.qld_ecq_eds import (
    form_fields_from_html,
    normalize_qld_ecq_eds_contexts,
    normalize_qld_ecq_eds_money_flows,
    normalize_qld_ecq_eds_participants,
)


def test_form_fields_from_html_preserves_selected_values_and_hidden_inputs() -> None:
    html = """
    <html>
      <body>
        <form id="root" method="post">
          <input type="hidden" name="ViewFilter.View" value="Table" />
          <input type="text" name="ViewFilter.Search" value="donor" />
          <input type="submit" name="ignored" value="Search" />
          <input type="checkbox" name="ViewFilter.HasEnablingGift" value="true" checked />
          <input type="checkbox" name="unchecked" value="false" />
          <select name="ViewFilter.GovernmentType">
            <option value="State">State</option>
            <option value="Local" selected>Local</option>
          </select>
          <textarea name="ViewFilter.Description">  test text  </textarea>
        </form>
      </body>
    </html>
    """

    fields = form_fields_from_html(html)

    assert fields == [
        ("ViewFilter.View", "Table"),
        ("ViewFilter.Search", "donor"),
        ("ViewFilter.HasEnablingGift", "true"),
        ("ViewFilter.GovernmentType", "Local"),
        ("ViewFilter.Description", "test text"),
    ]


def _write_raw_csv(raw_dir: Path, source_id: str, csv_text: str) -> Path:
    target_dir = raw_dir / source_id / "20260429T000000Z"
    target_dir.mkdir(parents=True)
    body_path = target_dir / "body.csv"
    body_path.write_text(csv_text, encoding="utf-8")
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "content_type": "text/csv",
                "fetched_at": "20260429T000000Z",
                "ok": True,
                "source": {"source_id": source_id},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def _write_raw_json(raw_dir: Path, source_id: str, payload: object) -> Path:
    target_dir = raw_dir / source_id / "20260429T000000Z"
    target_dir.mkdir(parents=True)
    body_path = target_dir / "body.json"
    body_path.write_text(json.dumps(payload), encoding="utf-8")
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "content_type": "application/json",
                "fetched_at": "20260429T000000Z",
                "ok": True,
                "source": {"source_id": source_id},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_qld_ecq_eds_money_flows(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_raw_csv(
        raw_dir,
        "qld_ecq_eds_map_export_csv",
        (
            "Donor,Recipient,Election,Date Gift Made,Gift value,Political donation,"
            "Electoral committee,Name of electoral committee\n"
            "Donor Pty Ltd,Recipient Party,2028 Local Government Elections,28-04-2026,"
            "300.00,Yes,,\n"
            "State Donor Pty Ltd,State Recipient Party,,28-04-2026,400.00,No,,\n"
        ),
    )
    _write_raw_csv(
        raw_dir,
        "qld_ecq_eds_expenditure_export_csv",
        (
            "Incurred By,Value,Date Incurred,Candidate Type,Local Electorate,Election,"
            "Description of Goods or Services,Purpose of the Expenditure\n"
            "Candidate Name,25.52,29/03/2026,Announced Candidate,Whitsunday Regional,"
            "2028 Local Government Elections,Advertising,Advertising\n"
        ),
    )

    summary_path = normalize_qld_ecq_eds_money_flows(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert summary["total_count"] == 3
    assert records[0]["source_dataset"] == "qld_ecq_eds"
    assert records[0]["receipt_type"] == "Political Donation"
    assert records[0]["amount_aud"] == "300.00"
    assert records[0]["jurisdiction_name"] == "Queensland local governments"
    assert records[0]["jurisdiction_level"] == "local"
    assert records[0]["jurisdiction_code"] == "QLD-LOCAL"
    assert records[1]["jurisdiction_name"] == "Queensland"
    assert records[1]["jurisdiction_level"] == "state"
    assert records[1]["jurisdiction_code"] == "QLD"
    assert records[2]["flow_kind"] == "qld_electoral_expenditure"
    assert records[2]["jurisdiction_level"] == "local"
    assert records[2]["campaign_support_attribution"]["not_personal_receipt"] is True


def test_normalize_qld_ecq_eds_participants(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_political_electors",
        [{"electorId": 123, "fullName": "Candidate Name"}],
    )
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_political_parties",
        [{"politicalPartyId": 456, "partyName": "Example Party (Queensland)"}],
    )
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_associated_entities",
        [{"organisationId": 789, "name": "Example Associated Entity Pty Ltd"}],
    )
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_local_groups",
        [{"localGroupId": 321, "name": "Example Local Group"}],
    )

    summary_path = normalize_qld_ecq_eds_participants(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert summary["total_count"] == 4
    assert records[0]["source_record_type"] == "qld_ecq_political_elector"
    assert records[0]["identifiers"] == [
        {"identifier_type": "qld_ecq_elector_id", "identifier_value": "123"}
    ]
    assert records[1]["aliases"] == ["Example Party"]
    assert records[1]["normalized_name"] == "example party queensland"


def test_normalize_qld_ecq_eds_contexts(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_political_events",
        [
            {
                "eventId": 636,
                "name": "2028 Local Government Elections",
                "code": "LGE2028",
                "eventType": "Local Government Election",
                "isState": False,
                "pollingDate": "2028-03-25T00:00:00",
            },
            {
                "eventId": 100,
                "name": "2026 Stafford State By-election",
                "code": "STAFFORD2026",
                "eventType": "State By-election",
                "isState": True,
                "pollingDate": "2026-04-18T00:00:00",
            },
        ],
    )
    _write_raw_json(
        raw_dir,
        "qld_ecq_eds_api_local_electorates",
        [{"localElectorateId": 777, "localElectorateName": "Whitsunday Regional"}],
    )

    summary_path = normalize_qld_ecq_eds_contexts(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]
    assert summary["total_count"] == 3
    assert summary["context_type_counts"] == {"local_electorate": 1, "political_event": 2}
    assert records[0]["context_type"] == "political_event"
    assert records[0]["external_id"] == "636"
    assert records[0]["level"] == "council"
    assert records[0]["identifier"] == {
        "identifier_type": "qld_ecq_event_id",
        "identifier_value": "636",
    }
    assert records[1]["level"] == "state"
    assert records[2]["context_type"] == "local_electorate"
    assert records[2]["identifier"] == {
        "identifier_type": "qld_ecq_local_electorate_id",
        "identifier_value": "777",
    }
