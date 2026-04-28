from pathlib import Path

from au_politics_money.ingest.aph_roster import _member_record, _senator_record


def test_member_roster_preserves_public_contact_fields() -> None:
    row = {
        "Honorific": "Mr",
        "First Name": "Basem",
        "Preferred Name": "Basem",
        "Surname": "Abdo",
        "Electorate": "Calwell",
        "State": "VIC",
        "Political Party": "ALP",
        "Gender": "Male",
        "Telephone": "(02) 6277 4503",
        "Electorate Address Line 1": "14 Dimboola Road",
        "Electorate Suburb": "Broadmeadows",
        "Electorate State": "VIC",
        "Electorate PostCode": "3047",
        "Electorate Telephone": "(03) 9367 5216",
        "Electorate Postal Address": "PO Box 3218",
        "Electorate Postal Suburb": "Broadmeadows",
        "Electorate Postal State": "VIC",
        "Electorate Postal Postcode": "3047",
    }

    record = _member_record(
        2,
        row,
        Path("metadata.json"),
        {
            "basem abdo mp": {
                "email": "Basem.Abdo.MP@aph.gov.au",
                "email_source_metadata_path": "members-list-metadata.json",
                "email_source_body_path": "members-list.pdf",
            }
        },
    )

    assert record["email"] == "Basem.Abdo.MP@aph.gov.au"
    assert record["parliamentary_phone"] == "(02) 6277 4503"
    assert record["electorate_phone"] == "(03) 9367 5216"
    assert record["electorate_office_address"] == "14 Dimboola Road, Broadmeadows VIC 3047"
    assert record["electorate_postal_address"] == "PO Box 3218, Broadmeadows VIC 3047"
    assert record["official_profile_search_url"].endswith("?q=Basem+Abdo")


def test_senator_roster_uses_official_senator_email_pattern_when_pdf_email_present() -> None:
    row = {
        "Title": "Senator",
        "First Name": "Penny",
        "Preferred Name": "Penny",
        "Surname": "Allman-Payne",
        "State": "QLD",
        "Political Party": "AG",
        "Electorate Address Line 1": "20-22 Herbert Street",
        "Electorate Suburb": "Gladstone",
        "Electorate State": "QLD",
        "Electorate PostCode": "4680",
        "Electorate Telephone": "(07) 4972 0380",
        "Label Address": "PO Box 5304",
        "Label Suburb": "Gladstone",
        "Label State": "QLD",
        "Label postcode": "4680",
    }

    record = _senator_record(
        2,
        row,
        Path("metadata.json"),
        {
            "senator allman payne": {
                "email": "senator.allman-payne@aph.gov.au",
                "email_source_metadata_path": "senator-list-metadata.json",
                "email_source_body_path": "los.pdf",
            }
        },
    )

    assert record["email"] == "senator.allman-payne@aph.gov.au"
    assert record["electorate_phone"] == "(07) 4972 0380"
    assert record["electorate_office_address"] == "20-22 Herbert Street, Gladstone QLD 4680"
    assert record["electorate_postal_address"] == "PO Box 5304, Gladstone QLD 4680"


def test_senator_email_match_skips_ambiguous_surnames() -> None:
    row = {
        "Title": "Senator",
        "First Name": "Dean",
        "Preferred Name": "Dean",
        "Surname": "Smith",
        "State": "WA",
        "Political Party": "LP",
    }

    record = _senator_record(
        2,
        row,
        Path("metadata.json"),
        {
            "senator smith": {
                "email": "senator.smith@aph.gov.au",
                "email_source_metadata_path": "senator-list-metadata.json",
                "email_source_body_path": "los.pdf",
            }
        },
        {"smith"},
    )

    assert record["email"] == ""
