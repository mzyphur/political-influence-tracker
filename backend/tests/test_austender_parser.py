"""Pure-function tests for the AusTender CSV→JSONL parser.

Covers the four parsing helpers that AusTender's column format
forces us to handle carefully (DD/MM/YYYY dates, dollar-comma
money, "NULL"-as-string sentinel, "Yes"/"No" flag fields, ABN
hygiene) plus an end-to-end smoke that runs the full
``normalise_csv`` against a small in-memory fixture and asserts
the resulting JSONL row + summary JSON have the expected shape.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from au_politics_money.ingest import austender


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", None),
        (None, None),
        ("NULL", None),
        ("null", None),
        ("Null", None),
        ("  Department of Defence  ", "Department of Defence"),
    ],
)
def test_clean_text_treats_NULL_string_as_absent(raw, expected) -> None:
    assert austender._clean_text(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("14/06/2016", "2016-06-14"),
        ("19/10/2017", "2017-10-19"),
        ("2018-06-29", "2018-06-29"),
        ("2017/03/15", "2017-03-15"),
        ("01-07-2009", "2009-07-01"),
        ("", None),
        ("NULL", None),
        ("not-a-date", None),
    ],
)
def test_parse_date_handles_DDMMYYYY_and_isobands(raw, expected) -> None:
    assert austender._parse_date(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$1,234.56", "1234.56"),
        ("1234.56", "1234.56"),
        ("$0", "0"),
        ("0", "0"),
        ("NULL", None),
        ("", None),
        (None, None),
        ("not-a-number", None),
    ],
)
def test_parse_money_strips_dollar_and_commas(raw, expected) -> None:
    assert austender._parse_money(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Yes", True),
        ("yes", True),
        ("Y", True),
        ("No", False),
        ("no", False),
        ("N", False),
        ("", None),
        ("NULL", None),
        ("Maybe", None),
    ],
)
def test_parse_bool_flag_parses_yes_no_strings(raw, expected) -> None:
    assert austender._parse_bool_flag(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("12345678901", "12345678901"),
        ("12 345 678 901", "12345678901"),
        ("12.345.678.901", "12345678901"),
        ("ABN 12345678901", "12345678901"),
        # 12-digit "ABNs" or partials get preserved as cleaned source-text
        # so the loader can fail-loud later instead of fabricating.
        ("123456789", "123456789"),
        ("", None),
        ("NULL", None),
    ],
)
def test_normalise_abn_strips_whitespace_and_dots(raw, expected) -> None:
    assert austender._normalise_abn(raw) == expected


# Synthetic 4-row CSV that exercises every code path the real
# AusTender historical CSV has surfaced — NULL values in the
# Contract Value, NULL Supplier ABN with abn_exempt=Yes, an
# Amendment row referencing a parent, a non-default contract
# notice type, the literal "NULL" string for missing values,
# and a row with confidentiality flags claimed.
_SYNTHETIC_CSV = (
    "Agency Name,Contract Notice Type,Parent Contract ID,Contract ID,"
    "Publish Date,Amendment Date,Start Date,Amendment Start Date,End Date,"
    "Contract Value,Amendments Value,Description,Amendment Reason,"
    "Agency Ref ID,UNSPSC,UNSPSC Title,Procurement Method,ATM ID,SON ID,"
    "Panel Arrangement,Confidentiality Contract Flag,Confidentiality Contract Reason,"
    "Confidentiality Outputs Flag,Confidentiality Outputs Reason,Consultancy Flag,"
    "Consultancy Reason,Supplier Name,Supplier Address,Supplier Suburb,"
    "Supplier Postcode,Supplier State,Supplier Country,Supplier ABN Exempt,"
    "Supplier ABN,Contact Name,Contact Phone,Branch,Division,Office Postcode\n"
    # New parent contract, fully populated.
    "Department of Defence,Parent,NULL,CN1234567,01/07/2017,NULL,01/07/2017,"
    "NULL,30/06/2020,\"$1,234,567.89\",NULL,Provision of widgets,NULL,REF001,"
    "12345678,Aircraft,Open tender,NULL,NULL,NULL,No,NULL,No,NULL,No,NULL,"
    "BAE Systems Australia,123 Smith St,Canberra,2600,ACT,Australia,No,"
    "12345678901,Jane Smith,02 1234 5678,Defence Science,Procurement,2600\n"
    # Amendment row referencing parent, with NULL value (a value reset).
    "Department of Defence,Amendment,CN1234567,CN1234567-A1,15/01/2018,"
    "15/01/2018,01/07/2017,15/01/2018,30/06/2025,NULL,\"$500,000\",Contract extension,"
    "Extension to 2025,REF001,12345678,Aircraft,Open tender,NULL,NULL,NULL,No,"
    "NULL,No,NULL,No,NULL,BAE Systems Australia,123 Smith St,Canberra,2600,"
    "ACT,Australia,No,12345678901,Jane Smith,02 1234 5678,Defence Science,"
    "Procurement,2600\n"
    # Foreign supplier, ABN exempt, confidentiality flag claimed.
    "Department of Foreign Affairs,Parent,NULL,CN9999999,03/03/2017,NULL,"
    "03/03/2017,NULL,02/03/2018,$50000,NULL,Embassy services,NULL,DFAT-001,"
    "98765432,Diplomatic services,Limited tender,NULL,NULL,NULL,Yes,"
    "Confidential commercial information,No,NULL,Yes,Strategic policy advice,"
    "Foreign Embassy GmbH,1 Diplomatenweg,Berlin,NULL,NULL,Germany,Yes,NULL,"
    "NULL,NULL,Diplomatic relations,Europe,NULL\n"
    # Consultancy with all the optional fields blank.
    "Department of Health,Parent,NULL,CN5555555,10/10/2017,NULL,"
    "10/10/2017,NULL,10/04/2018,$250000,NULL,Health policy review,NULL,"
    "DOH-2017-1,80101507,Management advisory services,Prequalified tender,"
    "NULL,NULL,NULL,No,NULL,No,NULL,Yes,Health policy advice,KPMG Australia,"
    "10 Market St,Sydney,2000,NSW,Australia,No,12345678902,NULL,NULL,"
    "Strategic Policy,Health,2601\n"
)


def test_normalise_csv_end_to_end(tmp_path: Path) -> None:
    csv_path = tmp_path / "synthetic.csv"
    csv_path.write_text(_SYNTHETIC_CSV, encoding="utf-8")
    output_dir = tmp_path / "processed"
    jsonl_path = austender.normalise_csv(
        csv_path, output_dir=output_dir, fiscal_year_label="synthetic"
    )

    # JSONL records.
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 4

    # First row — fully populated parent contract.
    first = rows[0]
    assert first["schema_version"] == "austender_v1"
    assert first["contract_id"] == "CN1234567"
    assert first["parent_contract_id"] is None
    assert first["contract_notice_type"] == "Parent"
    assert first["agency"]["name"] == "Department of Defence"
    assert first["supplier"]["abn"] == "12345678901"
    assert first["supplier"]["abn_exempt"] is False
    assert first["contract_value_aud"] == "1234567.89"
    assert first["amendments_value_aud"] is None
    assert first["publish_date"] == "2017-07-01"
    assert first["start_date"] == "2017-07-01"
    assert first["end_date"] == "2020-06-30"
    assert first["unspsc_code"] == "12345678"
    assert first["unspsc_title"] == "Aircraft"
    assert first["confidentiality_contract_flag"] is False
    assert first["consultancy_flag"] is False

    # Second row — amendment referencing the parent.
    amendment = rows[1]
    assert amendment["contract_notice_type"] == "Amendment"
    assert amendment["parent_contract_id"] == "CN1234567"
    assert amendment["contract_id"] == "CN1234567-A1"
    assert amendment["contract_value_aud"] is None
    assert amendment["amendments_value_aud"] == "500000"
    assert amendment["amendment_date"] == "2018-01-15"

    # Third row — foreign supplier with abn_exempt and confidentiality.
    foreign = rows[2]
    assert foreign["supplier"]["abn"] is None
    assert foreign["supplier"]["abn_exempt"] is True
    assert foreign["supplier"]["country"] == "Germany"
    assert foreign["confidentiality_contract_flag"] is True
    assert foreign["confidentiality_contract_reason"] == (
        "Confidential commercial information"
    )
    assert foreign["consultancy_flag"] is True

    # Fourth row — consultancy with KPMG.
    consultancy = rows[3]
    assert consultancy["consultancy_flag"] is True
    assert consultancy["supplier"]["name"] == "KPMG Australia"
    assert consultancy["procurement_method"] == "Prequalified tender"

    # Summary file.
    summary_path = next(output_dir.glob("*.summary.json"))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["row_count"] == 4
    assert summary["rows_with_contract_value"] == 3  # amendment row has NULL value
    assert summary["fiscal_year_label"] == "synthetic"
    assert summary["consultancy_flag_yes_count"] == 2
    assert summary["confidentiality_contract_flag_yes_count"] == 1
    assert summary["supplier_abn_exempt_yes_count"] == 1
    type_counts = summary["contract_notice_type_counts"]
    assert type_counts["Parent"] == 3
    assert type_counts["Amendment"] == 1
    assert summary["publish_date_span"]["earliest"] == "2017-03-03"
    assert summary["publish_date_span"]["latest"] == "2018-01-15"
    # Personal-identifying fields are deliberately absent from JSONL.
    assert "contact_name" not in first
    assert "contact_phone" not in first
    # Claim-discipline caveat is present in summary.
    assert "claim_discipline_caveat" in summary
    assert "NOT a donation" in summary["claim_discipline_caveat"]
