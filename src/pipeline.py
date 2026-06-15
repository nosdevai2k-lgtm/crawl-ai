"""Orchestrate fetch → extract → hash → optional LLM → storage."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from openai import OpenAI

from .config_loader import SourceConfig
from .content_profile import profile_http_bytes, profile_search_payload
from .extract import (
    SourcePayload,
    extract_from_html,
    extract_from_docx_bytes,
    extract_from_pdf_bytes,
    extract_from_rss_feed,
    is_pdf_bytes,
    normalize_for_hash,
    search_to_text,
)
from .fetch import fetch_url

import logging
import httpx
from .google_sheets import looks_like_csv_text, spreadsheet_csv_export_url
from .retry_proxy import fetch_with_retry, load_proxies_from_env
from .llm import extract_persons, make_llm_client, structure_content

_log = logging.getLogger(__name__)
from .markdown_gen import html_to_markdown
from .structured_record import EMPTY_STRUCTURED_RECORD, normalize_structured
from .document_store import DocumentStore
from .settings import Settings


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clip(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n...[truncated]..."


_JUNK_PREFIXES = (
    "(no search results",
    "(search error:",
    "(empty feed)",
    "(fetch error:",
    "(feed fetch error:",
)

# Dấu hiệu trang tường chặn (cookie/bot-check/captcha) — chỉ coi là rác khi text NGẮN,
# để tránh chặn nhầm bài viết thật có nhắc tới các từ này.
_BLOCKWALL_MARKERS = (
    "enable javascript",
    "verify you are human",
    "are you a human",
    "security verification",
    "checking your browser",
    "captcha",
    "access denied",
    "cookie policy",
    "use of cookies",
    "accept cookies",
    "set preferences",
    "page not found",
    "404 not found",
    "unauthorized",
    "forbidden",
    "nội dung không tồn tại",
    "không tìm thấy đường dẫn",
    "trang không tồn tại",
)
_BLOCKWALL_MAX_CHARS = 1500


def _looks_like_blockwall(text: str) -> bool:
    t = text.strip()
    if len(t) > _BLOCKWALL_MAX_CHARS:
        return False
    low = t.lower()
    return any(m in low for m in _BLOCKWALL_MARKERS)


def _is_junk_payload(payload: SourcePayload) -> bool:
    """Lỗi fetch/search/feed, nội dung rỗng, HTTP lỗi, hoặc tường chặn → không đáng lưu / structure."""
    if payload.meta.get("format") == "error":
        return True
    status = payload.meta.get("status")
    if isinstance(status, int) and status >= 400:
        return True
    t = (payload.text or "").strip()
    if not t or t.startswith(_JUNK_PREFIXES):
        return True
    return _looks_like_blockwall(t)


def _collect_images(
    source: SourceConfig, settings: Settings, html: str, base_url: str
) -> list[dict[str, str]]:
    if not source.crawl_images:
        return []
    from .image_extract import (
        download_images,
        extract_image_names,
        extract_image_urls,
        extract_page_title,
    )

    urls = extract_image_urls(html, base_url)
    names = extract_image_names(html, base_url)
    place = extract_page_title(html)
    return download_images(
        urls,
        settings.image_download_dir / source.id,
        user_agent=settings.user_agent,
        timeout=settings.http_timeout,
        names=names,
        place=place,
    )


def _page_links(html: str, base_url: str, *, limit: int) -> list[str]:
    """Link http(s) cùng domain với trang gốc (tránh footer nhảy sang bài ngẫu nhiên)."""
    from urllib.parse import urljoin, urldefrag, urlparse
    from bs4 import BeautifulSoup

    base_host = urlparse(base_url).netloc.lower()
    seen: set[str] = set()
    out: list[str] = []
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue
        absu = urldefrag(urljoin(base_url, href))[0]
        if not absu.startswith(("http://", "https://")) or absu == base_url or absu in seen:
            continue
        if urlparse(absu).netloc.lower() != base_host:
            continue
        seen.add(absu)
        out.append(absu)
        if len(out) >= limit:
            break
    return out


def _expand_links(
    source: SourceConfig, settings: Settings, html: str, base_url: str
) -> str:
    """Theo link cùng domain → crawl thêm TEXT (không lấy ảnh, tránh ảnh lạc đề)."""
    from .async_fetch import fetch_many_sync

    links = _page_links(html, base_url, limit=max(1, min(source.expand_max, 25)))
    if not links:
        return ""
    results = fetch_many_sync(
        links, user_agent=settings.user_agent,
        timeout=min(settings.http_timeout, 30.0), max_concurrent=8,
    )
    texts: list[str] = []
    for fr in results:
        ct = (fr.content_type or "").lower()
        if not fr.ok or "html" not in ct:
            continue
        sub_html = fr.body.decode("utf-8", errors="replace")
        sub_text = extract_from_html(sub_html, mode=source.extract)
        if len(sub_text.strip()) >= 200:
            texts.append(f"\n\n--- [expanded] {fr.url} ---\n{sub_text}")
    return "".join(texts)


# Giới hạn an toàn cho BSON (Mongo) khi raw_text rất lớn (lỗi decode trước đây).
_MAX_STORED_RAW_CHARS = 1_500_000

# Cache domain cần render bằng browser (SPA) để lần sau vào thẳng, bỏ fetch tĩnh thừa.
_SPA_CACHE_FILE = Path("data/spa_domains.txt")


def _spa_domains() -> set[str]:
    try:
        return {
            l.strip().lower()
            for l in _SPA_CACHE_FILE.read_text(encoding="utf-8").splitlines()
            if l.strip()
        }
    except Exception:
        return set()


def _remember_spa_domain(url: str) -> None:
    host = urlparse(url).netloc.lower()
    if not host:
        return
    domains = _spa_domains()
    if host not in domains:
        try:
            _SPA_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with _SPA_CACHE_FILE.open("a", encoding="utf-8") as f:
                f.write(host + "\n")
        except Exception:
            pass


def _render_spa(source: "SourceConfig", settings: "Settings") -> SourcePayload:
    """Render bằng browser, trả payload raw-extract (dùng cho SPA)."""
    from .fetch_browser import fetch_browser

    br = fetch_browser(source.url, user_agent=settings.user_agent)
    btext = extract_from_html(br.html, mode="raw")
    bmd = html_to_markdown(br.html)
    return SourcePayload(
        text=btext,
        meta={
            "fetched_url": br.url,
            "status": br.status_code,
            "content_type": br.content_type,
            "format": "spa_browser_fallback",
            "markdown": bmd.fit_markdown[:500_000] if bmd.fit_markdown else "",
            "links_discovered": bmd.links[:100],
            "images": _collect_images(source, settings, br.html, br.url),
        },
    )


@dataclass
class PipelineResult:
    source_id: str
    changed: bool
    skipped_reason: Optional[str]
    content_hash: str
    document_id: Optional[int | str]


def collect_payload(
    source: SourceConfig,
    settings: Settings,
    *,
    previous_etag: Optional[str] = None,
    previous_last_modified: Optional[str] = None,
) -> SourcePayload | None:
    if source.type == "url":
        if not source.url:
            raise ValueError(f"url missing for source {source.id}")

        # Domain đã biết là SPA → render thẳng bằng browser, bỏ fetch tĩnh thừa.
        if urlparse(source.url).netloc.lower() in _spa_domains():
            try:
                return _render_spa(source, settings)
            except Exception:
                pass

        csv_export = spreadsheet_csv_export_url(source.url)
        if csv_export:
            try:
                fr_csv = fetch_url(
                    csv_export,
                    user_agent=settings.user_agent,
                    timeout=settings.http_timeout,
                    if_none_match=None,
                    if_modified_since=None,
                )
            except Exception:
                fr_csv = None
            else:
                if not fr_csv.not_modified and fr_csv.status_code == 200:
                    raw_csv = fr_csv.body.decode("utf-8", errors="replace")
                    if looks_like_csv_text(raw_csv):
                        prof = profile_http_bytes(
                            fr_csv.body, fr_csv.content_type, fr_csv.status_code
                        )
                        return SourcePayload(
                            text=raw_csv,
                            meta={
                                "fetched_url": fr_csv.url,
                                "google_sheets_browser_url": source.url,
                                "status": fr_csv.status_code,
                                "content_type": fr_csv.content_type,
                                "format": "google_sheets_csv",
                                "content_profile": prof,
                            },
                            etag=fr_csv.etag,
                            last_modified=fr_csv.last_modified,
                        )

        try:
            fr = fetch_url(
                source.url,
                user_agent=settings.user_agent,
                timeout=settings.http_timeout,
                if_none_match=previous_etag,
                if_modified_since=previous_last_modified,
            )
        except httpx.HTTPStatusError as exc:
            # On block-like status (403/404/429/451), try proxy then browser fallback
            if exc.response.status_code in (403, 404, 429, 451):
                proxies = load_proxies_from_env()
                if proxies:
                    try:
                        fr = fetch_with_retry(
                            source.url,
                            user_agent=settings.user_agent,
                            timeout=settings.http_timeout,
                            proxies=proxies,
                        )
                        html = fr.body.decode("utf-8", errors="replace")
                        text = extract_from_html(html, mode=source.extract)
                        md = html_to_markdown(html)
                        return SourcePayload(
                            text=text,
                            meta={
                                "fetched_url": fr.url,
                                "status": fr.status_code,
                                "content_type": fr.content_type,
                                "format": "proxy_fallback",
                                "markdown": md.fit_markdown[:500_000] if md.fit_markdown else "",
                                "links_discovered": md.links[:100],
                            },
                            etag=fr.etag,
                            last_modified=fr.last_modified,
                        )
                    except Exception:
                        pass
                try:
                    from .fetch_browser import fetch_browser
                    br = fetch_browser(source.url, user_agent=settings.user_agent)
                    text = extract_from_html(br.html, mode=source.extract)
                    md = html_to_markdown(br.html)
                    return SourcePayload(
                        text=text,
                        meta={
                            "fetched_url": br.url,
                            "status": br.status_code,
                            "content_type": br.content_type,
                            "format": "browser_fallback",
                            "markdown": md.fit_markdown[:500_000] if md.fit_markdown else "",
                            "links_discovered": md.links[:100],
                        },
                    )
                except Exception:
                    pass
            return SourcePayload(
                text=f"(fetch error: {type(exc).__name__}: {exc})",
                meta={"fetched_url": source.url, "error": str(exc), "format": "error"},
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return SourcePayload(
                text=f"(fetch error: {type(exc).__name__}: {exc})",
                meta={"fetched_url": source.url, "error": str(exc), "format": "error"},
            )
        if fr.not_modified:
            return None
        ct = (fr.content_type or "").lower()
        is_pdf = "application/pdf" in ct or is_pdf_bytes(fr.body)
        if is_pdf:
            text = extract_from_pdf_bytes(fr.body)
            prof = profile_http_bytes(fr.body, fr.content_type, fr.status_code)
            return SourcePayload(
                text=text,
                meta={
                    "fetched_url": fr.url,
                    "status": fr.status_code,
                    "content_type": fr.content_type,
                    "format": "pdf",
                    "content_profile": prof,
                },
                etag=fr.etag,
                last_modified=fr.last_modified,
            )
        prof = profile_http_bytes(fr.body, fr.content_type, fr.status_code)
        if prof.get("kind") == "json_like":
            text = fr.body.decode("utf-8", errors="replace")
            return SourcePayload(
                text=text,
                meta={
                    "fetched_url": fr.url,
                    "status": fr.status_code,
                    "content_type": fr.content_type,
                    "format": "json",
                    "content_profile": prof,
                },
                etag=fr.etag,
                last_modified=fr.last_modified,
            )
        html = fr.body.decode("utf-8", errors="replace")
        text = extract_from_html(html, mode=source.extract)
        # SPA fallback: trang JS-render trả ít text tĩnh hoặc là tường chặn → render bằng browser.
        if len(text.strip()) < 1500 or _looks_like_blockwall(text):
            try:
                payload = _render_spa(source, settings)
                if len(payload.text.strip()) > len(text.strip()):
                    _remember_spa_domain(source.url)
                    return payload
            except Exception:
                pass
        md = html_to_markdown(html)
        images = _collect_images(source, settings, html, fr.url)
        if source.expand_links:
            exp_text = _expand_links(source, settings, html, fr.url)
            text = text + exp_text
        return SourcePayload(
            text=text,
            meta={
                "fetched_url": fr.url,
                "status": fr.status_code,
                "content_type": fr.content_type,
                "content_profile": prof,
                "markdown": md.fit_markdown[:500_000] if md.fit_markdown else "",
                "links_discovered": md.links[:100],
                "images": images,
            },
            etag=fr.etag,
            last_modified=fr.last_modified,
        )

    if source.type == "rss":
        if not source.url:
            raise ValueError(f"feed url missing for source {source.id}")
        try:
            fr = fetch_url(
                source.url,
                user_agent=settings.user_agent,
                timeout=settings.http_timeout,
            )
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.ConnectError) as exc:
            return SourcePayload(
                text=f"(feed fetch error: {type(exc).__name__}: {exc})",
                meta={"feed_url": source.url, "error": str(exc), "format": "error"},
            )
        text = extract_from_rss_feed(fr.body, max_entries=source.rss_max_entries)
        prof = profile_http_bytes(fr.body, fr.content_type, fr.status_code)
        return SourcePayload(
            text=text,
            meta={
                "feed_url": fr.url,
                "format": "rss",
                "content_profile": prof,
            },
            etag=fr.etag,
            last_modified=fr.last_modified,
        )

    if source.type == "search":
        if not source.query:
            raise ValueError(f"query missing for source {source.id}")
        text = search_to_text(source.query, max_results=source.max_results)
        return SourcePayload(
            text=text,
            meta={
                "query": source.query,
                "max_results": source.max_results,
                "content_profile": profile_search_payload(
                    source.query, source.max_results
                ),
            },
        )

    if source.type == "browser":
        if not source.url:
            raise ValueError(f"url missing for browser source {source.id}")
        from .fetch_browser import fetch_browser, fetch_browser_paginated

        if source.next_button_selector and source.max_pages > 1:
            br = fetch_browser_paginated(
                source.url,
                wait_selector=source.wait_selector,
                next_button_selector=source.next_button_selector,
                max_pages=source.max_pages,
                user_agent=settings.user_agent,
            )
        else:
            br = fetch_browser(
                source.url,
                wait_selector=source.wait_selector,
                user_agent=settings.user_agent,
                js_code=source.js_code,
            )
        text = extract_from_html(br.html, mode=source.extract)
        return SourcePayload(
            text=text,
            meta={
                "fetched_url": br.url,
                "status": br.status_code,
                "content_type": br.content_type,
                "format": "browser_rendered",
                "images": _collect_images(source, settings, br.html, br.url),
            },
        )

    if source.type == "deep_crawl":
        if not source.url:
            raise ValueError(f"url missing for deep_crawl source {source.id}")
        from .deep_crawl import deep_crawl_bfs

        result = deep_crawl_bfs(
            source.url,
            max_depth=source.max_depth,
            max_pages=source.max_crawl_pages,
            user_agent=settings.user_agent,
            timeout=settings.http_timeout,
        )
        texts = [f"## {p.url}\n{p.text}" for p in result.pages]
        text = "\n\n---\n\n".join(texts)
        return SourcePayload(
            text=text,
            meta={
                "start_url": source.url,
                "format": "deep_crawl",
                "pages_crawled": len(result.pages),
                "urls_visited": len(result.urls_visited),
                "urls_failed": result.urls_failed[:20],
            },
        )

    if source.type == "youtube":
        if not source.url:
            raise ValueError(f"url missing for youtube source {source.id}")
        from .youtube_fetch import fetch_youtube, videos_to_text

        videos = fetch_youtube(source.url, max_videos=source.max_videos)
        text = videos_to_text(videos)
        return SourcePayload(
            text=text,
            meta={
                "youtube_url": source.url,
                "format": "youtube",
                "video_count": len(videos),
                "videos": [
                    {
                        "id": v.id,
                        "title": v.title,
                        "url": v.url,
                        "playlist": v.playlist,
                        "file_path": v.file_path,
                        "channel": v.channel,
                        "duration": v.duration,
                        "upload_date": v.upload_date,
                        "description": v.description[:2000],
                        "view_count": v.view_count,
                        "tags": v.tags[:30],
                    }
                    for v in videos
                ],
            },
        )

    if source.type == "file":
        from pathlib import Path as _Path

        fp = source.file_path
        if not fp:
            raise ValueError(f"file_path missing for source {source.id}")
        p = _Path(fp)
        if not p.is_file():
            raise ValueError(f"File not found: {fp}")
        raw_bytes = p.read_bytes()
        suffix = p.suffix.lower()
        if suffix == ".pdf" or is_pdf_bytes(raw_bytes):
            text = extract_from_pdf_bytes(raw_bytes)
            fmt = "pdf"
        elif suffix in (".docx", ".doc"):
            text = extract_from_docx_bytes(raw_bytes)
            fmt = "docx"
        elif suffix in (".html", ".htm"):
            html = raw_bytes.decode("utf-8", errors="replace")
            text = extract_from_html(html, mode=source.extract)
            fmt = "html"
        elif suffix == ".csv":
            text = raw_bytes.decode("utf-8", errors="replace")
            fmt = "csv"
        else:
            text = raw_bytes.decode("utf-8", errors="replace")
            fmt = "text"
        return SourcePayload(
            text=text,
            meta={
                "file_path": str(p.resolve()),
                "format": fmt,
                "file_size": len(raw_bytes),
            },
        )

    raise ValueError(f"Unsupported type: {source.type}")


def run_source(
    source: SourceConfig,
    storage: DocumentStore,
    settings: Settings,
    client: OpenAI | None = None,
    *,
    cached_payload: SourcePayload | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> PipelineResult:
    latest = storage.latest_for_source(source.id)
    prev_etag = latest.etag if latest else None
    prev_lm = latest.last_modified if latest else None

    if cached_payload is not None:
        payload = cached_payload
    else:
        payload = collect_payload(
            source,
            settings,
            previous_etag=prev_etag,
            previous_last_modified=prev_lm,
        )
    if payload is None:
        return PipelineResult(
            source_id=source.id,
            changed=False,
            skipped_reason="not_modified_304",
            content_hash=latest.content_hash if latest else "",
            document_id=None,
        )

    if _is_junk_payload(payload):
        return PipelineResult(
            source_id=source.id,
            changed=False,
            skipped_reason="empty_or_error",
            content_hash=latest.content_hash if latest else "",
            document_id=None,
        )

    normalized = normalize_for_hash(payload.text)
    content_hash = _sha256(normalized)

    if latest and latest.content_hash == content_hash:
        return PipelineResult(
            source_id=source.id,
            changed=False,
            skipped_reason="unchanged_hash",
            content_hash=content_hash,
            document_id=None,
        )

    if settings.skip_llm or source.type == "youtube":
        structured = {
            **EMPTY_STRUCTURED_RECORD,
            "note": "SKIP_LLM: no model inference",
        }
        structured_json = json.dumps(structured, ensure_ascii=False)
    else:
        from .chunking import chunk_by_heading

        llm = client or make_llm_client(settings)
        llm_budget = min(max(settings.max_text_chars * 2, 96_000), 160_000)
        clipped = _clip(payload.text, llm_budget)
        fetch_context: dict[str, Any] = {
            "source_id": source.id,
            "source_config_type": source.type,
            "config_url": source.url,
            "config_query": source.query,
        }
        for k, v in payload.meta.items():
            if v is not None and k not in fetch_context and k != "markdown":
                fetch_context[k] = v

        if source.llm_mode == "persons":
            # For persons mode on large docs, chunk and merge results
            if len(clipped) > settings.max_text_chars:
                chunks = chunk_by_heading(clipped, max_chars=settings.max_text_chars)
                all_persons: list[Any] = []
                for chunk in chunks:
                    r = extract_persons(
                        llm, settings.ollama_model, chunk.text,
                        max_retries=settings.llm_max_retries,
                        backoff_sec=settings.llm_retry_backoff_sec,
                        fetch_context=fetch_context,
                    )
                    all_persons.extend(r.get("persons", []))
                structured = {"persons": all_persons}
            else:
                structured = extract_persons(
                    llm, settings.ollama_model, clipped,
                    max_retries=settings.llm_max_retries,
                    backoff_sec=settings.llm_retry_backoff_sec,
                    fetch_context=fetch_context,
                )
        else:
            structured = structure_content(
                llm, settings.ollama_model, clipped,
                max_retries=settings.llm_max_retries,
                backoff_sec=settings.llm_retry_backoff_sec,
                fetch_context=fetch_context,
            )
            structured = normalize_structured(structured)
            if not (structured.get("title") or "").strip() and not (structured.get("summary") or "").strip():
                return PipelineResult(
                    source_id=source.id,
                    changed=False,
                    skipped_reason="empty_or_error",
                    content_hash=content_hash,
                    document_id=None,
                )
        structured_json = json.dumps(structured, ensure_ascii=False)
    meta: dict[str, Any] = dict(payload.meta)
    meta["source_type"] = source.type
    if extra_meta:
        patch = dict(extra_meta)
        efb = patch.get("extract_full_by_field")
        if isinstance(efb, dict):
            from .field_catalog import cap_field_blob_map

            capped, trunc = cap_field_blob_map(
                {str(k): str(v) for k, v in efb.items()},
            )
            patch["extract_full_by_field"] = capped
            if trunc:
                patch["extract_full_truncated"] = True
        meta.update(patch)

    store_limit = min(_MAX_STORED_RAW_CHARS, max(settings.max_text_chars * 8, 256_000))
    raw_stored = _clip(payload.text, store_limit)
    if len(raw_stored) < len(payload.text):
        _log.warning(
            "source %s: raw_text truncated from %d to %d chars",
            source.id, len(payload.text), len(raw_stored),
        )

    doc_id = storage.insert_document(
        source_id=source.id,
        content_hash=content_hash,
        raw_text=raw_stored,
        structured_json=structured_json,
        meta=meta,
        etag=payload.etag,
        last_modified=payload.last_modified,
    )
    try:
        from .kg.indexer import index_document_kg

        structured_obj = json.loads(structured_json) if structured_json else {}
        index_document_kg(settings.database_path, doc_id, source.id, structured_obj, meta)
    except Exception as exc:  # noqa: BLE001
        _log.warning("KG index failed for doc %s: %s", doc_id, exc)

    return PipelineResult(
        source_id=source.id,
        changed=True,
        skipped_reason=None,
        content_hash=content_hash,
        document_id=doc_id,
    )
