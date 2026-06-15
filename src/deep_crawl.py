"""Deep crawl: BFS multi-page crawling with link discovery.

Inspired by crawl4ai's BFSDeepCrawlStrategy. Crawl a start URL,
discover internal links, and crawl them up to max_depth/max_pages.
Supports FilterChain for URL filtering and state export/resume.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .url_filters import FilterChain

logger = logging.getLogger(__name__)


@dataclass
class CrawlPage:
    url: str
    depth: int
    html: str
    text: str
    links: list[str]


@dataclass
class DeepCrawlResult:
    pages: list[CrawlPage]
    urls_visited: set[str] = field(default_factory=set)
    urls_failed: list[str] = field(default_factory=list)
    state: Optional[Dict[str, Any]] = None


def _same_domain(url1: str, url2: str) -> bool:
    return urlparse(url1).netloc == urlparse(url2).netloc


def _normalize_url(url: str) -> str:
    """Strip fragment and trailing slash for dedup."""
    p = urlparse(url)
    path = p.path.rstrip("/") or "/"
    return f"{p.scheme}://{p.netloc}{path}"


def _extract_links(html: str, base_url: str) -> list[str]:
    """Extract all internal links from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absolute = urljoin(base_url, href)
        if _same_domain(base_url, absolute):
            links.append(_normalize_url(absolute))
    return list(set(links))


def _build_state(visited: set[str], pending: list, pages_crawled: int) -> Dict[str, Any]:
    """Build serializable crawl state for resume."""
    return {
        "visited": list(visited),
        "pending": [{"url": u, "depth": d} for u, d in pending],
        "pages_crawled": pages_crawled,
    }


def export_state_to_file(state: Dict[str, Any], path: str) -> None:
    """Save crawl state to JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)


def load_state_from_file(path: str) -> Dict[str, Any]:
    """Load crawl state from JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def deep_crawl_bfs(
    start_url: str,
    *,
    max_depth: int = 2,
    max_pages: int = 20,
    user_agent: str = "crawl-ai/1.0",
    timeout: float = 30.0,
    max_concurrent: int = 10,
    url_filter: Callable[[str], bool] | None = None,
    filter_chain: FilterChain | None = None,
    extract_text: Callable[[str], str] | None = None,
    resume_state: Dict[str, Any] | None = None,
    on_state_change: Callable[[Dict[str, Any]], None] | None = None,
) -> DeepCrawlResult:
    """BFS deep crawl starting from start_url.

    Args:
        filter_chain: FilterChain instance for URL filtering (crawl4ai-style).
        resume_state: Previously exported state dict to resume from.
        on_state_change: Callback invoked after each depth level with current state.
    """
    from .async_fetch import fetch_many_sync
    from .extract import extract_from_html

    # Initialize from resume state or fresh
    if resume_state:
        visited = set(resume_state.get("visited", []))
        current_level = [(item["url"], item["depth"]) for item in resume_state.get("pending", [])]
        pages_crawled = resume_state.get("pages_crawled", 0)
    else:
        visited: set[str] = set()
        start = _normalize_url(start_url)
        visited.add(start)
        current_level = [(start, 0)]
        pages_crawled = 0

    pages: list[CrawlPage] = []
    failed: list[str] = []

    def _passes_filter(url: str) -> bool:
        if filter_chain and not filter_chain.apply(url):
            return False
        if url_filter and not url_filter(url):
            return False
        return True

    while current_level and pages_crawled < max_pages:
        urls_to_fetch = [(u, d) for u, d in current_level if _passes_filter(u)]
        if not urls_to_fetch:
            break

        budget = max_pages - pages_crawled
        urls_to_fetch = urls_to_fetch[:budget]

        results = fetch_many_sync(
            [u for u, _ in urls_to_fetch],
            user_agent=user_agent,
            timeout=timeout,
            max_concurrent=max_concurrent,
        )

        next_level: list[tuple[str, int]] = []

        for (url, depth), fr in zip(urls_to_fetch, results):
            if not fr.ok:
                logger.warning("Deep crawl failed %s: %s", url, fr.error)
                failed.append(url)
                continue
            ct = (fr.content_type or "").lower()
            if "text/html" not in ct and "application/xhtml" not in ct:
                continue
            html = fr.body.decode("utf-8", errors="replace")

            text = extract_text(html) if extract_text else extract_from_html(html, mode="article")
            links = _extract_links(html, url)

            pages.append(CrawlPage(url=url, depth=depth, html=html, text=text, links=links))
            pages_crawled += 1

            if depth < max_depth:
                for link in links:
                    if link not in visited and len(visited) < max_pages * 3:
                        if _passes_filter(link):
                            visited.add(link)
                            next_level.append((link, depth + 1))

        current_level = next_level

        if on_state_change:
            on_state_change(_build_state(visited, current_level, pages_crawled))

    final_state = _build_state(visited, current_level, pages_crawled)
    return DeepCrawlResult(pages=pages, urls_visited=visited, urls_failed=failed, state=final_state)
