"""Async parallel fetching for batch crawls.

Inspired by crawl4ai's async browser pool. Uses httpx.AsyncClient
to fetch multiple URLs concurrently.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

import httpx

from .fetch import FetchResult, build_request_headers


@dataclass
class AsyncFetchResult:
    url: str
    status_code: int
    body: bytes
    content_type: Optional[str]
    etag: Optional[str]
    last_modified: Optional[str]
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status_code < 400


async def async_fetch_url(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
) -> AsyncFetchResult:
    """Fetch a single URL using an existing async client."""
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        return AsyncFetchResult(
            url=str(resp.url),
            status_code=resp.status_code,
            body=resp.content,
            content_type=resp.headers.get("content-type"),
            etag=resp.headers.get("etag"),
            last_modified=resp.headers.get("last-modified"),
        )
    except Exception as e:
        return AsyncFetchResult(
            url=url, status_code=0, body=b"",
            content_type=None, etag=None, last_modified=None,
            error=f"{type(e).__name__}: {e}",
        )


async def async_fetch_many(
    urls: list[str],
    *,
    user_agent: str = "crawl-ai/1.0",
    timeout: float = 30.0,
    max_concurrent: int = 10,
) -> list[AsyncFetchResult]:
    """Fetch multiple URLs in parallel with concurrency limit.

    Args:
        urls: List of URLs to fetch.
        user_agent: HTTP User-Agent string.
        timeout: Per-request timeout in seconds.
        max_concurrent: Max simultaneous connections.

    Returns:
        List of AsyncFetchResult in same order as input URLs.
    """
    headers = build_request_headers(user_agent)
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_one(client: httpx.AsyncClient, url: str) -> AsyncFetchResult:
        async with semaphore:
            return await async_fetch_url(client, url, headers=headers)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [_fetch_one(client, url) for url in urls]
        return await asyncio.gather(*tasks)


def fetch_many_sync(
    urls: list[str],
    *,
    user_agent: str = "crawl-ai/1.0",
    timeout: float = 30.0,
    max_concurrent: int = 10,
) -> list[AsyncFetchResult]:
    """Synchronous wrapper for async_fetch_many."""
    return asyncio.run(
        async_fetch_many(urls, user_agent=user_agent, timeout=timeout, max_concurrent=max_concurrent)
    )
