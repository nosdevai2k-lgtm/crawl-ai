"""HTTP fetch with optional If-None-Match (304 Not Modified)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import httpx


def build_request_headers(
    user_agent: str,
    *,
    extra: Optional[dict[str, str]] = None,
) -> dict[str, str]:
    """
    Headers that behave closer to a normal browser.
    Wikimedia sites reject generic python/httpx User-Agents (403); use a
    descriptive USER_AGENT (see docs/CRAWL.md).
    """
    ua = (user_agent or "crawl-ai/1.0").strip()
    h: dict[str, str] = {
        "User-Agent": ua,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "application/pdf;q=0.9,image/avif,image/webp,*/*;q=0.7"
        ),
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    # Only add Sec-Fetch headers if UA looks like a real browser
    if "Mozilla/" in ua or "Chrome/" in ua:
        h["Sec-Fetch-Dest"] = "document"
        h["Sec-Fetch-Mode"] = "navigate"
        h["Sec-Fetch-Site"] = "none"
        h["Sec-Fetch-User"] = "?1"
    if extra:
        h.update(extra)
    return h


@dataclass
class FetchResult:
    url: str
    status_code: int
    body: bytes
    content_type: Optional[str]
    etag: Optional[str]
    last_modified: Optional[str]
    not_modified: bool = False


_RETRYABLE_STATUS = {429, 503, 502, 504}


def fetch_url(
    url: str,
    *,
    user_agent: str,
    timeout: float,
    method: str = "GET",
    headers: Optional[dict[str, str]] = None,
    if_none_match: Optional[str] = None,
    if_modified_since: Optional[str] = None,
    max_retries: int = 3,
    backoff_sec: float = 1.0,
) -> FetchResult:
    import time

    base_headers = build_request_headers(user_agent, extra=headers)
    if if_none_match:
        base_headers["If-None-Match"] = if_none_match
    if if_modified_since:
        base_headers["If-Modified-Since"] = if_modified_since

    last_exc: Exception | None = None
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for attempt in range(max_retries + 1):
            try:
                resp = client.request(method, url, headers=base_headers)
                if resp.status_code == 304:
                    return FetchResult(
                        url=str(resp.request.url),
                        status_code=304,
                        body=b"",
                        content_type=resp.headers.get("content-type"),
                        etag=resp.headers.get("etag"),
                        last_modified=resp.headers.get("last-modified"),
                        not_modified=True,
                    )
                if resp.status_code in _RETRYABLE_STATUS and attempt < max_retries:
                    wait = backoff_sec * (2 ** attempt)
                    if resp.status_code == 429:
                        ra = resp.headers.get("retry-after")
                        if ra and ra.isdigit():
                            wait = max(wait, float(ra))
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return FetchResult(
                    url=str(resp.url),
                    status_code=resp.status_code,
                    body=resp.content,
                    content_type=resp.headers.get("content-type"),
                    etag=resp.headers.get("etag"),
                    last_modified=resp.headers.get("last-modified"),
                    not_modified=False,
                )
            except httpx.TimeoutException as e:
                last_exc = e
                if attempt < max_retries:
                    time.sleep(backoff_sec * (2 ** attempt))
                    continue
                raise
            except httpx.HTTPStatusError:
                raise
    raise last_exc or RuntimeError("fetch_url: retries exhausted")
