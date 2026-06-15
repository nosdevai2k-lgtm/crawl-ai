"""Crawl tự động bằng prompt: gợi ý nguồn (LLM) -> crawl thẳng -> lưu."""

from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from .config_loader import SourceConfig
from .crawl_planner import (
    assert_safe_http_url,
    fetch_seed_context,
    suggest_crawl_sources,
)
from .document_store import DocumentStore
from .pipeline import PipelineResult, run_source
from .quick_sources import quick_rss_source, quick_search_source, quick_url_source
from .settings import Settings


@dataclass
class AutoCrawlItem:
    suggestion: dict[str, str]
    result: PipelineResult | None = None
    error: str | None = None


def suggestion_to_source(s: dict[str, str], *, crawl_images: bool = False, expand_links: bool = False) -> SourceConfig:
    kind = s.get("kind", "")
    value = s.get("value", "")
    if kind == "URL":
        src = quick_url_source(value, expand_links=expand_links)
        src.crawl_images = crawl_images
        return src
    if kind == "RSS":
        return quick_rss_source(value)
    if kind == "Search":
        return quick_search_source(value)
    raise ValueError(f"Unsupported suggestion kind: {kind}")


def plan_crawl(
    goal: str,
    settings: Settings,
    *,
    client: OpenAI | None = None,
    seed_url: str | None = None,
) -> list[dict[str, str]]:
    """Prompt -> gợi ý nguồn (đọc seed URL làm ngữ cảnh nếu có). Không crawl."""
    seed_excerpt: str | None = None
    if seed_url:
        try:
            seed_excerpt = fetch_seed_context(seed_url, settings)
        except Exception:
            seed_excerpt = None
    return suggest_crawl_sources(
        settings, user_goal=goal, seed_url=seed_url,
        seed_excerpt=seed_excerpt, client=client,
    )


def crawl_suggestions(
    suggestions: list[dict[str, str]],
    storage: DocumentStore,
    settings: Settings,
    *,
    client: OpenAI | None = None,
    crawl_images: bool = False,
    expand_links: bool = False,
) -> list[AutoCrawlItem]:
    """Crawl danh sách gợi ý (đã chọn) -> lưu DB. Validate + bỏ trùng URL."""
    items: list[AutoCrawlItem] = []
    seen: set[str] = set()
    for sug in suggestions:
        item = AutoCrawlItem(suggestion=sug)
        try:
            value = sug.get("value", "")
            if sug.get("kind") in ("URL", "RSS"):
                value = assert_safe_http_url(value)
            dedup_key = f"{sug.get('kind')}::{value.strip().lower()}"
            if dedup_key in seen:
                item.error = "duplicate suggestion (skipped)"
                items.append(item)
                continue
            seen.add(dedup_key)
            src = suggestion_to_source(sug, crawl_images=crawl_images, expand_links=expand_links)
            item.result = run_source(src, storage, settings, client)
        except Exception as exc:  # noqa: BLE001
            item.error = f"{type(exc).__name__}: {exc}"
        items.append(item)
    return items


def auto_crawl(
    goal: str,
    storage: DocumentStore,
    settings: Settings,
    *,
    client: OpenAI | None = None,
    seed_url: str | None = None,
    crawl_images: bool = False,
    expand_links: bool = False,
) -> list[AutoCrawlItem]:
    """Prompt -> gợi ý nguồn -> crawl từng nguồn -> lưu DB (một phát, cho CLI)."""
    suggestions = plan_crawl(goal, settings, client=client, seed_url=seed_url)
    return crawl_suggestions(
        suggestions, storage, settings, client=client, crawl_images=crawl_images,
        expand_links=expand_links,
    )
