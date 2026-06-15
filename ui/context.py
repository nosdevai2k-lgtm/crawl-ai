"""Shared UI runtime context."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.document_store import DocumentStore
    from src.settings import Settings


@dataclass
class UIContext:
    root: Path
    settings: Settings
    storage: DocumentStore | None
    storage_error: str | None
    config_path: Path
