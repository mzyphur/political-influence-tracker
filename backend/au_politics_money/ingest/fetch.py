from __future__ import annotations

import hashlib
import json
import mimetypes
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from au_politics_money.config import BROWSER_COMPATIBLE_USER_AGENT, RAW_DIR, USER_AGENT
from au_politics_money.models import SourceRecord


SAFE_RESPONSE_HEADERS = {
    "cache-control",
    "content-disposition",
    "content-encoding",
    "content-language",
    "content-length",
    "content-type",
    "date",
    "etag",
    "expires",
    "last-modified",
    "server",
    "vary",
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _suffix_for_content(url: str, content_type: str | None) -> str:
    parsed_suffix = Path(urlparse(url).path).suffix
    if parsed_suffix:
        return parsed_suffix
    if content_type:
        guessed = mimetypes.guess_extension(content_type.split(";")[0].strip())
        if guessed:
            return guessed
    return ".bin"


def _request_headers(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    user_agent = (
        BROWSER_COMPATIBLE_USER_AGENT
        if parsed.netloc.lower() == "parlinfo.aph.gov.au"
        else USER_AGENT
    )
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-AU,en;q=0.9",
    }


def _safe_response_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in SAFE_RESPONSE_HEADERS
    }


def fetch_source(source: SourceRecord, raw_dir: Path = RAW_DIR, timeout: int = 60) -> Path:
    """Fetch a source URL and store raw bytes plus audit metadata.

    This intentionally does not parse source contents. Parsing should be separate
    so raw acquisition remains reproducible and auditable.
    """

    run_ts = _timestamp()
    target_dir = raw_dir / source.source_id / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)

    request_headers = _request_headers(source.url)
    request = Request(source.url, headers=request_headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            headers = _safe_response_headers(dict(response.headers.items()))
            final_url = response.url
    except HTTPError as exc:
        body = exc.read()
        status = exc.code
        headers = _safe_response_headers(dict(exc.headers.items()) if exc.headers else {})
        final_url = source.url
    except URLError as exc:
        metadata_path = target_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "source": asdict(source),
                    "fetched_at": run_ts,
                    "ok": False,
                    "error": str(exc),
                    "request_headers": request_headers,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        raise

    sha256 = hashlib.sha256(body).hexdigest()
    content_type = headers.get("Content-Type") or headers.get("content-type")
    suffix = _suffix_for_content(final_url, content_type)
    body_path = target_dir / f"body{suffix}"
    body_path.write_bytes(body)

    metadata = {
        "source": asdict(source),
        "fetched_at": run_ts,
        "ok": 200 <= status < 400,
        "http_status": status,
        "final_url": final_url,
        "content_type": content_type,
        "content_length": len(body),
        "sha256": sha256,
        "body_path": str(body_path),
        "headers": headers,
        "request_headers": request_headers,
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not metadata["ok"]:
        raise RuntimeError(
            f"Fetch failed for {source.source_id}: HTTP {status}; metadata: {metadata_path}"
        )
    return metadata_path
