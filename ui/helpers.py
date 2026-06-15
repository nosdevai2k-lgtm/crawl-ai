"""Shared UI helpers for crawl workflow."""

from __future__ import annotations

import hashlib
import re

from src.config_loader import SourceConfig
from src.extract import SourcePayload
from src.quick_sources import (
    quick_file_source,
    quick_rss_source,
    quick_search_source,
    quick_url_source,
    quick_youtube_source,
)

from ui.constants import CRAWL_MODES

_SUGGESTION_KIND_TO_PIPELINE = {
    "URL": "URL",
    "RSS": "RSS",
    "Search": "Search",
}


def apply_suggestion_to_crawl_form(suggestion: dict[str, str]) -> bool:
    """Điền gợi ý auto-crawl lên form tab Crawl. Trả False nếu kind không hỗ trợ."""
    kind = suggestion.get("kind", "")
    value = (suggestion.get("value") or "").strip()
    pipeline_kind = _SUGGESTION_KIND_TO_PIPELINE.get(kind)
    if not pipeline_kind or not value:
        return False
    label = next(
        (lbl for lbl, pk, *_ in CRAWL_MODES if pk == pipeline_kind),
        CRAWL_MODES[0][0],
    )
    st.session_state["crawl_mode_pick"] = label
    st.session_state["main_paste_url"] = value
    st.session_state["ui_nav"] = "Crawl"
    return True


def blob_to_payload(b: dict) -> SourcePayload:
    return SourcePayload(
        text=str(b.get("text") or ""),
        meta=dict(b.get("meta") or {}),
        etag=b.get("etag"),
        last_modified=b.get("last_modified"),
    )


def payload_to_blob(p: SourcePayload) -> dict[str, object]:
    return {
        "text": p.text,
        "meta": dict(p.meta),
        "etag": p.etag,
        "last_modified": p.last_modified,
    }


def widget_key_fragment(label: str) -> str:
    digest = hashlib.sha256(label.encode("utf-8", errors="replace")).hexdigest()[:10]
    short = re.sub(r"[^a-zA-Z0-9]+", "_", label)[:32].strip("_") or "field"
    return f"{short}_{digest}"


def build_src_quick(
    kind: str,
    raw: str,
    extract: str,
    rss_n: int,
    dd_n: int,
    nick: str,
    llm_mode: str = "general",
    max_videos: int = 10,
    max_depth: int = 2,
    max_crawl_pages: int = 20,
    crawl_images: bool = False,
) -> SourceConfig:
    if kind == "URL":
        src = quick_url_source(raw, extract=extract, source_id=nick or None)
    elif kind == "RSS":
        src = quick_rss_source(
            raw,
            extract=extract,
            rss_max_entries=rss_n,
            source_id=nick or None,
        )
    elif kind == "File":
        src = quick_file_source(raw, extract=extract, source_id=nick or None)
    elif kind == "YouTube":
        src = quick_youtube_source(raw, max_videos=max_videos, source_id=nick or None)
    elif kind == "DeepCrawl":
        _sid = nick or f"deep_{hashlib.sha256(raw.encode()).hexdigest()[:12]}"
        src = SourceConfig(
            id=_sid,
            type="deep_crawl",
            schedule_cron="0 * * * *",
            extract=extract,  # type: ignore[arg-type]
            url=raw,
            max_depth=max_depth,
            max_crawl_pages=max_crawl_pages,
        )
    else:
        src = quick_search_source(raw, max_results=dd_n, source_id=nick or None)
    if llm_mode in ("general", "persons"):
        src.llm_mode = llm_mode  # type: ignore[assignment]
    src.crawl_images = bool(crawl_images)
    return src
