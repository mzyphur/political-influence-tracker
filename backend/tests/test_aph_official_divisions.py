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
