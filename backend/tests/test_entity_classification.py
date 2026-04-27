import json
from pathlib import Path

from au_politics_money.ingest.entity_classification import (
    aggregate_entity_names,
    classify_entity_names,
    classify_name,
)


def test_classify_name_assigns_clear_public_interest_sectors() -> None:
    assert classify_name("Westpac Banking Corporation")["public_sector"] == "banking"
    assert classify_name("Sino Iron Pty Ltd & Korean Steel Pty Ltd")["public_sector"] == "mining"
    assert classify_name("Australian Electoral Commission")["public_sector"] == "government_owned"
    assert classify_name("New South Wales Nurses and Midwives' Association")["public_sector"] == "unions"
    assert classify_name("Qantas Airways")["public_sector"] == "aviation"


def test_classify_name_avoids_known_false_positive_shapes() -> None:
    assert classify_name("Darwin Party Hire")["public_sector"] != "political_entity"
    assert classify_name("Donor - Asylum Seekers Resource Centre")["public_sector"] != "mining"
    assert classify_name("NOVOTEL BRISBANE SOUTH BANK")["public_sector"] != "banking"


def test_classify_name_keeps_individuals_uncoded() -> None:
    result = classify_name("Andrew & Nicola Forrest")

    assert result["entity_type"] == "individual"
    assert result["public_sector"] == "individual_uncoded"
    assert result["review_recommended"] is True


def test_classify_entity_names_writes_artifact_from_processed_inputs(tmp_path: Path) -> None:
    money_dir = tmp_path / "aec_annual_money_flows"
    money_dir.mkdir()
    (money_dir / "20260427T000000Z.jsonl").write_text(
        json.dumps(
            {
                "source_raw_name": "Westpac Banking Corporation",
                "recipient_raw_name": "Australian Labor Party",
                "amount_aud": "100.50",
                "source_id": "aec",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    house_dir = tmp_path / "house_interest_records"
    house_dir.mkdir()
    (house_dir / "20260427T000000Z.jsonl").write_text(
        json.dumps(
            {
                "counterparty_raw_name": "Qantas Airways",
                "source_id": "house",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    aggregates = aggregate_entity_names(processed_dir=tmp_path)
    assert set(aggregates) == {
        "australian labor party",
        "qantas airways",
        "westpac banking corporation",
    }

    summary_path = classify_entity_names(processed_dir=tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    records = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert summary["entity_name_count"] == 3
    assert summary["public_sector_counts"]["banking"] == 1
    assert summary["public_sector_counts"]["aviation"] == 1
    assert {record["classifier_name"] for record in records} == {"public_interest_sector_rules_v1"}
