from __future__ import annotations

from au_politics_money.ingest.qld_parliament_members import _normalize_member_rows


def test_normalize_qld_current_members_groups_offices_and_vacancies() -> None:
    rows = [
        {
            "title": "Mr",
            "first": "Robbie",
            "last": "Katter MP",
            "electorate": "Member for Traeger",
            "portfolio": "",
            "address 1": "PO Box 1968",
            "address 2": "MOUNT ISA  QLD  4825",
            "email address": "traeger@parliament.qld.gov.au",
            "salutation": "Mr Katter",
            "party": "KAP",
            "source_row_number": "92",
        },
        {
            "title": "Mr",
            "first": "Robbie",
            "last": "Katter MP",
            "electorate": "Member for Traeger",
            "address 1": "Stock Exchange Arcade",
            "address 2": "2/76 Mosman Street",
            "address 3": "CHARTERS TOWERS  QLD  4820",
            "email address": "traeger@parliament.qld.gov.au",
            "salutation": "Mr Katter",
            "party": "KAP",
            "source_row_number": "93",
        },
        {
            "electorate": "Member for Stafford",
            "address 1": "Unit 207, 6 Babarra Street",
            "address 2": "STAFFORD  QLD  4053",
            "email address": "stafford@parliament.qld.gov.au",
            "salutation": "Sir/Madam",
            "party": "-",
            "source_row_number": "70",
        },
    ]

    records = _normalize_member_rows(rows)

    stafford = next(record for record in records if record["electorate"] == "Stafford")
    assert stafford["is_vacant"] is True
    assert stafford["email"] == "stafford@parliament.qld.gov.au"

    traeger = next(record for record in records if record["electorate"] == "Traeger")
    assert traeger["is_vacant"] is False
    assert traeger["display_name"] == "Mr Robbie Katter"
    assert traeger["party_short_name"] == "KAP"
    assert traeger["email"] == "traeger@parliament.qld.gov.au"
    assert len(traeger["electorate_offices"]) == 2
    assert traeger["electorate_offices"][1]["address_lines"] == [
        "Stock Exchange Arcade",
        "2/76 Mosman Street",
        "CHARTERS TOWERS QLD 4820",
    ]
