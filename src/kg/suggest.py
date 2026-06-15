"""Unified entity suggest — local KG + optional Video KG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .storage import KGStorage
from .video_kg_client import video_kg_suggest


def suggest_entities(
    db_path: Path,
    query: str,
    *,
    labels: list[str] | None = None,
    limit: int = 8,
    video_kg_url: str = "",
) -> list[dict[str, Any]]:
    kg = KGStorage(db_path)
    local = kg.suggest_entities(query, labels=labels, limit=limit)
    for it in local:
        it["_source"] = "local"

    if not video_kg_url:
        return local[:limit]

    label_str = ",".join(labels) if labels else "Person,Location,Topic,Event,Festival"
    remote = video_kg_suggest(video_kg_url, query, labels=label_str, limit=limit)

    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for it in local + remote:
        key = (it.get("name") or "").lower()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(it)
        if len(merged) >= limit:
            break
    return merged
