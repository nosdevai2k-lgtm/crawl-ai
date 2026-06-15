"""Unit tests for all crawl-ai features (URL, RSS, Search, File, YouTube)."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import SourceConfig, load_config, source_config_as_dict, source_config_from_dict
from src.extract import SourcePayload
from src.field_catalog import build_field_catalog
from src.pipeline import collect_payload, run_source, _sha256
from src.quick_sources import (
    quick_file_source,
    quick_rss_source,
    quick_search_source,
    quick_url_source,
    quick_youtube_source,
)
from src.settings import Settings
from src.storage import Storage
from src.youtube_fetch import VideoResult, videos_to_text, _safe_dirname


# --- Fixtures ---

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


# --- Config Loader Tests ---

class TestConfigLoader:
    def test_youtube_source_type_accepted(self):
        sc = SourceConfig(
            id="yt_test", type="youtube", schedule_cron="0 * * * *",
            extract="raw", url="https://youtube.com/@test", max_videos=5,
        )
        assert sc.type == "youtube"
        assert sc.max_videos == 5

    def test_source_config_roundtrip(self):
        sc = SourceConfig(
            id="yt1", type="youtube", schedule_cron="0 6 * * *",
            extract="raw", url="https://youtube.com/@ch", max_videos=100,
        )
        d = source_config_as_dict(sc)
        assert d["max_videos"] == 100
        assert d["type"] == "youtube"
        restored = source_config_from_dict(d)
        assert restored.type == "youtube"
        assert restored.max_videos == 100
        assert restored.url == "https://youtube.com/@ch"

    def test_load_config_with_youtube(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        cfg.write_text(
            "sources:\n"
            "  - id: yt_test\n"
            "    type: youtube\n"
            "    url: https://youtube.com/@test\n"
            "    max_videos: 50\n"
            "    schedule_cron: '0 * * * *'\n",
            encoding="utf-8",
        )
        sources = load_config(cfg)
        assert len(sources) == 1
        assert sources[0].type == "youtube"
        assert sources[0].max_videos == 50


# --- Quick Sources Tests ---

class TestQuickSources:
    def test_quick_url_source(self):
        s = quick_url_source("https://example.com")
        assert s.type == "url"
        assert s.url == "https://example.com"

    def test_quick_url_adds_https(self):
        s = quick_url_source("example.com")
        assert s.url == "https://example.com"

    def test_quick_rss_source(self):
        s = quick_rss_source("https://feed.example.com/rss.xml", rss_max_entries=10)
        assert s.type == "rss"
        assert s.rss_max_entries == 10

    def test_quick_search_source(self):
        s = quick_search_source("test query", max_results=3)
        assert s.type == "search"
        assert s.max_results == 3

    def test_quick_file_source(self):
        s = quick_file_source("D:\\test.pdf")
        assert s.type == "file"
        assert s.file_path == "D:\\test.pdf"

    def test_quick_youtube_source(self):
        s = quick_youtube_source("https://www.youtube.com/@test", max_videos=20)
        assert s.type == "youtube"
        assert s.url == "https://www.youtube.com/@test"
        assert s.max_videos == 20

    def test_quick_youtube_clamps_max(self):
        s = quick_youtube_source("https://youtube.com/watch?v=abc", max_videos=5000)
        assert s.max_videos == 2000

    def test_quick_youtube_empty_url_raises(self):
        with pytest.raises(ValueError):
            quick_youtube_source("")


# --- YouTube Fetch Tests ---

class TestYouTubeFetch:
    def test_safe_dirname(self):
        assert _safe_dirname("Normal Name") == "Normal Name"
        assert _safe_dirname('Bad: "chars" <here>') == "Bad_ _chars_ _here_"
        assert _safe_dirname("") == "unknown"

    def test_videos_to_text_empty(self):
        assert videos_to_text([]) == "(no videos downloaded)"

    def test_videos_to_text_formats(self):
        vids = [VideoResult(
            id="abc", title="Test Video", url="https://youtube.com/watch?v=abc",
            duration=125, upload_date="20260519", channel="TestCh",
            playlist="My Playlist", file_path="C:\\videos\\test.mp4",
            description="A test video description", view_count=1000, tags=["tag1", "tag2"],
        )]
        text = videos_to_text(vids)
        assert "Test Video" in text
        assert "abc" in text
        assert "TestCh" in text
        assert "My Playlist" in text
        assert "2m05s" in text
        assert "1,000" in text
        assert "tag1, tag2" in text
        assert "A test video description" in text


# --- Pipeline Tests ---

class TestPipeline:
    def test_youtube_skips_llm(self, settings, storage):
        """YouTube sources should auto-skip LLM even if skip_llm=False."""
        settings.skip_llm = False  # LLM enabled globally
        src = SourceConfig(
            id="yt_test", type="youtube", schedule_cron="0 * * * *",
            extract="raw", url="https://youtube.com/watch?v=test", max_videos=1,
        )
        fake_videos = [VideoResult(
            id="v1", title="Video 1", url="https://youtube.com/watch?v=v1",
            duration=60, upload_date="20260519", channel="Ch1",
            playlist="PL1", file_path="/tmp/v1.mp4",
            description="desc", view_count=100, tags=["t1"],
        )]
        fake_payload = SourcePayload(
            text=videos_to_text(fake_videos),
            meta={
                "youtube_url": src.url,
                "format": "youtube",
                "video_count": 1,
                "videos": [{"id": "v1", "title": "Video 1", "url": "https://youtube.com/watch?v=v1",
                            "playlist": "PL1", "file_path": "/tmp/v1.mp4", "channel": "Ch1",
                            "duration": 60, "upload_date": "20260519",
                            "description": "desc", "view_count": 100, "tags": ["t1"]}],
            },
        )
        # Should NOT call LLM
        res = run_source(src, storage, settings, None, cached_payload=fake_payload)
        assert res.changed is True
        assert res.skipped_reason is None

    def test_url_collect_payload(self, settings):
        """URL source should return a SourcePayload with text."""
        src = quick_url_source("https://example.com")
        with patch("src.pipeline.fetch_url") as mock_fetch:
            mock_fetch.return_value = MagicMock(
                not_modified=False, status_code=200,
                body=b"<html><body><p>Hello World</p></body></html>",
                content_type="text/html", url="https://example.com",
                etag=None, last_modified=None,
            )
            payload = collect_payload(src, settings)
        assert payload is not None
        assert len(payload.text) > 0

    def test_rss_collect_payload(self, settings):
        """RSS source should parse feed XML."""
        src = quick_rss_source("https://feed.example.com/rss")
        rss_xml = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><title>Test</title>
        <item><title>Item 1</title><description>Desc 1</description></item>
        </channel></rss>"""
        with patch("src.pipeline.fetch_url") as mock_fetch:
            mock_fetch.return_value = MagicMock(
                not_modified=False, status_code=200,
                body=rss_xml, content_type="application/xml",
                url="https://feed.example.com/rss",
                etag=None, last_modified=None,
            )
            payload = collect_payload(src, settings)
        assert payload is not None
        assert "Item 1" in payload.text

    def test_search_collect_payload(self, settings):
        """Search source should return results."""
        from src import pipeline
        src = quick_search_source("test query", max_results=2)
        with patch.object(pipeline, "search_to_text", return_value="Result 1: example.com\nResult 2: test.org"):
            payload = collect_payload(src, settings)
        assert payload is not None
        assert "Result 1" in payload.text

    def test_file_collect_payload(self, settings, tmp_path):
        """File source should read from disk."""
        f = tmp_path / "test.txt"
        f.write_text("Hello from file", encoding="utf-8")
        src = quick_file_source(str(f))
        payload = collect_payload(src, settings)
        assert payload is not None
        assert "Hello from file" in payload.text

    def test_youtube_collect_payload(self, settings):
        """YouTube source should call fetch_youtube and return video data."""
        src = quick_youtube_source("https://youtube.com/watch?v=abc", max_videos=1)
        fake_vids = [VideoResult(
            id="abc", title="My Video", url="https://youtube.com/watch?v=abc",
            duration=300, upload_date="20260519", channel="MyCh",
            playlist="", file_path="/tmp/abc.mp4",
            description="Video desc", view_count=5000, tags=["music"],
        )]
        with patch("src.youtube_fetch.fetch_youtube", return_value=fake_vids):
            with patch("src.youtube_fetch.videos_to_text", return_value=videos_to_text(fake_vids)):
                payload = collect_payload(src, settings)
        assert payload is not None
        assert payload.meta["format"] == "youtube"
        assert payload.meta["video_count"] == 1
        assert payload.meta["videos"][0]["title"] == "My Video"
        assert payload.meta["videos"][0]["description"] == "Video desc"

    def test_dedup_same_content(self, settings, storage):
        """Same content should not create duplicate records."""
        src = quick_url_source("https://example.com")
        payload = SourcePayload(text="same content", meta={"format": "test"})
        res1 = run_source(src, storage, settings, None, cached_payload=payload)
        assert res1.changed is True
        res2 = run_source(src, storage, settings, None, cached_payload=payload)
        assert res2.changed is False
        assert res2.skipped_reason == "unchanged_hash"


# --- Field Catalog Tests ---

class TestFieldCatalog:
    def test_basic_fields(self):
        payload = SourcePayload(
            text="Hello world",
            meta={"fetched_url": "https://example.com", "format": "html"},
        )
        cat = build_field_catalog(payload)
        assert "raw_text" in cat
        assert cat["raw_text"] == "Hello world"
        assert "meta::fetched_url" in cat

    def test_youtube_fields(self):
        payload = SourcePayload(
            text="video summary",
            meta={
                "format": "youtube",
                "videos": [
                    {
                        "title": "Video A",
                        "description": "Desc A",
                        "channel": "ChA",
                        "upload_date": "20260519",
                        "duration": "120",
                        "view_count": "999",
                        "tags": ["t1", "t2"],
                        "url": "https://youtube.com/watch?v=a",
                        "file_path": "/tmp/a.mp4",
                    }
                ],
            },
        )
        cat = build_field_catalog(payload)
        assert "video_1::title" in cat
        assert cat["video_1::title"] == "Video A"
        assert cat["video_1::description"] == "Desc A"
        assert "t1, t2" in cat["video_1::tags"]

    def test_csv_fields(self):
        csv_text = "name,age\nAlice,30\nBob,25"
        payload = SourcePayload(
            text=csv_text,
            meta={"format": "google_sheets_csv", "content_profile": {"kind": "csv_tabular"}},
        )
        cat = build_field_catalog(payload)
        assert "col::name" in cat
        assert "Alice" in cat["col::name"]


# --- Storage Tests ---

class TestStorage:
    def test_insert_and_retrieve(self, storage):
        doc_id = storage.insert_document(
            source_id="test_src",
            content_hash="hash123",
            raw_text="text content",
            structured_json='{"key": "val"}',
            meta={"format": "test"},
        )
        assert doc_id > 0
        row = storage.latest_for_source("test_src")
        assert row is not None
        assert row.raw_text == "text content"
        assert row.content_hash == "hash123"
        assert row.meta["format"] == "test"

    def test_list_recent(self, storage):
        storage.insert_document("s1", "h1", "t1", None, {})
        storage.insert_document("s2", "h2", "t2", None, {})
        rows = storage.list_recent(limit=10)
        assert len(rows) == 2

    def test_patch_meta(self, storage):
        doc_id = storage.insert_document("s1", "h1", "text", None, {"a": 1})
        ok = storage.patch_document_meta(doc_id, {"b": 2})
        assert ok is True
        row = storage.get_document_by_id(doc_id)
        assert row.meta["a"] == 1
        assert row.meta["b"] == 2
