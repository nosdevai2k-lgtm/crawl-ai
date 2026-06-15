"""Retry with proxy escalation for blocked URLs.

Inspired by crawl4ai's 3-tier anti-bot detection with proxy fallback.
Tries: direct → proxy1 → proxy2 → ... until success or exhausted.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .fetch import FetchResult, build_request_headers


@dataclass
class ProxyConfig:
    """Proxy configuration."""
    server: str  # e.g. "http://proxy:8080" or "socks5://proxy:1080"
    username: str | None = None
    password: str | None = None

    @property
    def url(self) -> str:
        if self.username and self.password:
            # Insert credentials into URL
            scheme, rest = self.server.split("://", 1)
            return f"{scheme}://{self.username}:{self.password}@{rest}"
        return self.server

    DIRECT = None  # Sentinel for no-proxy


def load_proxies_from_env() -> list[ProxyConfig]:
    """Load proxy list from PROXY_LIST env var (comma-separated URLs)."""
    raw = os.environ.get("PROXY_LIST", "").strip()
    if not raw:
        return []
    return [ProxyConfig(server=p.strip()) for p in raw.split(",") if p.strip()]


def _is_blocked(status_code: int, body: bytes) -> bool:
    """Detect if response indicates blocking."""
    if status_code in (403, 429, 503, 520, 521, 522, 523):
        return True
    # Check for common block page indicators
    text_sample = body[:2000].decode("utf-8", errors="ignore").lower()
    block_signals = ["captcha", "access denied", "blocked", "rate limit", "cloudflare"]
    return any(s in text_sample for s in block_signals)


def fetch_with_retry(
    url: str,
    *,
    user_agent: str = "crawl-ai/1.0",
    timeout: float = 30.0,
    proxies: list[ProxyConfig] | None = None,
    max_retries: int = 3,
    backoff_sec: float = 2.0,
) -> FetchResult:
    """Fetch URL with retry and proxy escalation.

    Tries direct first, then each proxy in order.
    On each attempt, retries up to max_retries with backoff.
    """
    headers = build_request_headers(user_agent)
    proxy_chain: list[Optional[ProxyConfig]] = [None]  # Start with direct
    if proxies:
        proxy_chain.extend(proxies)

    last_error: Exception | None = None

    for proxy in proxy_chain:
        proxy_url = proxy.url if proxy else None
        transport_kwargs = {"proxy": proxy_url} if proxy_url else {}

        for attempt in range(max_retries):
            try:
                with httpx.Client(timeout=timeout, **transport_kwargs) as client:
                    resp = client.get(url, headers=headers, follow_redirects=True)

                if not _is_blocked(resp.status_code, resp.content):
                    return FetchResult(
                        url=str(resp.url),
                        status_code=resp.status_code,
                        body=resp.content,
                        content_type=resp.headers.get("content-type"),
                        etag=resp.headers.get("etag"),
                        last_modified=resp.headers.get("last-modified"),
                        not_modified=resp.status_code == 304,
                    )
                # Blocked — try next attempt or proxy
                last_error = httpx.HTTPStatusError(
                    f"Blocked ({resp.status_code})", request=resp.request, response=resp
                )
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_error = e

            if attempt < max_retries - 1:
                time.sleep(backoff_sec * (attempt + 1))

    # All attempts failed — return error result
    raise last_error or RuntimeError(f"All retries exhausted for {url}")
