import json

from au_politics_money.ingest.senate_interests import (
    _flatten_statement_detail,
    parse_senate_env_api_base,
)


def test_parse_senate_env_api_base() -> None:
    js_text = """
    window.env = {
      SENATORS_API_BASE_URL: 'https://example.test/api',
      SITECORE_CONTENT_API_BASE_URL: 'https://www.aph.gov.au/api',
    };
    """

    assert parse_senate_env_api_base(js_text) == "https://example.test/api"


def test_flatten_statement_detail(tmp_path) -> None:
    body_path = tmp_path / "body.json"
    body_path.write_text(
        json.dumps(
            {
                "senatorInterestStatement": {
                    "lodgementDate": "8/14/2025 1:31:50 PM",
                    "lastDateUpdated": "11/12/2025 4:09:19 PM",
                    "senatorTitle": "Senator",
                    "senatorName": "Example, Alex",
                    "senatorPostNominal": "",
                    "senatorParty": "Example Party",
                    "electorateState": "Queensland",
                },
                "gifts": {
                    "interests": [
                        {
                            "detailOfGifts": (
                                "Conference ticket on 12 April 2025 provided by "
                                "Example Ltd valued at $500"
                            ),
                            "id": "gift-1",
                        }
                    ],
                    "alterations": [],
                },
                "liabilities": {
                    "interests": [
                        {
                            "natureOfLiability": "Mortgage",
                            "creditor": "Example Bank",
                            "id": "liability-1",
                        }
                    ],
                    "alterations": [],
                },
            }
        ),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "source": {
                    "source_id": "aph_senators_interests_api_statement__123",
                    "name": "Senate interests API: statement detail for Example, Alex",
                    "url": "https://example.test/api/getSenatorStatement?cdapid=123",
                },
            }
        ),
        encoding="utf-8",
    )

    records = _flatten_statement_detail(metadata_path)

    assert len(records) == 2
    assert records[0]["external_key"] == "aph_senate_interests:123:liabilities:interests:liability-1"
    assert records[0]["counterparty_raw_name"] == "Example Bank"
    assert records[1]["interest_category"] == "gifts"
    assert records[1]["counterparty_raw_name"] == "Example Ltd"
    assert records[1]["estimated_value"] == "500"
    assert records[1]["event_date"] == "2025-04-12"


def test_flatten_senate_alteration_uses_created_on_as_reported_date(tmp_path) -> None:
    body_path = tmp_path / "body.json"
    body_path.write_text(
        json.dumps(
            {
                "senatorInterestStatement": {
                    "senatorName": "Example, Alex",
                    "senatorParty": "Example Party",
                    "electorateState": "Queensland",
                },
                "sponsoredTravelOrHospitality": {
                    "interests": [],
                    "alterations": [
                        {
                            "alterationType": "Addition",
                            "details": "Ticket as guest of Westpac on 27 August 2025",
                            "createdOn": "2025-09-18T10:00:00Z",
                            "id": "travel-1",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "body_path": str(body_path),
                "source": {
                    "source_id": "aph_senators_interests_api_statement__123",
                    "name": "Senate interests API: statement detail for Example, Alex",
                    "url": "https://example.test/api/getSenatorStatement?cdapid=123",
                },
            }
        ),
        encoding="utf-8",
    )

    records = _flatten_statement_detail(metadata_path)

    assert len(records) == 1
    assert records[0]["counterparty_raw_name"] == "Westpac"
    assert records[0]["event_date"] == "2025-08-27"
    assert records[0]["reported_date"] == "2025-09-18"
