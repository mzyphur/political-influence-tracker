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

from au_politics_money.config import RAW_DIR, USER_AGENT
from au_politics_money.models import SourceRecord


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


def fetch_source(source: SourceRecord, raw_dir: Path = RAW_DIR, timeout: int = 60) -> Path:
    """Fetch a source URL and store raw bytes plus audit metadata.

    This intentionally does not parse source contents. Parsing should be separate
    so raw acquisition remains reproducible and auditable.
    """

    run_ts = _timestamp()
    target_dir = raw_dir / source.source_id / run_ts
    target_dir.mkdir(parents=True, exist_ok=True)

    request = Request(source.url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = response.status
            headers = dict(response.headers.items())
            final_url = response.url
    except HTTPError as exc:
        body = exc.read()
        status = exc.code
        headers = dict(exc.headers.items()) if exc.headers else {}
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
    }
    metadata_path = target_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata_path

