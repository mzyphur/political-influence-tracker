"""Tests for AEC Register of Entities fetch + raw archive (Batch C PR 1).

The live endpoint requires an ASP.NET anti-forgery token + matching cookie.
These tests substitute a fake `OpenerDirector` so no live HTTP is performed
and assert: token extraction, cookie redaction, AEC field-name preservation
including the upstream typos (RegisterOfPolitcalParties, AmmendmentNumber),
and the loud-failure modes (missing token, malformed JSON, zero rows, HTTP
errors, the thirdpartycampaigner trap).
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from http.cookiejar import Cookie, CookieJar
from io import BytesIO
from pathlib import Path

import pytest

from au_politics_money.ingest import aec_register_entities as aec
from au_politics_money.ingest.aec_register_entities import (
    AECRegisterFetchError,
    CLIENT_TYPES,
    SOURCE_ID_BY_CLIENT_TYPE,
    _extract_token,
    _redact_headers,
    _redact_request_params,
    _split_associated_parties,
    fetch_register_of_entities,
    fetch_all_registers_of_entities,
    latest_register_of_entities_summary,
)


# --- low-level helpers ----------------------------------------------------


def test_extract_token_finds_hidden_input() -> None:
    html = (
        '<form><input name="__RequestVerificationToken" value="abc.xyz-123" />'
        '<input name="__RequestVerificationToken" value="abc.xyz-123" /></form>'
    )
    assert _extract_token(html) == "abc.xyz-123"


def test_extract_token_raises_when_missing() -> None:
    with pytest.raises(AECRegisterFetchError, match="__RequestVerificationToken"):
        _extract_token("<html><body>nope</body></html>")


def test_extract_token_raises_when_multiple_distinct() -> None:
    html = (
        '<input name="__RequestVerificationToken" value="aaa" />'
        '<input name="__RequestVerificationToken" value="bbb" />'
    )
    with pytest.raises(AECRegisterFetchError, match="multiple distinct"):
        _extract_token(html)


def test_redact_headers_redacts_cookie_set_cookie_only() -> None:
    redacted = _redact_headers(
        {
            "Content-Type": "text/html",
            "Set-Cookie": ".AspNetCore.Antiforgery.X=very-secret",
            "X-Frame-Options": "DENY",
            "cookie": "session=should-not-leak",
        }
    )
    assert redacted["Content-Type"] == "text/html"
    assert redacted["X-Frame-Options"] == "DENY"
    assert redacted["Set-Cookie"] == "__redacted_cookie_value__"
    assert redacted["cookie"] == "__redacted_cookie_value__"


def test_redact_request_params_only_strips_token() -> None:
    redacted = _redact_request_params(
        {
            "clientType": "associatedentity",
            "page": "1",
            "take": "200",
            "__RequestVerificationToken": "secret-token",
        }
    )
    assert redacted["__RequestVerificationToken"] == "__redacted_anti_forgery_token__"
    assert redacted["clientType"] == "associatedentity"
    assert redacted["take"] == "200"


def test_split_associated_parties_handles_multi_branch_with_trailing_semicolons() -> None:
    text = (
        "Australian Labor Party (ACT Branch); "
        "Australian Labor Party (N.S.W. Branch); "
        "Australian Labor Party (Northern Territory) Branch; "
    )
    segments = _split_associated_parties(text)
    assert segments == [
        "Australian Labor Party (ACT Branch)",
        "Australian Labor Party (N.S.W. Branch)",
        "Australian Labor Party (Northern Territory) Branch",
    ]


def test_split_associated_parties_handles_none_and_empty() -> None:
    assert _split_associated_parties(None) == []
    assert _split_associated_parties("") == []
    assert _split_associated_parties("   ;  ;  ") == []


def test_client_types_does_not_include_thirdpartycampaigner_trap() -> None:
    """The live endpoint returns HTTP 500 for `thirdpartycampaigner`; it must
    NOT be in the CLIENT_TYPES tuple even though the original AEC docs mention
    that label. The actual working value is `thirdparty`."""
    assert "thirdpartycampaigner" not in CLIENT_TYPES
    assert "thirdparty" in CLIENT_TYPES


def test_source_id_mapping_covers_every_client_type() -> None:
    assert set(SOURCE_ID_BY_CLIENT_TYPE) == set(CLIENT_TYPES)


# --- fake HTTP plumbing ---------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        status: int,
        body: bytes,
        headers: dict[str, str],
        url: str | None = None,
    ):
        self.status = status
        self._body = body
        self.headers = _Headers(headers)
        self.fp = BytesIO(body)
        self.code = status
        self.url = url

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Headers:
    def __init__(self, items: dict[str, str]):
        self._items = items

    def items(self):
        return list(self._items.items())


class _FakeOpener:
    """Mimics `urllib.request.OpenerDirector` enough for the fetcher.

    A scripted sequence of (method, url, response) entries is consumed in
    order; each `open` call asserts that the next scripted entry matches the
    incoming Request.
    """

    def __init__(self, scripted: list[dict]):
        self._scripted: Iterator[dict] = iter(scripted)
        self.calls: list[dict] = []
        self.addheaders: list[tuple[str, str]] = []

    def open(self, request, timeout: int = 60):  # noqa: D401
        try:
            entry = next(self._scripted)
        except StopIteration as exc:  # pragma: no cover - test bug if hit
            raise AssertionError(
                f"Unexpected extra request: {request.get_method()} {request.full_url}"
            ) from exc
        method = request.get_method()
        url = request.full_url
        body_bytes = request.data if request.data else b""
        self.calls.append(
            {
                "method": method,
                "url": url,
                "body": body_bytes.decode("utf-8") if body_bytes else "",
                "headers": dict(request.header_items()),
            }
        )
        assert entry["method"] == method, (entry, method)
        assert entry["url"] == url, (entry, url)
        return _FakeResponse(
            entry["response"]["status"],
            entry["response"]["body"],
            entry["response"].get("headers", {}),
            url=entry["response"].get("final_url", url),
        )


def _fake_session_factory(scripted: list[dict]):
    jar = CookieJar()
    # Pre-seed an antiforgery cookie so cookie-redaction logic has something
    # to redact during inventory.
    cookie = Cookie(
        version=0,
        name=".AspNetCore.Antiforgery.X",
        value="this-value-must-never-be-persisted",
        port=None,
        port_specified=False,
        domain="transparency.aec.gov.au",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=False,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={},
        rfc2109=False,
    )
    jar.set_cookie(cookie)
    opener = _FakeOpener(scripted)

    def factory():
        return opener, jar

    return factory, opener, jar


# --- end-to-end fetch tests ------------------------------------------------


def _register_page_html(token: str = "live.token-xyz") -> bytes:
    return (
        f'<html><body><form>'
        f'<input name="__RequestVerificationToken" value="{token}" />'
        f'<input name="__RequestVerificationToken" value="{token}" />'
        f"</form></body></html>"
    ).encode("utf-8")


def _client_details_payload(rows: list[dict], total: int | None = None) -> bytes:
    payload = {
        "Data": rows,
        "Total": total if total is not None else len(rows),
        "AggregateResults": None,
        "Errors": None,
    }
    return json.dumps(payload).encode("utf-8")


def _associatedentity_row_branches() -> dict:
    return {
        "ViewName": "Register of entities: Political parties",
        "ClientIdentifier": "28986",
        "FCRMClientId": None,
        "RegisterOfPolitcalParties": "Register - 1973 Foundation Pty Ltd",
        "LinkToRegisterOfPolitcalParties": "  https://www.aec.gov.au/example",
        "ShowInPoliticalPartyRegister": None,
        "ShowInAssociatedEntityRegister": "Y",
        "ShowInSignificantThirdPartyRegister": None,
        "ShowInThirdPartyRegister": None,
        "IsNonRegisteredBranch": "Registered",
        "ClientType": "associatedentity",
        "ClientTypeDescription": None,
        "ClientContactFirstName": "Dan",
        "ClientContactLastName": "Ashcroft",
        "ClientContactFullName": "Dan Ashcroft",
        "ClientName": "1973 Foundation Pty Ltd",
        "FinancialYear": "",
        "FinancialYearStartDate": None,
        "ReturnId": None,
        "ReturnType": None,
        "AssociatedParties": (
            "Australian Labor Party (ACT Branch); "
            "Australian Labor Party (N.S.W. Branch); "
        ),
        "RegisteredAsAssociatedEntity": "Yes",
        "RegisteredAsSignificantThirdParty": "No",
        "AmmendmentNumber": None,
        "ReturnStatus": None,
    }


def _associatedentity_row_individual() -> dict:
    row = _associatedentity_row_branches()
    row["ClientIdentifier"] = "99000"
    row["ClientName"] = "Independent Campaign Association Pty Ltd"
    row["AssociatedParties"] = "Allegra Spender;"
    return row


def test_fetch_register_of_entities_archives_raw_and_writes_jsonl(tmp_path: Path) -> None:
    rows_page1 = [_associatedentity_row_branches(), _associatedentity_row_individual()]
    scripted = [
        {
            "method": "GET",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities?clientType=associatedentity",
            "response": {
                "status": 200,
                "body": _register_page_html(),
                "headers": {
                    "Content-Type": "text/html; charset=utf-8",
                    "Set-Cookie": ".AspNetCore.Antiforgery.X=secret-cookie-value; path=/",
                },
            },
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {
                "status": 200,
                "body": _client_details_payload(rows_page1, total=2),
                "headers": {"Content-Type": "application/json; charset=utf-8"},
            },
        },
    ]
    factory, opener, _jar = _fake_session_factory(scripted)

    summary_path = fetch_register_of_entities(
        "associatedentity",
        take=200,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        session_factory=factory,
        timestamp_factory=lambda: "20260430T000000Z",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["client_type"] == "associatedentity"
    assert summary["row_count"] == 2
    assert summary["upstream_total"] == 2
    assert summary["page_index_count"] == 1
    assert summary["redaction_policy"].startswith("Anti-forgery token and all cookie values")
    assert "public redistribution" in summary["source_attribution_caveat"]

    jsonl = (
        Path(summary["jsonl_path"]).read_text(encoding="utf-8").splitlines()
    )
    assert len(jsonl) == 2
    first = json.loads(jsonl[0])
    # AEC typos preserved verbatim:
    assert first["register_of_political_parties_label"] == (
        "Register - 1973 Foundation Pty Ltd"
    )
    assert first["link_to_register_of_political_parties"] == (
        "  https://www.aec.gov.au/example"
    )
    assert "RegisterOfPolitcalParties" in first["raw_row"]  # AEC spelling
    assert "AmmendmentNumber" in first["raw_row"]
    # Multi-segment AssociatedParties split correctly:
    assert first["associated_party_segments"] == [
        "Australian Labor Party (ACT Branch)",
        "Australian Labor Party (N.S.W. Branch)",
    ]
    # Individual segment preserved as-is for PR 2 to filter:
    second = json.loads(jsonl[1])
    assert second["associated_party_segments"] == ["Allegra Spender"]

    # Raw archive: token + cookie redacted; HTML body verbatim.
    raw_html_path = tmp_path / "raw" / SOURCE_ID_BY_CLIENT_TYPE["associatedentity"] / "20260430T000000Z" / "register_page.html"
    raw_html = raw_html_path.read_text(encoding="utf-8")
    assert "__RequestVerificationToken" in raw_html  # raw HTML preserved verbatim
    page_metadata = json.loads(
        (raw_html_path.with_name("register_page.html.metadata.json")).read_text(encoding="utf-8")
    )
    assert page_metadata["http_response_headers"]["Set-Cookie"] == "__redacted_cookie_value__"
    assert page_metadata["cookies_after_response"][0]["value"] == "__redacted_cookie_value__"
    assert page_metadata["cookies_after_response"][0]["name"] == ".AspNetCore.Antiforgery.X"
    # Token is never echoed by GET so the page metadata has no token key, but
    # the redaction policy is named explicitly:
    assert page_metadata["redaction"]["anti_forgery_token"] == (
        "redacted_in_archive_metadata"
    )
    assert page_metadata["redaction"]["cookie_request_header"] == "never_persisted"

    # POST metadata: token redacted in request_params_redacted, never the
    # raw token literal "live.token-xyz".
    post_metadata_path = (
        raw_html_path.with_name("client_details_read_page_001.json.metadata.json")
    )
    post_metadata = json.loads(post_metadata_path.read_text(encoding="utf-8"))
    assert post_metadata["request_params_redacted"]["__RequestVerificationToken"] == (
        "__redacted_anti_forgery_token__"
    )
    assert "live.token-xyz" not in json.dumps(post_metadata)
    assert post_metadata["request_params_redacted"]["clientType"] == "associatedentity"

    # Confirm the POST request body the fetcher sent included the token (the
    # redaction is for archive metadata only, not for the actual upstream call).
    assert any("__RequestVerificationToken=live.token-xyz" in c["body"] for c in opener.calls)


def test_fetch_register_paginates_until_short_page(tmp_path: Path) -> None:
    full_page = [
        _associatedentity_row_branches() | {"ClientIdentifier": str(2000 + i)}
        for i in range(50)
    ]
    short_page = [
        _associatedentity_row_branches() | {"ClientIdentifier": str(3000 + i)}
        for i in range(7)
    ]
    scripted = [
        {
            "method": "GET",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities?clientType=associatedentity",
            "response": {"status": 200, "body": _register_page_html(), "headers": {}},
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {
                "status": 200,
                "body": _client_details_payload(full_page, total=57),
                "headers": {},
            },
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {
                "status": 200,
                "body": _client_details_payload(short_page, total=57),
                "headers": {},
            },
        },
    ]
    factory, _opener, _jar = _fake_session_factory(scripted)
    summary_path = fetch_register_of_entities(
        "associatedentity",
        take=50,
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
        session_factory=factory,
        timestamp_factory=lambda: "20260430T120000Z",
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["row_count"] == 57
    assert summary["upstream_total"] == 57
    assert summary["page_index_count"] == 2
    assert summary["completeness_note"] == "upstream Total matches normalized row count"


def test_fetch_register_raises_on_zero_rows(tmp_path: Path) -> None:
    scripted = [
        {
            "method": "GET",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities?clientType=politicalparty",
            "response": {"status": 200, "body": _register_page_html(), "headers": {}},
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {
                "status": 200,
                "body": _client_details_payload([], total=0),
                "headers": {},
            },
        },
    ]
    factory, _opener, _jar = _fake_session_factory(scripted)
    with pytest.raises(AECRegisterFetchError, match="zero rows"):
        fetch_register_of_entities(
            "politicalparty",
            take=200,
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            session_factory=factory,
            timestamp_factory=lambda: "20260430T130000Z",
        )


def test_fetch_register_raises_on_http_error(tmp_path: Path) -> None:
    scripted = [
        {
            "method": "GET",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities?clientType=politicalparty",
            "response": {"status": 200, "body": _register_page_html(), "headers": {}},
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {
                "status": 500,
                "body": b"<html>err</html>",
                "headers": {"Content-Type": "text/html"},
            },
        },
    ]
    factory, _opener, _jar = _fake_session_factory(scripted)
    with pytest.raises(AECRegisterFetchError, match="HTTP 500"):
        fetch_register_of_entities(
            "politicalparty",
            take=200,
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            session_factory=factory,
            timestamp_factory=lambda: "20260430T140000Z",
        )


def test_fetch_register_raises_on_malformed_json(tmp_path: Path) -> None:
    scripted = [
        {
            "method": "GET",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities?clientType=thirdparty",
            "response": {"status": 200, "body": _register_page_html(), "headers": {}},
        },
        {
            "method": "POST",
            "url": "https://transparency.aec.gov.au/RegisterOfEntities/ClientDetailsRead",
            "response": {"status": 200, "body": b"not-json-{", "headers": {}},
        },
    ]
    factory, _opener, _jar = _fake_session_factory(scripted)
    with pytest.raises(AECRegisterFetchError, match="non-JSON body"):
        fetch_register_of_entities(
            "thirdparty",
            take=200,
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
            session_factory=factory,
            timestamp_factory=lambda: "20260430T150000Z",
        )


def test_fetch_register_rejects_unsupported_client_type(tmp_path: Path) -> None:
    with pytest.raises(AECRegisterFetchError, match="thirdpartycampaigner"):
        fetch_register_of_entities(
            "thirdpartycampaigner",
            raw_dir=tmp_path / "raw",
            processed_dir=tmp_path / "processed",
        )


def test_fetch_all_collects_per_client_type_summaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(client_type: str, **kwargs):  # noqa: ANN001
        calls.append(client_type)
        if client_type == "thirdparty":
            raise AECRegisterFetchError("synthetic-fetch-failure")
        out = tmp_path / f"{client_type}.summary.json"
        out.write_text("{}")
        return out

    monkeypatch.setattr(aec, "fetch_register_of_entities", fake_fetch)
    result = fetch_all_registers_of_entities(
        client_types=("politicalparty", "associatedentity", "thirdparty"),
        raw_dir=tmp_path / "raw",
        processed_dir=tmp_path / "processed",
    )
    assert calls == ["politicalparty", "associatedentity", "thirdparty"]
    assert set(result["summary_paths"]) == {"politicalparty", "associatedentity"}
    assert "thirdparty" in result["errors"]
    assert "synthetic-fetch-failure" in result["errors"]["thirdparty"]


def test_latest_summary_returns_none_when_missing(tmp_path: Path) -> None:
    assert (
        latest_register_of_entities_summary(
            "associatedentity", processed_dir=tmp_path
        )
        is None
    )


def test_latest_summary_returns_most_recent_when_present(tmp_path: Path) -> None:
    target = tmp_path / "aec_register_of_entities" / "associatedentity"
    target.mkdir(parents=True)
    (target / "20260101T000000Z.summary.json").write_text("{}")
    (target / "20260202T000000Z.summary.json").write_text("{}")
    latest = latest_register_of_entities_summary(
        "associatedentity", processed_dir=tmp_path
    )
    assert latest is not None
    assert latest.name == "20260202T000000Z.summary.json"
