"""AEC Register of Entities ingestion (Batch C PR 1: fetch + raw archive).

Fetches the official public AEC Register of Entities at
https://transparency.aec.gov.au/RegisterOfEntities for each registered
client type, preserves the raw HTML page + each paginated JSON POST response
under data/raw/aec_register_of_entities/<client_type>/<timestamp>/, and
writes a processed JSONL of normalized register-row observations under
data/processed/aec_register_of_entities/<client_type>/<timestamp>.jsonl.

Provenance and redaction rules:

- The endpoint requires an ASP.NET Core anti-forgery token. We GET the page,
  extract the token from the hidden form input, then POST the
  ClientDetailsRead endpoint with the token + the session anti-forgery cookie.
- Raw archive metadata REDACTS the token (replacing it with the literal
  string ``__redacted_anti_forgery_token__``) and REDACTS every cookie value
  (preserving cookie names only). Request and response headers that carry
  ``Cookie`` or ``Set-Cookie`` are also redacted. Tokens and cookie values
  are session-disposable and have no public-data value once a request has
  completed.
- AEC field names that are misspelled in the upstream data are preserved
  verbatim: ``RegisterOfPolitcalParties``, ``LinkToRegisterOfPolitcalParties``,
  ``AmmendmentNumber``. Downstream loaders should also use these exact names.
- Source/licence wording is conservative: ``Official public AEC register;
  public redistribution/licence terms to be recorded before public data
  redistribution.`` Do not promise reuse permission until terms are
  captured in the repo.

Loader behaviour (PR 2) is intentionally NOT in this module. PR 2 will:

- Preserve every register row as an official registration observation
  (distinct from the canonical ``party`` table).
- For ``associatedentity.AssociatedParties`` segments, resolve through a
  curated, deterministic branch alias map (no fuzzy similarity).
- Auto-create ``party_entity_link`` rows only when a segment maps to
  exactly one canonical ``party.id``.

This module's responsibility is only fetch + raw archive + normalized
JSONL output, plus a CLI entry point that is wired in cli.py.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import asdict
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, OpenerDirector, Request, build_opener

from au_politics_money.config import PROCESSED_DIR, RAW_DIR, USER_AGENT
from au_politics_money.ingest.sources import get_source

PARSER_NAME = "aec_register_of_entities_v1"
PARSER_VERSION = "1"

BASE_URL = "https://transparency.aec.gov.au"
PAGE_URL_TEMPLATE = f"{BASE_URL}/RegisterOfEntities?clientType={{client_type}}"
DETAILS_URL = f"{BASE_URL}/RegisterOfEntities/ClientDetailsRead"

# AEC client_type values discovered via the live probe. Note the AEC uses
# "thirdparty" for the third-party register; "thirdpartycampaigner" returns
# HTTP 500 on this endpoint and must NOT be sent.
CLIENT_TYPES: tuple[str, ...] = (
    "politicalparty",
    "associatedentity",
    "significantthirdparty",
    "thirdparty",
)

DEFAULT_PAGE_SIZE = 200
HARD_PAGE_LIMIT = 50  # Refuse runaway pagination.

_TOKEN_INPUT_PATTERN = re.compile(
    r'<input[^>]*name="__RequestVerificationToken"[^>]*value="([^"]+)"',
    re.IGNORECASE,
)
_REDACTED_TOKEN_LITERAL = "__redacted_anti_forgery_token__"
_REDACTED_COOKIE_LITERAL = "__redacted_cookie_value__"

# Source IDs in the registry are namespaced per client_type so each fetch is
# its own auditable source_document chain.
SOURCE_ID_BY_CLIENT_TYPE = {
    "politicalparty": "aec_register_of_entities_politicalparty",
    "associatedentity": "aec_register_of_entities_associatedentity",
    "significantthirdparty": "aec_register_of_entities_significantthirdparty",
    "thirdparty": "aec_register_of_entities_thirdparty",
}


class AECRegisterFetchError(RuntimeError):
    """Raised on any unrecoverable fetch/parse error during register ingestion."""


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_session() -> tuple[OpenerDirector, CookieJar]:
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    opener.addheaders = [
        ("User-Agent", USER_AGENT),
        ("Accept-Language", "en-AU,en;q=0.9"),
    ]
    return opener, jar


def _extract_token(html: str) -> str:
    matches = _TOKEN_INPUT_PATTERN.findall(html)
    if not matches:
        raise AECRegisterFetchError(
            "Could not locate __RequestVerificationToken in AEC Register page HTML; "
            "upstream layout may have changed."
        )
    unique = set(matches)
    if len(unique) > 1:
        raise AECRegisterFetchError(
            "AEC Register page returned multiple distinct __RequestVerificationToken "
            "values; expected exactly one. Refusing to guess which to use."
        )
    return matches[0]


def _cookie_inventory(jar: CookieJar) -> list[dict[str, Any]]:
    """Cookie inventory with VALUES REDACTED. Preserves names only."""
    inventory: list[dict[str, Any]] = []
    for cookie in jar:
        inventory.append(
            {
                "name": cookie.name,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": bool(cookie.secure),
                "value": _REDACTED_COOKIE_LITERAL,
                "value_length": len(cookie.value or ""),
            }
        )
    return inventory


def _redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    redacted: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in {"cookie", "set-cookie"}:
            redacted[key] = _REDACTED_COOKIE_LITERAL
        else:
            redacted[key] = value
    return redacted


def _redact_request_params(params: dict[str, str]) -> dict[str, str]:
    sanitised: dict[str, str] = {}
    for key, value in params.items():
        if key == "__RequestVerificationToken":
            sanitised[key] = _REDACTED_TOKEN_LITERAL
        else:
            sanitised[key] = value
    return sanitised


def _http_get(opener: OpenerDirector, url: str, *, timeout: int = 60) -> tuple[int, bytes, dict[str, str]]:
    request = Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        body = exc.read() if exc.fp is not None else b""
        return exc.code, body, dict(exc.headers.items()) if exc.headers else {}
    except URLError as exc:
        raise AECRegisterFetchError(f"GET {url} failed: {exc}") from exc


def _http_post_form(
    opener: OpenerDirector,
    url: str,
    fields: dict[str, str],
    *,
    referer: str,
    timeout: int = 60,
) -> tuple[int, bytes, dict[str, str]]:
    body = urlencode(fields).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": BASE_URL,
            "Referer": referer,
        },
    )
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, response.read(), dict(response.headers.items())
    except HTTPError as exc:
        body_err = exc.read() if exc.fp is not None else b""
        return exc.code, body_err, dict(exc.headers.items()) if exc.headers else {}
    except URLError as exc:
        raise AECRegisterFetchError(f"POST {url} failed: {exc}") from exc


def _write_archive(
    target_dir: Path,
    *,
    artifact_name: str,
    body: bytes,
    metadata: dict[str, Any],
) -> tuple[Path, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    body_path = target_dir / artifact_name
    body_path.write_bytes(body)
    metadata_path = target_dir / f"{artifact_name}.metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return body_path, metadata_path


_TYPE_FIELDS_PRESERVE_VERBATIM = {
    "ViewName",
    "ClientIdentifier",
    "FCRMClientId",
    "RegisterOfPolitcalParties",  # AEC typo preserved verbatim.
    "LinkToRegisterOfPolitcalParties",  # AEC typo preserved verbatim.
    "ShowInPoliticalPartyRegister",
    "ShowInAssociatedEntityRegister",
    "ShowInSignificantThirdPartyRegister",
    "ShowInThirdPartyRegister",
    "IsNonRegisteredBranch",
    "ClientType",
    "ClientTypeDescription",
    "ClientContactFirstName",
    "ClientContactLastName",
    "ClientContactFullName",
    "ClientName",
    "FinancialYear",
    "FinancialYearStartDate",
    "ReturnId",
    "ReturnType",
    "AssociatedParties",
    "RegisteredAsAssociatedEntity",
    "RegisteredAsSignificantThirdParty",
    "AmmendmentNumber",  # AEC typo preserved verbatim.
    "ReturnStatus",
}


def _split_associated_parties(value: Any) -> list[str]:
    """Split AEC AssociatedParties on ';', strip whitespace, drop empties.

    Preserves ordering; does not normalize case or strip parenthetical
    qualifiers — that work belongs to the PR 2 resolver.
    """
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [segment.strip() for segment in text.split(";") if segment.strip()]


def _normalize_register_row(
    raw_row: dict[str, Any],
    *,
    client_type: str,
    source_id: str,
    raw_metadata_path: Path,
    raw_body_path: Path,
    page_index: int,
    row_index_in_page: int,
) -> dict[str, Any]:
    """Build a JSONL-friendly observation that preserves provenance.

    Each register row is treated as one OFFICIAL REGISTRATION OBSERVATION.
    The row keeps every upstream field plus a stable observation key derived
    from ClientIdentifier + ReturnId/FinancialYear/ViewName. Distinct rows
    that differ on FinancialYear / ReturnId / ReturnType / ViewName /
    AmmendmentNumber / ReturnStatus must be preserved (per dev direction —
    do NOT collapse register observations by ClientIdentifier).
    """
    preserved = {key: raw_row.get(key) for key in _TYPE_FIELDS_PRESERVE_VERBATIM}
    associated_parties_raw = preserved.get("AssociatedParties")
    associated_party_segments = _split_associated_parties(associated_parties_raw)
    client_identifier = str(preserved.get("ClientIdentifier") or "").strip()
    if not client_identifier:
        raise AECRegisterFetchError(
            "AEC Register row is missing ClientIdentifier; refusing to normalize "
            "without a stable identity field."
        )
    observation_key = "|".join(
        [
            client_identifier,
            str(preserved.get("ReturnId") or "").strip(),
            str(preserved.get("FinancialYear") or "").strip(),
            str(preserved.get("ReturnType") or "").strip(),
            str(preserved.get("ViewName") or "").strip(),
            str(preserved.get("AmmendmentNumber") or "").strip(),
            str(preserved.get("ReturnStatus") or "").strip(),
        ]
    )
    observation_fingerprint = hashlib.sha256(
        observation_key.encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "aec_register_of_entities_observation_v1",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "source_id": source_id,
        "source_metadata_path": str(raw_metadata_path.resolve()),
        "source_body_path": str(raw_body_path.resolve()),
        "client_type": client_type,
        "client_identifier": client_identifier,
        "client_name": preserved.get("ClientName"),
        "client_contact_full_name": preserved.get("ClientContactFullName"),
        "view_name": preserved.get("ViewName"),
        "return_id": preserved.get("ReturnId"),
        "financial_year": preserved.get("FinancialYear"),
        "return_type": preserved.get("ReturnType"),
        "return_status": preserved.get("ReturnStatus"),
        "ammendment_number": preserved.get("AmmendmentNumber"),
        "is_non_registered_branch": preserved.get("IsNonRegisteredBranch"),
        "associated_parties_raw": associated_parties_raw,
        "associated_party_segments": associated_party_segments,
        "show_in_political_party_register": preserved.get("ShowInPoliticalPartyRegister"),
        "show_in_associated_entity_register": preserved.get("ShowInAssociatedEntityRegister"),
        "show_in_significant_third_party_register": preserved.get(
            "ShowInSignificantThirdPartyRegister"
        ),
        "show_in_third_party_register": preserved.get("ShowInThirdPartyRegister"),
        "registered_as_associated_entity": preserved.get("RegisteredAsAssociatedEntity"),
        "registered_as_significant_third_party": preserved.get(
            "RegisteredAsSignificantThirdParty"
        ),
        "register_of_political_parties_label": preserved.get("RegisterOfPolitcalParties"),
        "link_to_register_of_political_parties": preserved.get(
            "LinkToRegisterOfPolitcalParties"
        ),
        "page_index": page_index,
        "row_index_in_page": row_index_in_page,
        "observation_fingerprint": observation_fingerprint,
        "raw_row_field_names": sorted(raw_row.keys()),
        "raw_row": raw_row,
    }


def _validate_payload_shape(payload: Any, *, client_type: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise AECRegisterFetchError(
            f"AEC Register {client_type} response was not a JSON object."
        )
    rows = payload.get("Data")
    if not isinstance(rows, list):
        raise AECRegisterFetchError(
            f"AEC Register {client_type} response missing top-level 'Data' list; "
            f"top-level keys: {sorted(payload.keys())}."
        )
    return [row for row in rows if isinstance(row, dict)]


def fetch_register_of_entities(
    client_type: str,
    *,
    take: int = DEFAULT_PAGE_SIZE,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    timeout: int = 60,
    session_factory: Callable[[], tuple[OpenerDirector, CookieJar]] | None = None,
    timestamp_factory: Callable[[], str] | None = None,
) -> Path:
    """Fetch one client_type's register, archive raw artefacts, write JSONL.

    Returns the path to the processed JSONL summary. Raises
    `AECRegisterFetchError` on any unrecoverable fetch/parse failure.
    """
    if client_type not in SOURCE_ID_BY_CLIENT_TYPE:
        raise AECRegisterFetchError(
            f"Unsupported AEC Register client_type {client_type!r}; expected "
            f"one of {sorted(SOURCE_ID_BY_CLIENT_TYPE)}."
        )
    if take < 1 or take > 1000:
        raise AECRegisterFetchError(
            f"take={take} is outside the 1..1000 range supported by this fetcher."
        )

    source_id = SOURCE_ID_BY_CLIENT_TYPE[client_type]
    source = get_source(source_id)
    factory = session_factory or _build_session
    timestamp = (timestamp_factory or _timestamp)()

    raw_target_dir = raw_dir / source_id / timestamp
    raw_target_dir.mkdir(parents=True, exist_ok=True)

    opener, jar = factory()

    # Step 1: GET the register page, archive raw HTML, extract token.
    page_url = PAGE_URL_TEMPLATE.format(client_type=client_type)
    page_status, page_body, page_response_headers = _http_get(opener, page_url, timeout=timeout)
    page_metadata: dict[str, Any] = {
        "source": asdict(source),
        "fetched_at": timestamp,
        "phase": "register_page_get",
        "url": page_url,
        "http_status": page_status,
        "http_response_headers": _redact_headers(page_response_headers),
        "cookies_after_response": _cookie_inventory(jar),
        "content_length": len(page_body),
        "sha256": hashlib.sha256(page_body).hexdigest(),
        "redaction": {
            "anti_forgery_token": "redacted_in_archive_metadata",
            "cookie_values": "redacted_in_archive_metadata",
            "cookie_request_header": "never_persisted",
        },
    }
    page_body_path, page_metadata_path = _write_archive(
        raw_target_dir,
        artifact_name="register_page.html",
        body=page_body,
        metadata=page_metadata,
    )
    if page_status >= 400:
        raise AECRegisterFetchError(
            f"AEC Register page GET returned HTTP {page_status} for {client_type}; "
            f"see metadata at {page_metadata_path}"
        )
    token = _extract_token(page_body.decode("utf-8", errors="replace"))

    # Step 2: paginated POSTs.
    all_rows: list[dict[str, Any]] = []
    total_upstream: int | None = None
    page_artifact_paths: list[str] = []
    page_index = 0
    skip = 0
    while True:
        if page_index >= HARD_PAGE_LIMIT:
            raise AECRegisterFetchError(
                f"AEC Register fetcher exceeded HARD_PAGE_LIMIT={HARD_PAGE_LIMIT} pages "
                f"for client_type={client_type!r}; refusing to continue."
            )
        page_index += 1
        params = {
            "clientType": client_type,
            "page": str(skip // max(take, 1) + 1),
            "pageSize": str(take),
            "skip": str(skip),
            "take": str(take),
            "__RequestVerificationToken": token,
        }
        post_status, post_body, post_response_headers = _http_post_form(
            opener,
            DETAILS_URL,
            params,
            referer=page_url,
            timeout=timeout,
        )
        page_metadata = {
            "source": asdict(source),
            "fetched_at": timestamp,
            "phase": "client_details_read_post",
            "url": DETAILS_URL,
            "http_status": post_status,
            "http_response_headers": _redact_headers(post_response_headers),
            "cookies_after_response": _cookie_inventory(jar),
            "content_length": len(post_body),
            "sha256": hashlib.sha256(post_body).hexdigest(),
            "request_params_redacted": _redact_request_params(params),
            "page_index_within_session": page_index,
            "redaction": {
                "anti_forgery_token": "redacted_in_archive_metadata",
                "cookie_values": "redacted_in_archive_metadata",
                "cookie_request_header": "never_persisted",
            },
        }
        post_body_path, post_metadata_path = _write_archive(
            raw_target_dir,
            artifact_name=f"client_details_read_page_{page_index:03d}.json",
            body=post_body,
            metadata=page_metadata,
        )
        page_artifact_paths.append(str(post_metadata_path.resolve()))
        if post_status >= 400:
            raise AECRegisterFetchError(
                f"AEC Register POST returned HTTP {post_status} for "
                f"client_type={client_type!r} page={page_index}; "
                f"see metadata at {post_metadata_path}"
            )
        try:
            payload = json.loads(post_body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError as exc:
            raise AECRegisterFetchError(
                f"AEC Register POST returned non-JSON body for "
                f"client_type={client_type!r} page={page_index}: {exc}"
            ) from exc
        if isinstance(payload, dict) and total_upstream is None:
            try:
                total_upstream = int(payload.get("Total")) if payload.get("Total") is not None else None
            except (TypeError, ValueError):
                total_upstream = None
        rows = _validate_payload_shape(payload, client_type=client_type)
        for row_index, row in enumerate(rows):
            all_rows.append(
                _normalize_register_row(
                    row,
                    client_type=client_type,
                    source_id=source_id,
                    raw_metadata_path=post_metadata_path,
                    raw_body_path=post_body_path,
                    page_index=page_index,
                    row_index_in_page=row_index,
                )
            )
        if len(rows) < take:
            break
        skip += take

    if not all_rows:
        raise AECRegisterFetchError(
            f"AEC Register {client_type} fetch produced zero rows; refusing to "
            f"silently publish an empty observation set. See raw archive at "
            f"{raw_target_dir}"
        )
    if total_upstream is not None and len(all_rows) != total_upstream:
        # Not strictly an error — paginated fetches with intra-fetch updates
        # could differ — but worth recording so the loader can decide.
        completeness_note = (
            f"upstream Total={total_upstream} but normalized {len(all_rows)} rows; "
            f"rows were paginated across {page_index} POSTs"
        )
    else:
        completeness_note = "upstream Total matches normalized row count"

    processed_target_dir = processed_dir / "aec_register_of_entities" / client_type
    processed_target_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = processed_target_dir / f"{timestamp}.jsonl"
    summary_path = processed_target_dir / f"{timestamp}.summary.json"

    with jsonl_path.open("w", encoding="utf-8") as handle:
        for row in all_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    summary = {
        "schema_version": "aec_register_of_entities_summary_v1",
        "parser_name": PARSER_NAME,
        "parser_version": PARSER_VERSION,
        "source_id": source_id,
        "client_type": client_type,
        "generated_at": timestamp,
        "raw_dir": str(raw_target_dir.resolve()),
        "raw_page_metadata_path": str(page_metadata_path.resolve()),
        "raw_post_metadata_paths": page_artifact_paths,
        "jsonl_path": str(jsonl_path.resolve()),
        "row_count": len(all_rows),
        "upstream_total": total_upstream,
        "page_index_count": page_index,
        "page_size_used": take,
        "completeness_note": completeness_note,
        "redaction_policy": (
            "Anti-forgery token and all cookie values are redacted from raw archive "
            "metadata; cookie request headers are never persisted; raw response "
            "bodies are preserved verbatim."
        ),
        "source_attribution_caveat": (
            "Official public AEC register; public redistribution/licence terms to be "
            "recorded before public data redistribution."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def fetch_all_registers_of_entities(
    *,
    client_types: Iterable[str] = CLIENT_TYPES,
    take: int = DEFAULT_PAGE_SIZE,
    raw_dir: Path = RAW_DIR,
    processed_dir: Path = PROCESSED_DIR,
    timeout: int = 60,
    session_factory: Callable[[], tuple[OpenerDirector, CookieJar]] | None = None,
    timestamp_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Fetch every supported client_type. Each session is independent so a
    failure on one client_type does not leak token/cookie state to the next.

    Returns a dict with per-client_type summary paths and any errors.
    """
    summary_paths: dict[str, str] = {}
    errors: dict[str, str] = {}
    for client_type in client_types:
        try:
            path = fetch_register_of_entities(
                client_type,
                take=take,
                raw_dir=raw_dir,
                processed_dir=processed_dir,
                timeout=timeout,
                session_factory=session_factory,
                timestamp_factory=timestamp_factory,
            )
        except AECRegisterFetchError as exc:
            errors[client_type] = str(exc)
            continue
        summary_paths[client_type] = str(path.resolve())
    return {
        "summary_paths": summary_paths,
        "errors": errors,
    }


def latest_register_of_entities_summary(
    client_type: str,
    *,
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    """Return the most recent summary.json for a client_type if present."""
    target_dir = processed_dir / "aec_register_of_entities" / client_type
    if not target_dir.exists():
        return None
    candidates = sorted(target_dir.glob("*.summary.json"), reverse=True)
    return candidates[0] if candidates else None
