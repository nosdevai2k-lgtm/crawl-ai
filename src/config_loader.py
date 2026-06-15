"""Load config.yaml into typed structures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml


SourceType = Literal["url", "rss", "search", "browser", "file", "youtube", "deep_crawl"]
ExtractMode = Literal["article", "raw"]
LlmMode = Literal["general", "persons"]

_VALID_SOURCE_TYPES = frozenset(
    {"url", "rss", "search", "browser", "file", "youtube", "deep_crawl"}
)
_VALID_EXTRACT_MODES = frozenset({"article", "raw"})
_VALID_LLM_MODES = frozenset({"general", "persons"})


@dataclass
class SourceConfig:
    id: str
    type: SourceType
    schedule_cron: str
    extract: ExtractMode
    url: str | None = None
    query: str | None = None
    max_results: int = 5
    rss_max_entries: int = 20
    # browser-specific options
    wait_selector: str | None = None
    next_button_selector: str | None = None
    max_pages: int = 1
    js_code: list[str] | None = None
    # file-specific options
    file_path: str | None = None
    # youtube-specific options
    max_videos: int = 10
    # deep_crawl-specific options
    max_depth: int = 2
    max_crawl_pages: int = 20
    # LLM structuring mode
    llm_mode: LlmMode = "general"
    # tải ảnh trên trang (url/browser)
    crawl_images: bool = False
    # theo link trên trang (gồm khác domain) để crawl thêm text + ảnh
    expand_links: bool = False
    expand_max: int = 5
    # độ ưu tiên nguồn: cao hơn chạy trước (nguồn chính thống nên đặt cao).
    # None = tự suy ra từ độ tin cậy domain (source_trust).
    priority: int | None = None


def _parse_js_code(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        out = [str(x).strip() for x in raw if str(x).strip()]
        return out or None
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return None


def _source_config_from_item(item: dict[str, Any], *, validate_id: bool = True) -> SourceConfig:
    """Parse one YAML/dict source entry into SourceConfig."""
    sid = str(item["id"])
    stype = str(item["type"])
    if stype not in _VALID_SOURCE_TYPES:
        raise ValueError(f"Unknown source type for {sid}: {stype}")

    extract = str(item.get("extract") or "article")
    if extract not in _VALID_EXTRACT_MODES:
        raise ValueError(f"Invalid extract mode for {sid}: {extract}")

    llm_mode = str(item.get("llm_mode") or "general")
    if llm_mode not in _VALID_LLM_MODES:
        raise ValueError(f"Invalid llm_mode for {sid}: {llm_mode}")

    return SourceConfig(
        id=sid,
        type=stype,  # type: ignore[arg-type]
        schedule_cron=str(item.get("schedule_cron") or "0 * * * *"),
        extract=extract,  # type: ignore[arg-type]
        url=str(item["url"]) if item.get("url") else None,
        query=str(item["query"]) if item.get("query") else None,
        max_results=int(item.get("max_results") or 5),
        rss_max_entries=int(item.get("rss_max_entries") or 20),
        wait_selector=str(item["wait_selector"]) if item.get("wait_selector") else None,
        next_button_selector=(
            str(item["next_button_selector"]) if item.get("next_button_selector") else None
        ),
        max_pages=int(item.get("max_pages") or 1),
        js_code=_parse_js_code(item.get("js_code")),
        file_path=str(item["file_path"]) if item.get("file_path") else None,
        max_videos=int(item.get("max_videos") or 10),
        max_depth=int(item.get("max_depth") or 2),
        max_crawl_pages=int(item.get("max_crawl_pages") or 20),
        llm_mode=llm_mode,  # type: ignore[arg-type]
        crawl_images=bool(item.get("crawl_images") or False),
        expand_links=bool(item.get("expand_links") or False),
        expand_max=int(item.get("expand_max") or 5),
        priority=(int(item["priority"]) if item.get("priority") is not None else None),
    )


def source_config_as_dict(s: SourceConfig) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": s.id,
        "type": s.type,
        "schedule_cron": s.schedule_cron,
        "extract": s.extract,
        "url": s.url,
        "query": s.query,
        "max_results": s.max_results,
        "rss_max_entries": s.rss_max_entries,
        "wait_selector": s.wait_selector,
        "next_button_selector": s.next_button_selector,
        "max_pages": s.max_pages,
        "file_path": s.file_path,
        "max_videos": s.max_videos,
        "max_depth": s.max_depth,
        "max_crawl_pages": s.max_crawl_pages,
        "llm_mode": s.llm_mode,
        "crawl_images": s.crawl_images,
        "expand_links": s.expand_links,
        "expand_max": s.expand_max,
    }
    if s.priority is not None:
        d["priority"] = s.priority
    if s.js_code:
        d["js_code"] = list(s.js_code)
    return d


def source_config_from_dict(d: dict[str, Any]) -> SourceConfig:
    return _source_config_from_item(d)


def load_config(path: Path) -> list[SourceConfig]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_sources: list[dict[str, Any]] = data.get("sources") or []
    return [_source_config_from_item(item) for item in raw_sources]
