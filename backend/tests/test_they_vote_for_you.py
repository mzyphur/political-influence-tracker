from __future__ import annotations

import json
from pathlib import Path

import pytest

from au_politics_money.ingest import they_vote_for_you
from au_politics_money.ingest.they_vote_for_you import (
    MissingTheyVoteForYouApiKey,
    _api_key,
    _public_url_without_secret,
    fetch_they_vote_for_you_divisions,
    normalize_division_detail,
    normalize_house,
    normalize_vote_value,
)


def test_api_key_missing_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THEY_VOTE_FOR_YOU_API_KEY", raising=False)
    monkeypatch.delenv("TVFY_API_KEY", raising=False)

    with pytest.raises(MissingTheyVoteForYouApiKey):
        _api_key()


def test_public_url_omits_api_key_only() -> None:
    url = _public_url_without_secret(
        "divisions.json",
        {
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "house": "senate",
            "key": "secret",
        },
    )

    assert "secret" not in url
    assert "key=" not in url
    assert "house=senate" in url


def test_normalizers_accept_expected_api_values() -> None:
    assert normalize_house("representatives") == "house"
    assert normalize_house("senate") == "senate"
    assert normalize_vote_value("Yes") == "aye"
    assert normalize_vote_value("No") == "no"
    assert normalize_vote_value("Absent") == "absent"
    assert normalize_vote_value("something else") == "unknown"


def test_fetch_divisions_auto_splits_capped_date_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bodies: dict[Path, list[dict[str, int]]] = {}
    list_requests: list[tuple[str, str, str]] = []
    detail_requests: list[int] = []

    def fake_fetch_json_endpoint(
        *,
        endpoint: str,
        params: dict[str, str],
        source_id: str,
        source_name: str,
        source_type: str,
        timeout: int = 60,
    ) -> Path:
        del source_name, source_type, timeout
        metadata_path = tmp_path / f"{source_id}.json"
        if endpoint == "divisions.json":
            start = params["start_date"]
            end = params["end_date"]
            house = params["house"]
            list_requests.append((house, start, end))
            if (start, end) == ("2026-01-01", "2026-01-04"):
                bodies[metadata_path] = [{"id": value} for value in range(1, 101)]
            elif (start, end) == ("2026-01-01", "2026-01-02"):
                bodies[metadata_path] = [{"id": 1}, {"id": 2}]
            elif (start, end) == ("2026-01-03", "2026-01-04"):
                bodies[metadata_path] = [{"id": 3}]
            else:
                bodies[metadata_path] = []
        else:
            detail_requests.append(int(endpoint.removeprefix("divisions/").removesuffix(".json")))
        metadata_path.write_text("{}", encoding="utf-8")
        return metadata_path

    monkeypatch.setenv("THEY_VOTE_FOR_YOU_API_KEY", "test-key")
    monkeypatch.setattr(they_vote_for_you, "_fetch_json_endpoint", fake_fetch_json_endpoint)
    monkeypatch.setattr(they_vote_for_you, "_metadata_body", lambda path: bodies[path])

    summary_path = fetch_they_vote_for_you_divisions(
        start_date="2026-01-01",
        end_date="2026-01-04",
        house="senate",
        processed_dir=tmp_path,
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert list_requests == [
        ("senate", "2026-01-01", "2026-01-04"),
        ("senate", "2026-01-01", "2026-01-02"),
        ("senate", "2026-01-03", "2026-01-04"),
    ]
    assert detail_requests == [1, 2, 3]
    assert summary["listed_count"] == 3
    assert summary["detail_count_fetched"] == 3
    assert summary["list_request_count"] == 3
    assert len(summary["split_windows"]) == 1
    assert len(summary["accepted_windows"]) == 2


def test_fetch_divisions_fails_when_one_day_hits_result_cap(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    metadata_path = tmp_path / "list.json"
    metadata_path.write_text("{}", encoding="utf-8")

    monkeypatch.setenv("THEY_VOTE_FOR_YOU_API_KEY", "test-key")
    monkeypatch.setattr(they_vote_for_you, "_fetch_json_endpoint", lambda **kwargs: metadata_path)
    monkeypatch.setattr(
        they_vote_for_you,
        "_metadata_body",
        lambda path: [{"id": value} for value in range(1, 101)],
    )

    with pytest.raises(RuntimeError, match="one-day API window"):
        fetch_they_vote_for_you_divisions(
            start_date="2026-01-01",
            end_date="2026-01-01",
            house="senate",
            processed_dir=tmp_path,
        )


def _write_division_detail(tmp_path: Path) -> Path:
    body_path = tmp_path / "body.json"
    body_path.write_text(
        json.dumps(
            {
                "id": 123,
                "house": "representatives",
                "name": "Climate Bill - Second Reading",
                "date": "2026-03-04",
                "number": 2,
                "clock_time": "4:31 PM",
                "aye_votes": 76,
                "no_votes": 70,
                "possible_turnout": 150,
                "rebellions": 1,
                "edited": True,
                "summary": "The majority voted for the bill.",
                "bills": [{"name": "Climate Bill 2026"}],
                "policy_divisions": [
                    {
                        "vote": "strong",
                        "policy": {
                            "id": 99,
                            "name": "for climate action",
                            "description": "Support stronger climate action.",
                            "provisional": False,
                        },
                    }
                ],
                "votes": [
                    {
                        "vote": "Yes",
                        "rebelled": False,
                        "person": {
                            "id": 7,
                            "name": "Jane Example",
                            "electorate": "Demo",
                            "party": "Example Party",
                        },
                    },
                    {
                        "vote": "No",
                        "rebelled": True,
                        "person": {
                            "id": 8,
                            "name": "John Example",
                            "electorate": "Sample",
                            "party": {"name": "Other Party"},
                        },
                    },
                    {
                        "vote": "Yes",
                        "member": {
                            "id": 9,
                            "first_name": "Sam",
                            "last_name": "Sample",
                            "electorate": "Example",
                            "party": "Example Party",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "source": {
                    "source_id": "they_vote_for_you_api_division_123",
                    "name": "division",
                    "source_type": "division_vote_api_detail",
                    "jurisdiction": "Commonwealth",
                    "level": "federal",
                    "url": "https://theyvoteforyou.org.au/api/v1/divisions/123.json",
                    "expected_format": "json",
                    "update_frequency": "ongoing",
                    "priority": "high",
                    "notes": "",
                },
                "body_path": str(body_path),
            }
        ),
        encoding="utf-8",
    )
    return metadata_path


def test_normalize_division_detail_preserves_votes_policies_and_caveat(tmp_path: Path) -> None:
    metadata_path = _write_division_detail(tmp_path)

    division = normalize_division_detail(metadata_path)

    assert division["external_id"] == "they_vote_for_you:division:123"
    assert division["chamber"] == "house"
    assert division["division_date"] == "2026-03-04"
    assert division["bill_name"] == "Climate Bill 2026"
    assert division["votes"][0]["vote"] == "aye"
    assert division["votes"][1]["vote"] == "no"
    assert division["votes"][1]["rebelled_against_party"] is True
    assert division["votes"][2]["person_name"] == "Sam Sample"
    assert division["policies"][0]["tvfy_policy_id"] == 99
    assert division["metadata"]["source_evidence_class"] == "third_party_civic"
