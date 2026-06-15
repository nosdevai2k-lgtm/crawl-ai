"""URL filter chain for deep crawl link filtering.

Inspired by crawl4ai's FilterChain, DomainFilter, URLPatternFilter,
and ContentTypeFilter.
"""

from __future__ import annotations

import fnmatch
import re
from typing import List, Set, Union
from urllib.parse import urlparse


class URLFilter:
    """Base filter class."""

    def apply(self, url: str) -> bool:
        return True


class FilterChain:
    """Chain of URL filters — URL must pass ALL filters."""

    def __init__(self, filters: List[URLFilter] | None = None):
        self.filters = list(filters or [])

    def apply(self, url: str) -> bool:
        return all(f.apply(url) for f in self.filters)


class DomainFilter(URLFilter):
    """Filter URLs by allowed/blocked domains (supports subdomains)."""

    def __init__(
        self,
        allowed_domains: List[str] | str | None = None,
        blocked_domains: List[str] | str | None = None,
    ):
        if isinstance(allowed_domains, str):
            allowed_domains = [allowed_domains]
        if isinstance(blocked_domains, str):
            blocked_domains = [blocked_domains]
        self._allowed = frozenset(d.lower() for d in (allowed_domains or []))
        self._blocked = frozenset(d.lower() for d in (blocked_domains or []))

    def apply(self, url: str) -> bool:
        domain = urlparse(url).netloc.lower()
        for b in self._blocked:
            if domain == b or domain.endswith(f".{b}"):
                return False
        if not self._allowed:
            return True
        return any(domain == a or domain.endswith(f".{a}") for a in self._allowed)


class URLPatternFilter(URLFilter):
    """Filter URLs by glob/regex patterns.

    Args:
        patterns: Glob or regex patterns to match.
        reverse: If True, reject matching URLs instead of accepting them.
    """

    def __init__(
        self,
        patterns: Union[str, List[str]],
        reverse: bool = False,
    ):
        if isinstance(patterns, str):
            patterns = [patterns]
        self._reverse = reverse
        self._compiled: list[re.Pattern] = []
        for p in patterns:
            if p.startswith("^") or p.endswith("$"):
                self._compiled.append(re.compile(p))
            else:
                self._compiled.append(re.compile(fnmatch.translate(p)))

    def apply(self, url: str) -> bool:
        matched = any(r.search(url) for r in self._compiled)
        return not matched if self._reverse else matched


class ContentTypeFilter(URLFilter):
    """Reject URLs whose extension indicates non-HTML content."""

    _SKIP_EXTENSIONS = frozenset({
        "jpg", "jpeg", "png", "gif", "svg", "webp", "ico", "bmp",
        "mp3", "mp4", "avi", "mov", "wmv", "flv", "mkv", "webm",
        "zip", "gz", "tar", "rar", "7z", "exe", "msi", "dmg",
        "woff", "woff2", "ttf", "otf", "eot",
        "css", "js",
    })

    def apply(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        if "." in path.split("/")[-1]:
            ext = path.rsplit(".", 1)[-1]
            if ext in self._SKIP_EXTENSIONS:
                return False
        return True
