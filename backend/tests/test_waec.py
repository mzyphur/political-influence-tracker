import json
from pathlib import Path

import pytest

from au_politics_money.ingest.waec import (
    _date_string,
    normalize_waec_political_contributions,
)


def _sha256_path(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _attr(name: str, display: str, value=None):
    if value is None:
        value = display
    return {
        "Name": name,
        "DisplayValue": display,
        "FormattedValue": display,
        "Value": value,
    }


def _lookup_attr(name: str, display: str, external_id: str):
    return _attr(
        name,
        display,
        {
            "Id": external_id,
            "LogicalName": "account",
            "Name": display,
            "KeyAttributes": [],
            "RowVersion": None,
            "ExtensionData": None,
        },
    )


def _write_waec_fixture(
    tmp_path: Path,
    *,
    row_overrides=None,
    item_count: int = 1,
    record_count: int = 1,
) -> Path:
    page_path = tmp_path / "page.json"
    row = {
        "Id": "wa-row-1",
        "EntityName": "waec_disclosure",
        "Attributes": [
            _attr("waec_datedisclosurereceived", "4/27/2026", "/Date(1777305600000)/"),
            _lookup_attr("waec_donorid", "Example Donor Pty Ltd", "donor-1"),
            _attr(
                "a_f9c48d73871b443ba59c75ceb843e999.waec_publicpostcode",
                "6000",
            ),
            _attr("waec_amount", "$1,234.50", {"Value": 1234.5}),
            _lookup_attr(
                "waec_politicalentityaccountid",
                "Example Party WA",
                "entity-1",
            ),
            _attr("waec_politicalcontributiontype", "Gift"),
            _attr("waec_disclosureversiontype", "Original"),
            _lookup_attr("waec_financialyearid", "2025-2026", "fy-1"),
            _attr("statuscode", "Published"),
            _lookup_attr("transactioncurrencyid", "Australian Dollar", "aud-1"),
        ],
    }
    if row_overrides:
        row.update(row_overrides)
    page_path.write_text(
        json.dumps(
            {
                "Records": [row],
                "MoreRecords": False,
                "ItemCount": item_count,
                "PageNumber": 1,
                "PageSize": 1000,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    body_path = tmp_path / "body.json"
    body_path.write_text(
        json.dumps(
            {
                "source_id": "waec_ods_political_contributions",
                "complete_page_coverage": True,
                "pages": [
                    {
                        "page": 1,
                        "body_path": str(page_path),
                        "sha256": _sha256_path(page_path),
                        "item_count_reported": item_count,
                        "page_count_reported": 1,
                        "record_count": record_count,
                    }
                ],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {"source_id": "waec_ods_political_contributions"},
                "body_path": str(body_path),
                "sha256": _sha256_path(body_path),
                "pages": [
                    {
                        "page": 1,
                        "body_path": str(page_path),
                        "sha256": _sha256_path(page_path),
                        "item_count_reported": item_count,
                        "page_count_reported": 1,
                        "record_count": record_count,
                    }
                ],
                "complete_page_coverage": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_waec_political_contributions_extracts_rows(tmp_path) -> None:
    metadata_path = _write_waec_fixture(tmp_path)
    summary_path = normalize_waec_political_contributions(
        metadata_path=metadata_path,
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert summary["total_count"] == 1
    assert summary["reported_amount_total"] == "1234.5"
    assert rows[0]["source_dataset"] == "waec_political_contributions"
    assert rows[0]["flow_kind"] == "wa_political_contribution"
    assert rows[0]["source_raw_name"] == "Example Donor Pty Ltd"
    assert rows[0]["recipient_raw_name"] == "Example Party WA"
    assert rows[0]["date"] == ""
    assert rows[0]["date_reported"] == "2026-04-27"
    assert "disclosure-received date" in rows[0]["date_caveat"]
    assert rows[0]["donor_public_postcode"] == "6000"
    assert rows[0]["public_amount_counting_role"] == "single_observation"
    assert rows[0]["original"]["donor_id"] == "donor-1"
    assert rows[0]["original"]["political_entity_id"] == "entity-1"
    assert rows[0]["original"]["disclosure_received_date"] == "2026-04-27"


def test_waec_amendment_rows_are_preserved_but_not_totalled(tmp_path) -> None:
    metadata_path = _write_waec_fixture(
        tmp_path,
        row_overrides={
            "Attributes": [
                _attr("waec_datedisclosurereceived", "27/4/2026", "/Date(1777305600000)/"),
                _lookup_attr("waec_donorid", "Example Donor Pty Ltd", "donor-1"),
                _attr(
                    "a_f9c48d73871b443ba59c75ceb843e999.waec_publicpostcode",
                    "6000",
                ),
                _attr("waec_amount", "$1,234.50", {"Value": 1234.5}),
                _lookup_attr("waec_politicalentityaccountid", "Example Party WA", "entity-1"),
                _attr("waec_politicalcontributiontype", "Gift"),
                _attr("waec_disclosureversiontype", "Amendment"),
                _lookup_attr("waec_financialyearid", "2025-2026", "fy-1"),
                _attr("statuscode", "Published"),
                _lookup_attr("transactioncurrencyid", "Australian Dollar", "aud-1"),
            ],
        },
    )

    summary_path = normalize_waec_political_contributions(
        metadata_path=metadata_path,
        processed_dir=tmp_path / "processed",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    ]

    assert summary["reported_amount_total"] == "0"
    assert summary["versioned_observation_pending_dedupe_count"] == 1
    assert rows[0]["amount_aud"] == "1234.5"
    assert rows[0]["source_row_reported_amount_aud"] == "1234.5"
    assert rows[0]["public_amount_counting_role"] == "versioned_observation_pending_dedupe"


def test_waec_normalizer_rejects_reported_count_mismatch(tmp_path) -> None:
    metadata_path = _write_waec_fixture(tmp_path, item_count=2, record_count=2)

    with pytest.raises(ValueError, match="row count mismatch"):
        normalize_waec_political_contributions(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )


def test_waec_normalizer_rejects_uncapped_item_count_shortfall(tmp_path) -> None:
    metadata_path = _write_waec_fixture(tmp_path, item_count=2, record_count=1)

    with pytest.raises(ValueError, match="reported item count exceeds parsed rows"):
        normalize_waec_political_contributions(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )


def test_waec_normalizer_rejects_page_hash_mismatch(tmp_path) -> None:
    metadata_path = _write_waec_fixture(tmp_path)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    page_path = Path(metadata["pages"][0]["body_path"])
    page_path.write_text("tampered\n", encoding="utf-8")

    with pytest.raises(ValueError, match="page hash mismatch"):
        normalize_waec_political_contributions(
            metadata_path=metadata_path,
            processed_dir=tmp_path / "processed",
        )


def test_waec_display_date_rejects_ambiguous_australian_fallback() -> None:
    with pytest.raises(ValueError, match="Ambiguous WAEC display date"):
        _date_string(_attr("waec_datedisclosurereceived", "04/05/2026", "04/05/2026"))
