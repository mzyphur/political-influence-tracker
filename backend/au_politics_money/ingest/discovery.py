from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from au_politics_money.config import PROCESSED_DIR, RAW_DIR
from au_politics_money.models import DiscoveredLink, SourceRecord


def latest_body_path(source_id: str, raw_dir: Path = RAW_DIR) -> Path | None:
    source_dir = raw_dir / source_id
    if not source_dir.exists():
        return None

    for run_dir in sorted(source_dir.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if metadata.get("ok") is False:
                continue
        candidates = sorted(path for path in run_dir.iterdir() if path.name.startswith("body."))
        if candidates:
            return candidates[0]
    return None


def latest_discovered_links_path(
    source_id: str,
    processed_dir: Path = PROCESSED_DIR,
) -> Path | None:
    source_dir = processed_dir / "discovered_links" / source_id
    if not source_dir.exists():
        return None
    candidates = sorted(source_dir.glob("*.json"), reverse=True)
    return candidates[0] if candidates else None


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _link_type(url: str, title: str) -> str:
    path = urlparse(url).path.lower()
    title_lower = title.lower()
    if path.endswith(".js") or "javascript" in title_lower:
        return "js"
    if path.endswith(".csv") or "csv" in title_lower:
        return "csv"
    if path.endswith(".pdf") or "pdf" in title_lower:
        return "pdf"
    if path.endswith(".zip") or "/download/all" in path:
        return "zip_or_download"
    if path.endswith((".doc", ".docx")) or "word" in title_lower:
        return "word"
    return "html"


def _should_keep_link(source_id: str, url: str, title: str) -> bool:
    path = urlparse(url).path.lower()
    title_lower = title.lower()

    if source_id == "aec_transparency_downloads":
        return "/download/all" in path

    if source_id == "aph_contacts_csv":
        return path.endswith(".csv") or path.endswith(".pdf")

    if source_id == "aph_members_interests_48":
        return path.endswith(".pdf") or "pdf" in title_lower

    if source_id == "aph_senators_interests":
        if "senators-interests-register/build/env.js" in path:
            return True
        return path.endswith(".pdf") or "pdf" in title_lower

    if source_id == "aec_federal_boundaries_gis":
        return path.endswith(".zip") or "zip" in title_lower

    if source_id == "aph_house_votes_and_proceedings":
        if "parlinfo.aph.gov.au" in urlparse(url).netloc.lower():
            return "chamber/votes" in url.lower()
        return False

    if source_id == "aph_senate_journals":
        if "parlinfo.aph.gov.au" in urlparse(url).netloc.lower():
            return "chamber/journals" in url.lower()
        return False

    return False


def discover_links_from_html(source: SourceRecord, html: str) -> list[DiscoveredLink]:
    soup = BeautifulSoup(html, "html.parser")
    links: list[DiscoveredLink] = []
    seen: set[str] = set()

    candidates: list[tuple[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        candidates.append((str(anchor["href"]).strip(), anchor.get_text(" ", strip=True)))

    if source.source_id == "aph_senators_interests":
        for script in soup.find_all("script", src=True):
            src = str(script["src"]).strip()
            candidates.append((src, Path(urlparse(src).path).name or "script"))

    for href, raw_title in candidates:
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        url = urljoin(source.url, href)
        title = _clean_text(raw_title) or Path(urlparse(url).path).name

        if not _should_keep_link(source.source_id, url, title):
            continue
        if url in seen:
            continue

        seen.add(url)
        links.append(
            DiscoveredLink(
                parent_source_id=source.source_id,
                title=title,
                url=url,
                link_type=_link_type(url, title),
            )
        )

    return links


def discover_links_from_body(source: SourceRecord, body_path: Path) -> list[DiscoveredLink]:
    html = body_path.read_text(encoding="utf-8", errors="replace")
    return discover_links_from_html(source, html)


def write_discovered_links(
    source: SourceRecord,
    links: list[DiscoveredLink],
    processed_dir: Path = PROCESSED_DIR,
) -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_dir = processed_dir / "discovered_links" / source.source_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{timestamp}.json"
    payload = {
        "source": source.to_dict(),
        "generated_at": timestamp,
        "link_count": len(links),
        "links": [link.to_dict() for link in links],
    }
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target_path


def read_discovered_links(path: Path) -> list[DiscoveredLink]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [DiscoveredLink(**item) for item in payload["links"]]
