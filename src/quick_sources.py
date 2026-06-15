"""Tạo SourceConfig tạm cho crawl một lần (UI / CLI) — không cần sửa config.yaml."""

from __future__ import annotations

import hashlib
import re

from .config_loader import ExtractMode, SourceConfig


def _readable_slug(key: str, max_len: int = 40) -> str:
    """Slug ASCII dễ đọc từ URL (host + path cuối) hoặc câu query."""
    import unicodedata
    from urllib.parse import urlparse, unquote

    k = key.strip()
    if re.match(r"^https?://", k, re.I):
        p = urlparse(k)
        host = re.sub(r"^www\.", "", p.netloc).split(".")[0]
        tail = unquote(p.path.rstrip("/").split("/")[-1]) if p.path.rstrip("/") else ""
        k = f"{host} {tail}".strip()
    s = unicodedata.normalize("NFKD", k).replace("đ", "d").replace("Đ", "D")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].strip("-")


def _slug_id(prefix: str, key: str, max_len: int = 56) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:6]
    base = re.sub(r"[^a-zA-Z0-9_-]+", "_", prefix).strip("_") or "adhoc"
    base = base[:20]
    slug = _readable_slug(key)
    out = f"{base}_{slug}_{digest}" if slug else f"{base}_{digest}"
    return out[:max_len]


def rss_feed_source_id(display_title: str, feed_url: str) -> str:
    """Id ổn định cho một feed RSS (dùng khi import OPML / tạo nguồn batch)."""
    prefix = (display_title or "").strip() or "rss"
    return _slug_id(prefix, feed_url)


def _sanitize_source_id(raw: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]", "_", raw.strip())
    return s[:64] or "adhoc"


def quick_url_source(
    url: str,
    *,
    extract: ExtractMode = "article",
    source_id: str | None = None,
    expand_links: bool = False,
    expand_max: int = 5,
) -> SourceConfig:
    u = url.strip().splitlines()[0].strip() if url.strip() else ""
    if not u:
        raise ValueError("URL không được để trống.")
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    sid = _sanitize_source_id(source_id) if source_id and source_id.strip() else _slug_id("url", u)
    return SourceConfig(
        id=sid,
        type="url",
        schedule_cron="0 * * * *",
        extract=extract,
        url=u,
        expand_links=expand_links,
        expand_max=expand_max,
    )


def quick_rss_source(
    feed_url: str,
    *,
    extract: ExtractMode = "article",
    rss_max_entries: int = 20,
    source_id: str | None = None,
) -> SourceConfig:
    u = feed_url.strip().splitlines()[0].strip() if feed_url.strip() else ""
    if not u:
        raise ValueError("Link RSS không được để trống.")
    if not re.match(r"^https?://", u, re.I):
        u = "https://" + u.lstrip("/")
    sid = _sanitize_source_id(source_id) if source_id and source_id.strip() else _slug_id("rss", u)
    n = max(1, min(int(rss_max_entries), 100))
    return SourceConfig(
        id=sid,
        type="rss",
        schedule_cron="0 * * * *",
        extract=extract,
        url=u,
        rss_max_entries=n,
    )


def quick_search_source(
    query: str,
    *,
    max_results: int = 5,
    source_id: str | None = None,
) -> SourceConfig:
    q = query.strip().splitlines()[0].strip() if query.strip() else ""
    if not q:
        raise ValueError("Từ khóa không được để trống.")
    sid = _sanitize_source_id(source_id) if source_id and source_id.strip() else _slug_id("search", q)
    n = max(1, min(int(max_results), 25))
    return SourceConfig(
        id=sid,
        type="search",
        schedule_cron="0 * * * *",
        extract="raw",
        query=q,
        max_results=n,
    )


def quick_file_source(
    file_path: str,
    *,
    extract: ExtractMode = "raw",
    source_id: str | None = None,
) -> SourceConfig:
    p = file_path.strip() if file_path else ""
    if not p:
        raise ValueError("Đường dẫn file không được để trống.")
    sid = _sanitize_source_id(source_id) if source_id and source_id.strip() else _slug_id("file", p)
    return SourceConfig(
        id=sid,
        type="file",
        schedule_cron="0 * * * *",
        extract=extract,
        file_path=p,
    )



def quick_youtube_source(
    url: str,
    *,
    max_videos: int = 10,
    source_id: str | None = None,
) -> SourceConfig:
    u = url.strip().splitlines()[0].strip() if url.strip() else ""
    if not u:
        raise ValueError("YouTube URL không được để trống.")
    sid = _sanitize_source_id(source_id) if source_id and source_id.strip() else _slug_id("youtube", u)
    n = max(1, min(int(max_videos), 2000))
    return SourceConfig(
        id=sid,
        type="youtube",
        schedule_cron="0 * * * *",
        extract="raw",
        url=u,
        max_videos=n,
    )
