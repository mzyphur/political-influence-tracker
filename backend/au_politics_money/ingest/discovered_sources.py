from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

from au_politics_money.models import DiscoveredLink, SourceRecord


def child_source_id(parent_source_id: str, link: DiscoveredLink) -> str:
    path_name = Path(urlparse(link.url).path).name.lower()
    clean_name = "".join(char if char.isalnum() else "_" for char in path_name).strip("_")
    digest = hashlib.sha1(link.url.encode("utf-8")).hexdigest()[:10]
    if not clean_name:
        clean_name = link.link_type
    return f"{parent_source_id}__{clean_name[:50]}__{digest}"


def source_from_discovered_link(parent: SourceRecord, link: DiscoveredLink) -> SourceRecord:
    return SourceRecord(
        source_id=child_source_id(parent.source_id, link),
        name=f"{parent.name}: {link.title}",
        jurisdiction=parent.jurisdiction,
        level=parent.level,
        source_type=f"discovered_{link.link_type}",
        url=link.url,
        expected_format=link.link_type,
        update_frequency=parent.update_frequency,
        priority=parent.priority,
        notes=f"Discovered from parent source {parent.source_id}. {link.notes}".strip(),
    )
