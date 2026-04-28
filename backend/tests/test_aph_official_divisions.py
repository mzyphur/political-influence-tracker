from __future__ import annotations

import json

from au_politics_money.ingest.aph_official_divisions import parse_official_divisions_from_text


def test_parse_senate_division_extracts_votes_and_tellers(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "people": [
                    {
                        "canonical_name": "Penny Allman-Payne",
                        "chamber": "senate",
                        "preferred_name": "Penny",
                        "first_name": "Penny",
                        "surname": "Allman-Payne",
                        "party": "AG",
                        "state": "QLD",
                    },
                    {
                        "canonical_name": "Nick McKim",
                        "chamber": "senate",
                        "preferred_name": "Nick",
                        "first_name": "Nicholas",
                        "surname": "McKim",
                        "party": "AG",
                        "state": "TAS",
                    },
                    {
                        "canonical_name": "David Pocock",
                        "chamber": "senate",
                        "preferred_name": "David",
                        "first_name": "David",
                        "surname": "Pocock",
                        "party": "IND",
                        "state": "ACT",
                    },
                    {
                        "canonical_name": "Barbara Pocock",
                        "chamber": "senate",
                        "preferred_name": "Barbara",
                        "first_name": "Barbara",
                        "surname": "Pocock",
                        "party": "AG",
                        "state": "SA",
                    },
                    {
                        "canonical_name": "Deborah O'Neill",
                        "chamber": "senate",
                        "preferred_name": "Deborah",
                        "first_name": "Deborah",
                        "surname": "O'Neill",
                        "party": "ALP",
                        "state": "NSW",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    text = """
    4 Example Bill 2026
    Question—That the amendment be agreed to—put.
    The Senate divided—
    AYES, 4
    Senators—
    Allman-Payne McKim* Pocock, David Pocock, Barbara
    NOES, 1
    Senators—
    O’Neill
    * Tellers
    Question negatived.
    """

    divisions = parse_official_divisions_from_text(
        text=text,
        chamber="senate",
        record={
            "external_key": "aph_senate_journals:test",
            "record_date": "2026-03-25",
            "title": "Journals of the Senate 2026-03-25",
        },
        document={
            "source_id": "aph_senate_journals__decision_record__test",
            "representation_kind": "parlinfo_pdf",
            "representation_url": "https://parlinfo.aph.gov.au/example.pdf",
            "metadata_path": "/tmp/metadata.json",
            "status": "fetched",
        },
        roster_path=roster_path,
    )

    assert len(divisions) == 1
    division = divisions[0]
    assert division["chamber"] == "senate"
    assert division["aye_count"] == 4
    assert division["no_count"] == 1
    assert division["metadata"]["vote_count_matches"] is True
    assert [vote["raw_name"] for vote in division["votes"]] == [
        "Allman-Payne",
        "McKim",
        "Pocock, David",
        "Pocock, Barbara",
        "O’Neill",
    ]
    assert division["votes"][1]["is_teller"] is True
    assert division["votes"][-1]["matched_roster_canonical_name"] == "Deborah O'Neill"


def test_parse_house_division_extracts_honorific_initial_names_and_page_headers(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "people": [
                    {
                        "canonical_name": "Monique Ryan",
                        "chamber": "house",
                        "honorific": "Dr",
                        "preferred_name": "Monique",
                        "first_name": "Monique",
                        "other_name": "Marie",
                        "surname": "Ryan",
                        "party": "IND",
                        "state": "VIC",
                    },
                    {
                        "canonical_name": "Joanne Ryan",
                        "chamber": "house",
                        "honorific": "Ms",
                        "preferred_name": "Joanne",
                        "first_name": "Joanne",
                        "surname": "Ryan",
                        "party": "ALP",
                        "state": "VIC",
                    },
                    {
                        "canonical_name": "Tim Wilson",
                        "chamber": "house",
                        "honorific": "Mr",
                        "preferred_name": "Tim",
                        "first_name": "Timothy",
                        "surname": "Wilson",
                        "party": "LP",
                        "state": "VIC",
                    },
                    {
                        "canonical_name": "Josh Wilson",
                        "chamber": "house",
                        "honorific": "Mr",
                        "preferred_name": "Josh",
                        "first_name": "Joshua",
                        "surname": "Wilson",
                        "party": "ALP",
                        "state": "WA",
                    },
                    {
                        "canonical_name": "Rick Wilson",
                        "chamber": "house",
                        "honorific": "Mr",
                        "preferred_name": "Rick",
                        "first_name": "Richard",
                        "surname": "Wilson",
                        "party": "LP",
                        "state": "WA",
                    },
                    {
                        "canonical_name": "Allegra Spender",
                        "chamber": "house",
                        "honorific": "Ms",
                        "preferred_name": "Allegra",
                        "first_name": "Allegra",
                        "surname": "Spender",
                        "party": "IND",
                        "state": "NSW",
                    },
                    {
                        "canonical_name": "Sharon Claydon",
                        "chamber": "house",
                        "honorific": "Ms",
                        "preferred_name": "Sharon",
                        "first_name": "Sharon",
                        "surname": "Claydon",
                        "party": "ALP",
                        "state": "NSW",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    text = """
    6 MIGRATION AMENDMENT (2026 MEASURES NO. 1) BILL 2026
    Question—That the amendments be agreed to—put.
    The House divided (the Speaker, Mr Dick, in the Chair)—
    AYES, 2
    Dr M Ryan Ms Spender*
    NOES, 5
    Mr R Wilson Mr T Wilson*
    554 No. 45—11 March 2026
    Mr J Wilson Ms Claydon Ms J Ryan
    * Tellers
    And so it was negatived.
    """

    divisions = parse_official_divisions_from_text(
        text=text,
        chamber="house",
        record={
            "external_key": "aph_house_votes_and_proceedings:test",
            "record_date": "2026-03-11",
            "title": "House Votes and Proceedings 2026-03-11",
        },
        document={
            "source_id": "aph_house_votes_and_proceedings__decision_record__test",
            "representation_kind": "parlinfo_pdf",
            "representation_url": "https://parlinfo.aph.gov.au/example.pdf",
            "metadata_path": "/tmp/metadata.json",
            "status": "fetched",
        },
        roster_path=roster_path,
    )

    assert len(divisions) == 1
    division = divisions[0]
    assert division["chamber"] == "house"
    assert division["metadata"]["vote_count_matches"] is True
    assert [vote["matched_roster_canonical_name"] for vote in division["votes"]] == [
        "Monique Ryan",
        "Allegra Spender",
        "Rick Wilson",
        "Tim Wilson",
        "Josh Wilson",
        "Sharon Claydon",
        "Joanne Ryan",
    ]
    assert division["votes"][1]["is_teller"] is True
    assert division["votes"][3]["is_teller"] is True


def test_parse_house_partial_division_is_not_treated_as_full_person_vote() -> None:
    text = """
    The House divided and only Ms Boele, Mr Gee and Mr Katter voting "Aye",
    the question was negatived.
    """

    divisions = parse_official_divisions_from_text(
        text=text,
        chamber="house",
        record={"external_key": "aph_house_votes_and_proceedings:test", "record_date": "2026-03-11"},
        document={"source_id": "source", "representation_url": "https://example.test", "metadata_path": ""},
    )

    assert divisions == []


def test_parse_house_division_keeps_unmatched_roster_name_and_continues(tmp_path) -> None:
    roster_path = tmp_path / "roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "people": [
                    {
                        "canonical_name": "Leon Rebello",
                        "chamber": "house",
                        "honorific": "Mr",
                        "preferred_name": "Leon",
                        "first_name": "Leon",
                        "surname": "Rebello",
                        "party": "LNP",
                        "state": "QLD",
                    },
                    {
                        "canonical_name": "Jason Wood",
                        "chamber": "house",
                        "honorific": "Hon",
                        "preferred_name": "Jason",
                        "first_name": "Jason",
                        "surname": "Wood",
                        "party": "LP",
                        "state": "VIC",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    text = """
    Question—That the motion be agreed to—put.
    The House divided (the Speaker, Mr Dick, in the Chair)—
    AYES, 0
    NOES, 3
    Ms Ley Mr Rebello Mr Wood
    Question agreed to.
    """

    divisions = parse_official_divisions_from_text(
        text=text,
        chamber="house",
        record={
            "external_key": "aph_house_votes_and_proceedings:test",
            "record_date": "2026-01-20",
            "title": "House Votes and Proceedings 2026-01-20",
        },
        document={
            "source_id": "aph_house_votes_and_proceedings__decision_record__test",
            "representation_kind": "parlinfo_pdf",
            "representation_url": "https://parlinfo.aph.gov.au/example.pdf",
            "metadata_path": "/tmp/metadata.json",
            "status": "fetched",
        },
        roster_path=roster_path,
    )

    division = divisions[0]
    assert division["metadata"]["vote_count_matches"] is True
    assert division["metadata"]["unmatched_roster_vote_count"] == 1
    assert [vote["raw_name"] for vote in division["votes"]] == ["Ms Ley", "Mr Rebello", "Mr Wood"]
    assert division["votes"][0]["name_match_status"] == "unmatched_roster"
    assert [vote["matched_roster_canonical_name"] for vote in division["votes"][1:]] == [
        "Leon Rebello",
        "Jason Wood",
    ]
