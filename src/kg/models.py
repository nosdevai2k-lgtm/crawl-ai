"""KG dataclasses shared across extract/scenes/indexer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedEntity:
    id: str
    label: str
    name: str
    why: str


@dataclass
class ExtractedMedia:
    media_kind: str
    media_ref: str
    title: str = ""
    snippet: str = ""
    date: str = ""
    timestamp_sec: float | None = None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    media: list[ExtractedMedia] = field(default_factory=list)
    doc_title: str = ""
    doc_summary: str = ""
    doc_date: str = ""
