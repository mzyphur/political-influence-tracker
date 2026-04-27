from pathlib import Path

from au_politics_money.ingest.aph_roster import _member_record, _senator_record


def test_member_record_uses_preferred_name() -> None:
    row = {
        "Honorific": "Ms",
        "First Name": "Example",
        "Preferred Name": "Ex",
        "Surname": "Member",
        "Electorate": "Demo",
        "State": "NSW",
        "Political Party": "IND",
        "Gender": "Female",
    }
    record = _member_record(2, row, Path("metadata.json"))
    assert record["chamber"] == "house"
    assert record["canonical_name"] == "Ex Member"
    assert record["display_name"] == "Ms Ex Member"
    assert record["electorate"] == "Demo"


def test_senator_record_uses_state() -> None:
    row = {
        "Title": "Senator",
        "First Name": "Example",
        "Preferred Name": "Ex",
        "Surname": "Senator",
        "State": "VIC",
        "Political Party": "ALP",
        "Gender": "Male",
    }
    record = _senator_record(2, row, Path("metadata.json"))
    assert record["chamber"] == "senate"
    assert record["canonical_name"] == "Ex Senator"
    assert record["display_name"] == "Senator Ex Senator"
    assert record["state"] == "VIC"

