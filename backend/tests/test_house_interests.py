from au_politics_money.ingest.house_interests import _extract_member_metadata, split_numbered_sections
from au_politics_money.ingest.house_interest_records import (
    guess_counterparty,
    records_from_house_section,
)


def test_split_numbered_sections_handles_missing_space_after_dot() -> None:
    text = """
1. Shareholdings
Self Nil
10.The nature of any other substantial sources of income
Self Salary
11.Gifts
Self Ticket from Example Org
"""
    sections = split_numbered_sections(text)
    assert [section["section_number"] for section in sections] == ["1", "10", "11"]
    assert sections[1]["section_title"] == "The nature of any other substantial sources of income"
    assert "Ticket from Example Org" in sections[2]["section_text"]


def test_split_numbered_sections_does_not_treat_dates_as_sections() -> None:
    text = """
11.Gifts
Self 1.11.25 Ticket to the Jack Jumpers basketball game x 3
12.Any sponsored travel or hospitality received where the value exceeds $300
Self Nil
"""
    sections = split_numbered_sections(text)
    assert [section["section_number"] for section in sections] == ["11", "12"]
    assert "1.11.25 Ticket" in sections[0]["section_text"]


def test_extract_member_metadata_handles_scanned_label_order() -> None:
    text = """
FAMILY NAME
KATTER
(please print)
NAMES
GIVEN ROBERT CARL
STATE
ELECTORALDIVISION KENNEDY OLD
"""
    metadata = _extract_member_metadata(text)
    assert metadata["family_name"] == "KATTER"
    assert metadata["given_names"] == "ROBERT CARL"
    assert metadata["member_name"] == "ROBERT CARL KATTER"
    assert metadata["electorate"] == "KENNEDY OLD"


def test_extract_member_metadata_handles_ocr_parenthetical_inline() -> None:
    text = """
FAMILY NAME

(please print) Gosling

GIVEN NAMES Luke

ELECTORAL DIVISION Solomon STATE NT
"""
    metadata = _extract_member_metadata(text)
    assert metadata["family_name"] == "Gosling"
    assert metadata["given_names"] == "Luke"
    assert metadata["member_name"] == "Luke Gosling"


def test_records_from_house_section_keeps_owner_context_and_values() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Anne Aly",
        "family_name": "Aly",
        "given_names": "Anne",
        "electorate": "Cowan",
        "state": "Western Australia",
        "section_number": "11",
        "section_title": "Gifts",
        "section_text": """
11.Gifts
Detail of gifts
Self Qantas Chairman's Lounge membership
Virgin Club membership
Spouse/ Not Applicable
Partner
Dependent Not Applicable
Children
5
""",
    }

    records = records_from_house_section(section)

    assert [record["owner_context"] for record in records] == ["self", "self"]
    assert [record["description"] for record in records] == [
        "Qantas Chairman's Lounge membership",
        "Virgin Club membership",
    ]
    assert records[0]["interest_category"] == "Gifts"


def test_records_from_house_section_skips_explanatory_notes() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Anne Aly",
        "family_name": "Aly",
        "given_names": "Anne",
        "electorate": "Cowan",
        "state": "Western Australia",
        "section_number": "2",
        "section_title": "The information which you are required to provide is contained in resolutions",
        "section_text": """
2. The information which you are required to provide is contained in resolutions agreed to by the
House of Representatives on 9 October 1984, amended 13 February 1986, 22 October 1986,
30 November 1988, 9 November 1994, 6 November 2003, 13 February 2008 and
19 September 2019. It consists of the Member's registrable interests and the registrable interests
of which the Member is aware.
""",
    }

    assert records_from_house_section(section) == []


def test_records_from_house_section_skips_ocr_explanatory_notes() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Luke Gosling",
        "family_name": "Gosling",
        "given_names": "Luke",
        "electorate": "Solomon",
        "state": "NT",
        "section_number": "1",
        "section_title": "Itis suggested that the accompanying Explanatory Notes be read before this statement is",
        "section_text": """
1. Itis suggested that the accompanying Explanatory Notes be read before this statement is
completed.
""",
    }

    assert records_from_house_section(section) == []


def test_records_from_house_section_skips_standard_form_prompts() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Sussan Ley",
        "family_name": "Ley",
        "given_names": "Sussan",
        "electorate": "Farrer",
        "state": "New South Wales",
        "section_number": "3",
        "section_title": "Real estate, including the location and purpose for which it is owned",
        "section_text": """
3. Real estate, including the location (suburb or area only) and the purpose for which it is owned
Location Purpose for which owned
Self Albury, NSW Residential
Albury, NSW Investment
Spouse/ Not Applicable Not Applicable
Partner
Dependent Not Applicable Not Applicable
Children
""",
    }

    records = records_from_house_section(section)

    assert [record["description"] for record in records] == [
        "Albury, NSW Residential",
        "Albury, NSW Investment",
    ]


def test_records_from_house_section_skips_form_headers_signature_and_ocr_noise() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Example Member",
        "family_name": "Member",
        "given_names": "Example",
        "electorate": "Example",
        "state": "Victoria",
        "section_number": "12",
        "section_title": "Sponsored travel or hospitality",
        "section_text": """
12. Sponsored travel or hospitality
HOUSE OF REPRESENTATIVES
PARLIAMENT OF AUSTRALIA
Self Signed: Date:
Self � AUSTRALI�,, k
Self Two tickets from Rugby Australia
""",
    }

    records = records_from_house_section(section)

    assert [record["description"] for record in records] == ["Two tickets from Rugby Australia"]


def test_records_from_house_section_skips_alteration_form_identity_tail() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Anthony Albanese",
        "family_name": "Albanese",
        "given_names": "Anthony",
        "electorate": "Grayndler",
        "state": "New South Wales",
        "section_number": "12",
        "section_title": "Sponsored travel or hospitality",
        "section_text": """
12. Sponsored travel or hospitality
Tickets to Oasis - Sydney 7 November from Venues NSW
PARLIAMENT OF AUSTRALIA
HOUSE OF REPRESENTATIVES
REGISTER OF MEMBERS' INTERESTS
NOTIFICATION OF AL TERATION(S) OF INTERESTS
48TH PARLIAMENT
45TH PARLIAMENT
FAMILY NAME
ALBANESE
(please print)
GIVEN NAMES
ANTHONY
ELECTORAL DIVISION I STATE
GRAYNDLER NSW
GRAYNDLER I STATE NSW
I wish to alter my statement of registrable interests as follows:
ADDITION
Item Details
""",
    }

    records = records_from_house_section(section)

    assert [record["description"] for record in records] == [
        "Tickets to Oasis - Sydney 7 November from Venues NSW"
    ]


def test_records_from_house_section_normalizes_non_values() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Example Member",
        "family_name": "Member",
        "given_names": "Example",
        "electorate": "Example",
        "state": "Victoria",
        "section_number": "11",
        "section_title": "Gifts",
        "section_text": """
11. Gifts
Self N/A
Spouse/ Nil applicable
Partner
Dependent Value: Unknown
Children
Self valued at $20
Self 2025 – valued at $50
Self Ticket from Example Association
""",
    }

    records = records_from_house_section(section)

    assert [record["description"] for record in records] == [
        "Ticket from Example Association"
    ]


def test_records_from_house_section_handles_spouse_slash_prefix() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "David Smith",
        "family_name": "Smith",
        "given_names": "David",
        "electorate": "Bean",
        "state": "Australian Capital Territory",
        "section_number": "3",
        "section_title": "Real estate",
        "section_text": """
3. Real estate, including the location (suburb or area only) and the purpose for which it is owned
Location Purpose for which owned
Self Farrer ACT Residential
Spouse/ Farrer ACT Residential
Partner
Dependent Not Applicable Not Applicable
Children
""",
    }

    records = records_from_house_section(section)

    assert records[0]["description"] == "Farrer ACT Residential"
    assert records[1]["owner_context"] == "spouse_partner"
    assert records[1]["description"] == "Farrer ACT Residential"


def test_records_from_house_section_merges_obvious_continuations() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Basem Abdo",
        "family_name": "Abdo",
        "given_names": "Basem",
        "electorate": "Calwell",
        "state": "Victoria",
        "section_number": "11",
        "section_title": "Gifts",
        "section_text": """
11. Gifts
ETU contribution to catering for
Maiden Speech event (valued at
$620.40)
""",
    }

    records = records_from_house_section(section)

    assert len(records) == 1
    assert records[0]["description"] == "ETU contribution to catering for Maiden Speech event (valued at $620.40)"


def test_guess_counterparty_from_clear_from_phrase() -> None:
    assert (
        guess_counterparty("Conference ticket from Example Minerals Pty Ltd - surrendered")
        == "Example Minerals Pty Ltd"
    )
    assert guess_counterparty("Qantas Chairman's Lounge membership") == "Qantas"


def test_records_from_house_section_extracts_provider_value_and_event_date() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Basem Abdo",
        "family_name": "Abdo",
        "given_names": "Basem",
        "electorate": "Calwell",
        "state": "Victoria",
        "section_number": "11",
        "section_title": "Gifts",
        "section_text": """
11. Gifts
Self Two tickets to awards dinner on 12 April 2025 provided by Example Association valued at $450.00
""",
    }

    records = records_from_house_section(section)

    assert len(records) == 1
    assert records[0]["counterparty_raw_name"] == "Example Association"
    assert records[0]["estimated_value"] == "450.00"
    assert records[0]["estimated_value_currency"] == "AUD"
    assert records[0]["event_date"] == "2025-04-12"
    assert records[0]["counterparty_extraction"]["method"] == "explicit_provider_phrase:provided by"


def test_records_from_house_section_extracts_invitation_provider_and_worth_value() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Example Member",
        "family_name": "Member",
        "given_names": "Example",
        "electorate": "Example",
        "state": "Victoria",
        "section_number": "11",
        "section_title": "Gifts",
        "section_text": """
11. Gifts
Self AFL Grand Final tickets at invitation of Commonwealth Bank worth $900
""",
    }

    records = records_from_house_section(section)

    assert len(records) == 1
    assert records[0]["counterparty_raw_name"] == "Commonwealth Bank"
    assert records[0]["estimated_value"] == "900"
    assert records[0]["counterparty_extraction"]["method"] == (
        "explicit_provider_phrase:at invitation of"
    )


def test_records_from_house_section_extracts_branded_lounge_provider() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Example Member",
        "family_name": "Member",
        "given_names": "Example",
        "electorate": "Example",
        "state": "Victoria",
        "section_number": "14",
        "section_title": "Other interests",
        "section_text": """
14. Other interests
Self Virgin Club membership
""",
    }

    records = records_from_house_section(section)

    assert len(records) == 1
    assert records[0]["counterparty_raw_name"] == "Virgin Australia"
    assert records[0]["counterparty_extraction"]["method"] == (
        "known_brand_provider:virgin_australia"
    )


def test_records_from_house_section_extracts_subject_provider_and_range_date() -> None:
    section = {
        "source_id": "source-1",
        "source_name": "Example PDF",
        "source_metadata_path": "/tmp/metadata.json",
        "body_path": "/tmp/body.pdf",
        "url": "https://example.test/example.pdf",
        "member_name": "Example Member",
        "family_name": "Member",
        "given_names": "Example",
        "electorate": "Example",
        "state": "Victoria",
        "section_number": "12",
        "section_title": "Sponsored travel or hospitality",
        "section_text": """
12. Sponsored travel or hospitality
Self Commonwealth Bank hosted AFL Grand Final hospitality 12-14 April 2025 valued at $1,200
""",
    }

    records = records_from_house_section(section)

    assert len(records) == 1
    assert records[0]["counterparty_raw_name"] == "Commonwealth Bank"
    assert records[0]["counterparty_extraction"]["method"] == (
        "subject_provider_verb:hosted"
    )
    assert records[0]["event_date"] == "2025-04-12"
    assert records[0]["event_date_extraction"]["method"] == (
        "explicit_textual_event_date_range_start"
    )
    assert records[0]["estimated_value"] == "1200"
