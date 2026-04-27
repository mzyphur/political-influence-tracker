from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal


SourcePriority = Literal["core", "high", "medium", "later"]


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    name: str
    jurisdiction: str
    level: str
    source_type: str
    url: str
    expected_format: str
    update_frequency: str
    priority: SourcePriority
    notes: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class DiscoveredLink:
    parent_source_id: str
    title: str
    url: str
    link_type: str
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)
