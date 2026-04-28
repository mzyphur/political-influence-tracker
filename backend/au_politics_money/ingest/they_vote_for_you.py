from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.fetch import _safe_response_headers
from au_politics_money.ingest.sources import get_source
from au_politics_money.models import SourceRecord


API_BASE_URL = "https://theyvoteforyou.org.au/api/v1"
PARSER_NAME = "they_vote_for_you_divisions_v1"
PARSER_VERSION = "1"


class MissingTheyVoteForYouApiKey(RuntimeError):
    pass


@dataclass
class _DivisionFetchAccumulator:
    list_metadata_paths: list[str]
    detail_metadata_paths: list[str]
    accepted_windows: list[dict[str, Any]]
    split_windows: list[dict[str, Any]]
    listed_count: int = 0
    remaining_limit: int | None = None


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _api_key() -> str:
    key = os.environ.get("THEY_VOTE_FOR_YOU_API_KEY") or os.environ.get("TVFY_API_KEY")
    if not key:
        raise MissingTheyVoteForYouApiKey(
            "Set THEY_VOTE_FOR_YOU_API_KEY in the environment or backend/.env. "
            "They Vote For You issues keys at https://theyvoteforyou.org.au/help/data."
        )
    return key


def _clean_source_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return cleaned[:90] or "request"


def _public_url_without_secret(endpoint: str, params: dict[str, Any]) -> str:
    public_params = {key: value for key, value in params.items() if key != "key" and value is not None}
    query = urlencode(public_params)
    return f"{API_BASE_URL}/{endpoint}" + (f"?{query}" if query else "")


def _request_url(endpoint: str, params: dict[str, Any]) -> str:
    query = urlencode({key: value for key, value in params.items() if value is not None})
    return f"{API_BASE_URL}/{endpoint}?{query}"


def _source_record(source_id: str, name: str, url: str, source_type: str) -> SourceRecord:
    parent = get_source("they_vote_for_you_api")
    return SourceRecord(
        source_id=source_id,
        name=name,
        jurisdiction=parent.jurisdiction,
        level=parent.level,
        source_type=source_type,
        url=url,
        expected_format="json",
        update_frequency=parent.update_frequency,
        priority=parent.priority,
        notes="They Vote For You REST API response. API key is omitted from stored metadata.",
    )


def _fetch_json_endpoint(
    *,
    endpoint: str,
    params: dict[str, Any],
    source_id: str,
    source_name: str,
    source_type: str,
    timeout: int = 60,
) -> Path:
    params_with_key = {**params, "key": _api_key()}
    public_url = _public_url_without_secret(endpoint, params)
    request_url = _request_url(endpoint, params_with_key)
    source = _source_record(source_id, source_name, public_url, source_type)

    run_ts = _timestamp()
    target_dir = RAW_DIR / source.source_id / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)
    request = Request(request_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            headers = _safe_response_headers(dict(response.headers.items()))
            final_url = public_url
    except HTTPError as exc:
        body = exc.read()
        status = exc.code
        headers = _safe_response_headers(dict(exc.headers.items()) if exc.headers else {})
        final_url = public_url
    except URLError as exc:
        metadata_path = target_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source": asdict(source),
                    "fetched_at": run_ts,
                    "ok": False,
                    "error": str(exc),
                    "request_params": params,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    sha256 = hashlib.sha256(body).hexdigest()
    body_path = target_dir / "body.json"
    body_path.write_bytes(body)
    metadata = {
        "source": asdict(source),
        "fetched_at": run_ts,
        "ok": 200 <= status < 400,
        "http_status": status,
        "final_url": final_url,
        "content_type": headers.get("Content-Type") or headers.get("content-type"),
        "content_length": len(body),
        "sha256": sha256,
        "body_path": str(body_path),
        "headers": headers,
        "request_params": params,
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if not metadata["ok"]:
        raise RuntimeError(
            f"They Vote For You fetch failed for {source_id}: HTTP {status}; "
            f"metadata: {metadata_path}"
        )
    return metadata_path


def _latest_file(directory: Path, pattern: str) -> Path:
    candidates = sorted(directory.glob(pattern), reverse=True)
    if not candidates:
        raise FileNotFoundError(f"No files matching {pattern!r} in {directory}")
    return candidates[0]


def _metadata_body(metadata_path: Path) -> Any:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return json.loads(Path(metadata["body_path"]).read_text(encoding="utf-8"))


def _records_from_response(payload: Any, key: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get(key) or payload.get("results") or payload.get("data")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    raise RuntimeError(f"Unexpected They Vote For You API response shape for {key}.")


def fetch_they_vote_for_you_people(*, processed_dir: Path = PROCESSED_DIR) -> Path:
    metadata_path = _fetch_json_endpoint(
        endpoint="people.json",
        params={},
        source_id="they_vote_for_you_api_people",
        source_name="They Vote For You API: current people",
        source_type="division_vote_api_people",
    )
    payload = _metadata_body(metadata_path)
    people = _records_from_response(payload, "people")
    timestamp = _timestamp()
    target_dir = processed_dir / "they_vote_for_you_people_fetches"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "people_count": len(people),
        "metadata_path": str(metadata_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def _default_start_end(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    end = date.fromisoformat(end_date) if end_date else _today()
    start = date.fromisoformat(start_date) if start_date else end - timedelta(days=90)
    if start > end:
        raise ValueError("start_date must be on or before end_date.")
    return start.isoformat(), end.isoformat()


def _house_values(house: str | None) -> list[str]:
    if house:
        return [house]
    return ["representatives", "senate"]


def _split_date_window(start: str, end: str) -> tuple[tuple[str, str], tuple[str, str]] | None:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end)
    if start_date >= end_date:
        return None
    midpoint = start_date + timedelta(days=(end_date - start_date).days // 2)
    return (start, midpoint.isoformat()), ((midpoint + timedelta(days=1)).isoformat(), end)


def _fetch_they_vote_for_you_house_window(
    *,
    house_value: str,
    start: str,
    end: str,
    allow_truncated: bool,
    accumulator: _DivisionFetchAccumulator,
) -> None:
    params = {"start_date": start, "end_date": end, "house": house_value}
    list_source_id = _clean_source_id(f"they_vote_for_you_api_divisions_{house_value}_{start}_{end}")
    list_metadata_path = _fetch_json_endpoint(
        endpoint="divisions.json",
        params=params,
        source_id=list_source_id,
        source_name=f"They Vote For You API: divisions {house_value} {start} to {end}",
        source_type="division_vote_api_list",
    )
    accumulator.list_metadata_paths.append(str(list_metadata_path))
    divisions = _records_from_response(_metadata_body(list_metadata_path), "divisions")

    if len(divisions) >= 100 and not allow_truncated:
        split = _split_date_window(start, end)
        if split is None:
            raise RuntimeError(
                "They Vote For You returned 100 divisions for "
                f"{house_value} {start} to {end}. The one-day API window still "
                "hit the result cap, so full ingestion cannot be guaranteed without "
                "upstream pagination or a narrower source query."
            )
        accumulator.split_windows.append(
            {
                "house": house_value,
                "start_date": start,
                "end_date": end,
                "observed_count": len(divisions),
                "list_metadata_path": str(list_metadata_path),
                "children": [
                    {"start_date": split[0][0], "end_date": split[0][1]},
                    {"start_date": split[1][0], "end_date": split[1][1]},
                ],
            }
        )
        for child_start, child_end in split:
            if accumulator.remaining_limit == 0:
                break
            _fetch_they_vote_for_you_house_window(
                house_value=house_value,
                start=child_start,
                end=child_end,
                allow_truncated=allow_truncated,
                accumulator=accumulator,
            )
        return

    accepted_divisions = divisions
    if accumulator.remaining_limit is not None:
        accepted_divisions = divisions[: accumulator.remaining_limit]
        accumulator.remaining_limit -= len(accepted_divisions)

    accumulator.listed_count += len(accepted_divisions)
    accumulator.accepted_windows.append(
        {
            "house": house_value,
            "start_date": start,
            "end_date": end,
            "listed_count": len(divisions),
            "accepted_count": len(accepted_divisions),
            "list_metadata_path": str(list_metadata_path),
        }
    )

    for division in accepted_divisions:
        division_id = division.get("id")
        if division_id is None:
            raise RuntimeError(f"Division list item is missing id: {division}")
        accumulator.detail_metadata_paths.append(
            str(
                _fetch_json_endpoint(
                    endpoint=f"divisions/{division_id}.json",
                    params={},
                    source_id=_clean_source_id(f"they_vote_for_you_api_division_{division_id}"),
                    source_name=f"They Vote For You API: division {division_id}",
                    source_type="division_vote_api_detail",
                )
            )
        )


def fetch_they_vote_for_you_divisions(
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    house: str | None = None,
    limit: int | None = None,
    allow_truncated: bool = False,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    start, end = _default_start_end(start_date, end_date)
    list_metadata_paths: list[str] = []
    detail_metadata_paths: list[str] = []
    accepted_windows: list[dict[str, Any]] = []
    split_windows: list[dict[str, Any]] = []
    listed_count = 0

    for house_value in _house_values(house):
        accumulator = _DivisionFetchAccumulator(
            list_metadata_paths=[],
            detail_metadata_paths=[],
            accepted_windows=[],
            split_windows=[],
            remaining_limit=limit,
        )
        _fetch_they_vote_for_you_house_window(
            house_value=house_value,
            start=start,
            end=end,
            allow_truncated=allow_truncated,
            accumulator=accumulator,
        )
        list_metadata_paths.extend(accumulator.list_metadata_paths)
        detail_metadata_paths.extend(accumulator.detail_metadata_paths)
        accepted_windows.extend(accumulator.accepted_windows)
        split_windows.extend(accumulator.split_windows)
        listed_count += accumulator.listed_count

    timestamp = _timestamp()
    target_dir = processed_dir / "they_vote_for_you_division_fetches"
    target_dir.mkdir(parents=True, exist_ok=True)
    summary_path = target_dir / f"{timestamp}.summary.json"
    summary = {
        "generated_at": timestamp,
        "start_date": start,
        "end_date": end,
        "house": house,
        "limit_per_house": limit,
        "allow_truncated": allow_truncated,
        "listed_count": listed_count,
        "detail_count_fetched": len(detail_metadata_paths),
        "list_request_count": len(list_metadata_paths),
        "accepted_windows": accepted_windows,
        "split_windows": split_windows,
        "list_metadata_paths": list_metadata_paths,
        "detail_metadata_paths": detail_metadata_paths,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path


def latest_they_vote_for_you_fetch_summary(processed_dir: Path = PROCESSED_DIR) -> Path:
    return _latest_file(processed_dir / "they_vote_for_you_division_fetches", "*.summary.json")


def latest_they_vote_for_you_divisions_jsonl(processed_dir: Path = PROCESSED_DIR) -> Path | None:
    target_dir = processed_dir / "they_vote_for_you_divisions"
    if not target_dir.exists():
        return None
    candidates = sorted(target_dir.glob("*.jsonl"), reverse=True)
    return candidates[0] if candidates else None


def normalize_house(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    if cleaned in {"representatives", "house", "house of representatives", "reps"}:
        return "house"
    if cleaned == "senate":
        return "senate"
    raise ValueError(f"Unknown They Vote For You house value: {value!r}")


def normalize_vote_value(value: str) -> str:
    cleaned = str(value or "").strip().lower().replace(" ", "_")
    if cleaned in {"yes", "aye", "ayes", "for"}:
        return "aye"
    if cleaned in {"no", "noes", "against"}:
        return "no"
    if cleaned in {"absent", "did_not_vote", "not_voting"}:
        return "absent"
    if cleaned in {"abstain", "abstained"}:
        return "abstain"
    if cleaned in {"paired", "pair"}:
        return "paired"
    if cleaned in {"tell_aye", "teller_aye"}:
        return "tell_aye"
    if cleaned in {"tell_no", "teller_no"}:
        return "tell_no"
    return "unknown"


def _as_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _person_from_vote(vote: dict[str, Any]) -> dict[str, Any]:
    person = vote.get("person") or vote.get("member") or {}
    if not isinstance(person, dict):
        person = {}
    return person


def _vote_person_name(vote: dict[str, Any], person: dict[str, Any]) -> str:
    explicit_name = str(
        person.get("name")
        or person.get("full_name")
        or vote.get("name")
        or vote.get("person_name")
        or vote.get("member_name")
        or ""
    ).strip()
    if explicit_name:
        return explicit_name
    first = str(person.get("first_name") or vote.get("first_name") or "").strip()
    last = str(person.get("last_name") or vote.get("last_name") or "").strip()
    return f"{first} {last}".strip()


def _party_name(vote: dict[str, Any], person: dict[str, Any]) -> str:
    party = person.get("party") or vote.get("party")
    if isinstance(party, dict):
        return str(party.get("name") or party.get("short_name") or "").strip()
    return str(party or "").strip()


def _policy_record(item: dict[str, Any]) -> dict[str, Any]:
    policy = item.get("policy") if isinstance(item.get("policy"), dict) else item
    policy_id = policy.get("id") or item.get("policy_id")
    return {
        "tvfy_policy_id": _as_int(policy_id),
        "name": str(policy.get("name") or item.get("policy_name") or "").strip(),
        "description": str(policy.get("description") or "").strip(),
        "provisional": policy.get("provisional"),
        "last_edited_at": policy.get("last_edited_at"),
        "vote": str(item.get("vote") or "").strip(),
        "raw": item,
    }


def _bill_name(bill: Any) -> str:
    if isinstance(bill, dict):
        return str(bill.get("name") or bill.get("title") or bill.get("short_title") or "").strip()
    return str(bill or "").strip()


def normalize_division_detail(metadata_path: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload = json.loads(Path(metadata["body_path"]).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected division detail object in {metadata_path}")

    policies = [
        _policy_record(item)
        for item in payload.get("policy_divisions", [])
        if isinstance(item, dict)
    ]
    bills = [_bill_name(item) for item in payload.get("bills", [])]
    bills = [name for name in bills if name]

    votes = []
    for index, vote in enumerate(payload.get("votes", []), start=1):
        if not isinstance(vote, dict):
            continue
        person = _person_from_vote(vote)
        tvfy_person_id = _as_int(person.get("id") or vote.get("person_id") or vote.get("member_id"))
        votes.append(
            {
                "tvfy_person_id": tvfy_person_id,
                "person_name": _vote_person_name(vote, person),
                "electorate": str(person.get("electorate") or vote.get("electorate") or "").strip(),
                "state": str(person.get("state") or vote.get("state") or "").strip(),
                "party": _party_name(vote, person),
                "vote": normalize_vote_value(vote.get("vote") or vote.get("voted") or vote.get("option")),
                "raw_vote": vote.get("vote") or vote.get("voted") or vote.get("option"),
                "rebelled_against_party": bool(
                    vote.get("rebelled")
                    or vote.get("rebelled_against_party")
                    or vote.get("rebellion")
                ),
                "source_index": index,
                "raw": vote,
            }
        )

    chamber = normalize_house(str(payload.get("house") or ""))
    tvfy_division_id = _as_int(payload.get("id"))
    return {
        "schema_version": "they_vote_for_you_division_v1",
        "source": "they_vote_for_you",
        "source_metadata_path": str(metadata_path),
        "source_url": metadata["source"]["url"],
        "external_id": f"they_vote_for_you:division:{tvfy_division_id}",
        "tvfy_division_id": tvfy_division_id,
        "chamber": chamber,
        "division_date": payload.get("date"),
        "division_number": _as_int(payload.get("number")),
        "clock_time": payload.get("clock_time"),
        "title": str(payload.get("name") or "").strip() or f"Division {tvfy_division_id}",
        "bill_name": "; ".join(bills) if bills else "",
        "motion_text": str(payload.get("summary") or "").strip(),
        "aye_count": _as_int(payload.get("aye_votes")),
        "no_count": _as_int(payload.get("no_votes")),
        "possible_turnout": _as_int(payload.get("possible_turnout")),
        "rebellions_count": _as_int(payload.get("rebellions")),
        "edited": bool(payload.get("edited")),
        "policies": policies,
        "bills": bills,
        "votes": votes,
        "raw_keys": sorted(payload.keys()),
        "metadata": {
            "parser_name": PARSER_NAME,
            "parser_version": PARSER_VERSION,
            "clock_time": payload.get("clock_time"),
            "source_evidence_class": "third_party_civic",
            "source_caveat": (
                "They Vote For You is a reputable civic data source, not the official "
                "parliamentary source of record. Public claims should preserve this caveat."
            ),
        },
    }


def extract_they_vote_for_you_divisions(
    fetch_summary_path: Path | None = None,
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    fetch_summary_path = fetch_summary_path or latest_they_vote_for_you_fetch_summary(processed_dir)
    fetch_summary = json.loads(fetch_summary_path.read_text(encoding="utf-8"))
    detail_paths = [Path(path) for path in fetch_summary["detail_metadata_paths"]]

    timestamp = _timestamp()
    target_dir = processed_dir / "they_vote_for_you_divisions"
    target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = target_dir / f"{timestamp}.jsonl"
    summary_path = target_dir / f"{timestamp}.summary.json"

    divisions = [normalize_division_detail(path) for path in detail_paths]
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for division in divisions:
            handle.write(json.dumps(division, sort_keys=True) + "\n")

    vote_count = sum(len(division["votes"]) for division in divisions)
    summary = {
        "generated_at": timestamp,
        "fetch_summary_path": str(fetch_summary_path),
        "jsonl_path": str(jsonl_path),
        "division_count": len(divisions),
        "vote_count": vote_count,
        "chamber_counts": {
            chamber: sum(1 for division in divisions if division["chamber"] == chamber)
            for chamber in sorted({division["chamber"] for division in divisions})
        },
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary_path
