"""Client for external Video KG Search API (FastAPI on :8009)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

_log = logging.getLogger(__name__)


def _base(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    return u if u else ""


def video_kg_available(base_url: str, *, timeout: float = 5.0) -> bool:
    b = _base(base_url)
    if not b:
        return False
    try:
        r = httpx.get(f"{b}/api/stats", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def video_kg_structured(
    base_url: str,
    *,
    entities: str = "",
    topics: str = "",
    has_people: str = "any",
    media: str = "both",
    top_k: int = 30,
    timeout: float = 30.0,
) -> dict[str, Any]:
    b = _base(base_url)
    if not b:
        return {"count": 0, "results": [], "error": "VIDEO_KG_BASE_URL not set"}
    params = {
        "entities": entities,
        "topics": topics,
        "has_people": has_people,
        "media": media,
        "top_k": top_k,
    }
    try:
        r = httpx.get(f"{b}/api/structured", params=params, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        for item in data.get("results") or []:
            item["_source"] = "video_kg"
        data["_source"] = "video_kg"
        return data
    except Exception as exc:
        _log.warning("Video KG request failed: %s", exc)
        return {"count": 0, "results": [], "error": str(exc), "_source": "video_kg"}


def video_kg_suggest(
    base_url: str,
    query: str,
    *,
    labels: str = "Person,Location,Topic,Event,Festival",
    limit: int = 8,
    timeout: float = 10.0,
) -> list[dict[str, Any]]:
    b = _base(base_url)
    if not b or not query.strip():
        return []
    try:
        r = httpx.get(
            f"{b}/api/suggest",
            params={"q": query, "label": labels, "limit": limit},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        items = data.get("items") or data if isinstance(data, list) else []
        for it in items:
            it["_source"] = "video_kg"
        return items
    except Exception as exc:
        _log.debug("Video KG suggest failed: %s", exc)
        return []


def video_kg_stats(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    b = _base(base_url)
    if not b:
        return {}
    try:
        r = httpx.get(f"{b}/api/stats", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def video_kg_media_url(base_url: str, video_id: str) -> str:
    b = _base(base_url)
    return urljoin(b + "/", f"api/media?path={video_id}")
