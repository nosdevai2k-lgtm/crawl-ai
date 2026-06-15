"""Unit tests cho crawl-ai — tat ca chuc nang, khong can mang."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import SourceConfig, source_config_as_dict, source_config_from_dict, load_config
from src.extract import SourcePayload, extract_from_html
from src.export import export_to_csv, export_to_json
from src.fetch_cache import FetchCache
from src.field_catalog import build_field_catalog
from src.markdown_gen import html_to_markdown
from src.chunking import chunk_by_heading, chunk_by_tokens
from src.css_extract import css_extract
from src.pipeline import collect_payload, run_source
from src.quick_sources import (
    quick_url_source, quick_rss_source, quick_search_source,
    quick_file_source, quick_youtube_source,
)
from src.settings import Settings
from src.storage import Storage
from src.youtube_fetch import VideoResult, videos_to_text, _safe_dirname


@pytest.fixture
def settings(tmp_path):
    return Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="test",
        ollama_api_key="test",
        http_timeout=10,
        user_agent="test-agent",
        database_path=tmp_path / "test.db",
        max_text_chars=40000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.1,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="",
        mongodb_collection="",
    )


@pytest.fixture
def storage(tmp_path):
    return Storage(tmp_path / "test.db")


# === Config ===

class TestConfig:
    def test_all_source_types_valid(self):
        for t in ("url", "rss", "search", "browser", "file", "youtube", "deep_crawl"):
            sc = SourceConfig(id=f"test_{t}", type=t, schedule_cron="0 * * * *", extract="raw")
            assert sc.type == t

    def test_roundtrip(self):
        sc = SourceConfig(id="yt1", type="youtube", schedule_cron="0 * * * *",
                          extract="raw", url="https://youtube.com/@ch", max_videos=50)
        d = source_config_as_dict(sc)
        restored = source_config_from_dict(d)
        assert restored.type == "youtube"
        assert restored.max_videos == 50

    def test_roundtrip_extended_fields(self):
        sc = SourceConfig(
            id="br1",
            type="browser",
            schedule_cron="0 * * * *",
            extract="raw",
            url="https://example.com",
            expand_links=True,
            expand_max=12,
            js_code=["document.title"],
            max_depth=4,
            max_crawl_pages=30,
        )
        restored = source_config_from_dict(source_config_as_dict(sc))
        assert restored.expand_links is True
        assert restored.expand_max == 12
        assert restored.js_code == ["document.title"]
        assert restored.max_depth == 4
        assert restored.max_crawl_pages == 30

    def test_load_yaml(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text("sources:\n  - id: t1\n    type: url\n    url: https://x.com\n", encoding="utf-8")
        sources = load_config(cfg)
        assert len(sources) == 1
        assert sources[0].url == "https://x.com"

    def test_load_yaml_extended_fields(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            """
sources:
  - id: spa
    type: url
    url: https://spa.example.com
    expand_links: true
    expand_max: 8
    max_depth: 3
    max_crawl_pages: 25
    js_code:
      - "window.scrollTo(0, document.body.scrollHeight)"
""",
            encoding="utf-8",
        )
        sources = load_config(cfg)
        assert sources[0].expand_links is True
        assert sources[0].expand_max == 8
        assert sources[0].max_depth == 3
        assert sources[0].max_crawl_pages == 25
        assert sources[0].js_code == ["window.scrollTo(0, document.body.scrollHeight)"]


# === Quick Sources ===

class TestQuickSources:
    def test_url(self):
        s = quick_url_source("example.com")
        assert s.url == "https://example.com"

    def test_rss(self):
        s = quick_rss_source("https://feed.xml", rss_max_entries=10)
        assert s.rss_max_entries == 10

    def test_search(self):
        s = quick_search_source("query", max_results=3)
        assert s.max_results == 3

    def test_file(self):
        s = quick_file_source("C:\\test.pdf")
        assert s.file_path == "C:\\test.pdf"

    def test_youtube(self):
        s = quick_youtube_source("https://youtube.com/watch?v=abc", max_videos=5)
        assert s.max_videos == 5

    def test_youtube_max_clamp(self):
        s = quick_youtube_source("https://youtube.com/@x", max_videos=9999)
        assert s.max_videos == 2000

    def test_youtube_empty_raises(self):
        with pytest.raises(ValueError):
            quick_youtube_source("")


# === Pipeline ===

class TestPipeline:
    def test_url_fetch(self, settings):
        src = quick_url_source("https://example.com")
        with patch("src.pipeline.fetch_url") as mock:
            mock.return_value = MagicMock(
                not_modified=False, status_code=200,
                body=b"<html><body><p>Hello</p></body></html>",
                content_type="text/html", url="https://example.com",
                etag=None, last_modified=None,
            )
            p = collect_payload(src, settings)
        assert p is not None
        assert len(p.text) > 0

    def test_rss_fetch(self, settings):
        src = quick_rss_source("https://feed.xml")
        rss = b'<?xml version="1.0"?><rss><channel><item><title>News</title></item></channel></rss>'
        with patch("src.pipeline.fetch_url") as mock:
            mock.return_value = MagicMock(
                not_modified=False, status_code=200, body=rss,
                content_type="application/xml", url="https://feed.xml",
                etag=None, last_modified=None,
            )
            p = collect_payload(src, settings)
        assert "News" in p.text

    def test_file_fetch(self, settings, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("File content here", encoding="utf-8")
        src = quick_file_source(str(f))
        p = collect_payload(src, settings)
        assert "File content" in p.text

    def test_youtube_skips_llm(self, settings, storage):
        settings.skip_llm = False
        src = SourceConfig(id="yt", type="youtube", schedule_cron="0 * * * *",
                           extract="raw", url="https://youtube.com/watch?v=x", max_videos=1)
        pay = SourcePayload(text="video info", meta={"format": "youtube", "video_count": 1, "videos": []})
        res = run_source(src, storage, settings, None, cached_payload=pay)
        assert res.changed is True

    def test_dedup(self, settings, storage):
        src = quick_url_source("https://x.com")
        pay = SourcePayload(
            text="Nội dung bài viết đủ dài để vượt ngưỡng tối thiểu, dùng cho kiểm thử dedup.",
            meta={"format": "test"},
        )
        r1 = run_source(src, storage, settings, None, cached_payload=pay)
        r2 = run_source(src, storage, settings, None, cached_payload=pay)
        assert r1.changed is True
        assert r2.changed is False
        assert r2.skipped_reason == "unchanged_hash"

    def test_deep_crawl(self, settings):
        src = SourceConfig(id="dc", type="deep_crawl", schedule_cron="0 * * * *",
                           extract="article", url="https://example.com", max_depth=1, max_crawl_pages=1)
        with patch("src.async_fetch.fetch_many_sync") as mock:
            mock.return_value = [MagicMock(
                ok=True, status_code=200, content_type="text/html",
                body=b"<html><body><p>Deep page</p></body></html>",
                url="https://example.com", error=None,
            )]
            p = collect_payload(src, settings)
        assert p is not None
        assert p.meta["format"] == "deep_crawl"


# === Storage ===

class TestStorage:
    def test_insert_retrieve(self, storage):
        doc_id = storage.insert_document("s1", "h1", "text", None, {"a": 1})
        row = storage.latest_for_source("s1")
        assert row.raw_text == "text"
        assert row.meta["a"] == 1

    def test_list_recent(self, storage):
        storage.insert_document("s1", "h1", "t1", None, {})
        storage.insert_document("s2", "h2", "t2", None, {})
        assert len(storage.list_recent()) == 2

    def test_patch_meta(self, storage):
        doc_id = storage.insert_document("s1", "h1", "t", None, {"x": 1})
        storage.patch_document_meta(doc_id, {"y": 2})
        row = storage.get_document_by_id(doc_id)
        assert row.meta == {"x": 1, "y": 2}


# === Export ===

class TestExport:
    def test_csv(self, storage):
        storage.insert_document("s1", "h1", "hello world", None, {"fetched_url": "https://x.com", "format": "html"})
        rows = storage.list_recent()
        data = export_to_csv(rows)
        assert b"hello world" in data
        assert data.startswith(b"\xef\xbb\xbf")  # BOM

    def test_json(self, storage):
        storage.insert_document("s1", "h1", "content", None, {"format": "test"})
        rows = storage.list_recent()
        data = export_to_json(rows)
        parsed = json.loads(data)
        assert parsed[0]["text"] == "content"


# === Fetch Cache ===

class TestFetchCache:
    def test_put_get(self, tmp_path):
        cache = FetchCache(db_path=tmp_path / "cache.db", ttl_sec=60)
        cache.put("https://x.com", b"data", "text/html", 200)
        hit = cache.get("https://x.com")
        assert hit is not None
        assert hit.body == b"data"

    def test_expired(self, tmp_path):
        cache = FetchCache(db_path=tmp_path / "cache.db", ttl_sec=0)
        cache.put("https://x.com", b"old", "text/html", 200)
        assert cache.get("https://x.com") is None

    def test_invalidate(self, tmp_path):
        cache = FetchCache(db_path=tmp_path / "cache.db", ttl_sec=60)
        cache.put("https://x.com", b"data", "text/html", 200)
        cache.invalidate("https://x.com")
        assert cache.get("https://x.com") is None


# === Markdown ===

class TestMarkdown:
    def test_basic(self):
        r = html_to_markdown("<html><body><h1>Title</h1><p>Text here.</p></body></html>")
        assert "Title" in r.raw_markdown or "Text" in r.raw_markdown

    def test_links(self):
        r = html_to_markdown('<a href="https://x.com">Link</a>')
        assert "https://x.com" in r.links


# === CSS Extract ===

class TestCSSExtract:
    def test_basic(self):
        html = '<div class="item"><h2>A</h2></div><div class="item"><h2>B</h2></div>'
        schema = {"baseSelector": "div.item", "fields": [{"name": "title", "selector": "h2", "type": "text"}]}
        results = css_extract(html, schema)
        assert len(results) == 2
        assert results[0]["title"] == "A"


# === Chunking ===

class TestChunking:
    def test_by_heading(self):
        text = "# A\nContent A\n# B\nContent B"
        chunks = chunk_by_heading(text, max_chars=20)
        assert len(chunks) >= 2

    def test_by_tokens(self):
        text = "word " * 1000
        chunks = chunk_by_tokens(text, max_chars=500)
        assert len(chunks) > 1


# === YouTube ===

class TestYouTube:
    def test_safe_dirname(self):
        assert _safe_dirname("Normal") == "Normal"
        assert _safe_dirname('A:B"C') == "A_B_C"
        assert _safe_dirname("") == "unknown"

    def test_videos_to_text(self):
        v = VideoResult(id="x", title="Vid", url="http://y", duration=65,
                        upload_date="20260101", channel="Ch", playlist="PL",
                        file_path="/tmp/x.mp4", description="Desc", view_count=100, tags=["t1"])
        text = videos_to_text([v])
        assert "Vid" in text
        assert "1m05s" in text
        assert "PL" in text


# === Field Catalog ===

class TestFieldCatalog:
    def test_basic(self):
        p = SourcePayload(text="hello", meta={"fetched_url": "https://x.com", "format": "html"})
        cat = build_field_catalog(p)
        assert "raw_text" in cat
        assert cat["raw_text"] == "hello"

    def test_youtube_fields(self):
        p = SourcePayload(text="vid", meta={"format": "youtube", "videos": [
            {"title": "T", "description": "D", "channel": "C", "upload_date": "20260101",
             "duration": "60", "view_count": "99", "tags": ["a"], "url": "u", "file_path": "f"}
        ]})
        cat = build_field_catalog(p)
        assert "video_1::title" in cat
        assert cat["video_1::title"] == "T"
