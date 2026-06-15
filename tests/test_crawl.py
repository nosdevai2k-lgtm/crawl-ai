"""Unit tests cho crawl-ai (không cần mạng / Ollama)."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from pypdf import PdfWriter

from src.config_loader import SourceConfig, load_config
from src.extract import (
    SourcePayload,
    extract_from_html,
    extract_from_rss_feed,
    extract_from_pdf_bytes,
    is_pdf_bytes,
    normalize_for_hash,
)
from src.document_store import get_document_store
from src.fetch import build_request_headers
from src.pipeline import PipelineResult, _clip, collect_payload, run_source
from src.quick_sources import quick_rss_source, quick_search_source, quick_url_source
from src.settings import Settings
from src.storage import Storage


def test_get_document_store_sqlite_without_mongo(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MONGODB_URI", "")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "only.sqlite"))
    from src.settings import load_settings

    s = load_settings()
    st = get_document_store(s)
    assert type(st).__name__ == "Storage"


def test_is_pdf_bytes_magic() -> None:
    assert not is_pdf_bytes(b"")
    assert not is_pdf_bytes(b"<html>")
    w = PdfWriter()
    w.add_blank_page(width=50, height=50)
    buf = BytesIO()
    w.write(buf)
    data = buf.getvalue()
    assert data.startswith(b"%PDF")
    assert is_pdf_bytes(data)


def test_extract_from_pdf_blank_page_has_placeholder() -> None:
    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    buf = BytesIO()
    w.write(buf)
    out = extract_from_pdf_bytes(buf.getvalue())
    assert "PDF" in out


def test_collect_payload_url_pdf_not_html_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.fetch import FetchResult

    w = PdfWriter()
    w.add_blank_page(width=72, height=72)
    bio = BytesIO()
    w.write(bio)
    pdf_bytes = bio.getvalue()

    def _fake_fetch(*_a: object, **_k: object) -> FetchResult:
        return FetchResult(
            url="https://cdn.example/doc.pdf",
            status_code=200,
            body=pdf_bytes,
            content_type="application/pdf",
            etag=None,
            last_modified=None,
        )

    monkeypatch.setattr("src.pipeline.fetch_url", _fake_fetch)
    src = SourceConfig(
        id="pdfsrc",
        type="url",
        schedule_cron="* * * * *",
        extract="raw",
        url="https://cdn.example/doc.pdf",
    )
    settings = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="ollama",
        http_timeout=5.0,
        user_agent="test-agent",
        database_path=Path("x.db"),
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    pl = collect_payload(src, settings)
    assert pl is not None
    assert pl.meta.get("format") == "pdf"
    assert pl.meta.get("content_type") == "application/pdf"
    assert "PDF" in pl.text
    assert pl.meta.get("content_profile", {}).get("kind") == "pdf"


def test_build_request_headers_includes_accept_and_ua() -> None:
    h = build_request_headers("MyBot/1.0 (https://x.test; a@b.c) httpx")
    assert h["User-Agent"].startswith("MyBot")
    assert "text/html" in h["Accept"]
    assert "application/pdf" in h["Accept"]
    assert "Accept-Language" in h


def test_quick_url_adds_https_and_stable_id() -> None:
    s1 = quick_url_source("example.com/foo", extract="raw", source_id=None)
    assert s1.url == "https://example.com/foo"
    assert s1.type == "url"
    s2 = quick_url_source("example.com/foo", extract="raw", source_id=None)
    assert s1.id == s2.id


def test_quick_url_custom_id() -> None:
    s = quick_url_source("https://a.com", extract="article", source_id="my_blog")
    assert s.id == "my_blog"


def test_quick_rss_clamps_entries() -> None:
    s = quick_rss_source("https://x.com/feed.xml", rss_max_entries=500, source_id=None)
    assert s.rss_max_entries == 100


def test_quick_search_empty_raises() -> None:
    with pytest.raises(ValueError, match="Từ khóa"):
        quick_search_source("   ", max_results=5)


def test_normalize_for_hash_collapses_whitespace_and_case() -> None:
    assert normalize_for_hash("  Hello\n\nWorld  ") == "hello world"


def test_extract_from_html_raw_strips_tags() -> None:
    html = "<html><body><p>Hi</p></body></html>"
    text = extract_from_html(html, mode="raw")
    assert "Hi" in text


def test_extract_from_rss_feed_minimal() -> None:
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel>
      <item><title>A</title><link>http://a</link><description>DA</description></item>
      <item><title>B</title><link>http://b</link><description>DB</description></item>
    </channel></rss>"""
    out = extract_from_rss_feed(xml, max_entries=2)
    assert "A" in out and "http://a" in out and "B" in out


def test_load_config_valid_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        """
sources:
  - id: s1
    type: url
    url: https://example.com
    schedule_cron: "0 * * * *"
    extract: article
""",
        encoding="utf-8",
    )
    sources = load_config(cfg)
    assert len(sources) == 1
    assert sources[0].id == "s1"
    assert sources[0].type == "url"


def test_load_config_rejects_bad_extract_mode(tmp_path: Path) -> None:
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(
        """
sources:
  - id: x
    type: url
    url: https://example.com
    extract: invalid_mode
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Invalid extract"):
        load_config(cfg)


def test_storage_insert_latest_and_list_recent(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    st = Storage(db)
    st.insert_document(
        source_id="a",
        content_hash="h1",
        raw_text="t1",
        structured_json='{"k":1}',
        meta={"m": 1},
    )
    st.insert_document(
        source_id="a",
        content_hash="h2",
        raw_text="t2",
        structured_json=None,
        meta={},
    )
    latest = st.latest_for_source("a")
    assert latest is not None
    assert latest.content_hash == "h2"
    recent = st.list_recent(limit=10)
    assert len(recent) == 2
    assert recent[0].id >= recent[1].id


def test_clip_truncates_long_text() -> None:
    long = "x" * 100
    clipped = _clip(long, max_chars=40)
    assert len(clipped) <= 40
    assert "truncated" in clipped


def test_run_source_skip_llm_inserts(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    storage = Storage(db)
    settings = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="ollama",
        http_timeout=5.0,
        user_agent="test-agent",
        database_path=db,
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    source = SourceConfig(
        id="src1",
        type="url",
        schedule_cron="* * * * *",
        extract="raw",
        url="https://example.com",
    )
    fake_payload = SourcePayload(
        text="Unique body. " * 8 + "Nội dung bài viết thử nghiệm đủ dài để không bị coi là rác.",
        meta={"ok": True},
        etag='W/"t1"',
        last_modified=None,
    )
    with patch("src.pipeline.collect_payload", return_value=fake_payload):
        res = run_source(source, storage, settings, None)
    assert res.changed is True
    assert res.document_id is not None
    row = storage.latest_for_source("src1")
    assert row is not None
    obj = json.loads(row.structured_json or "{}")
    assert obj.get("note") == "SKIP_LLM: no model inference"
    assert obj.get("topics") == []
    assert obj.get("primary_topic") == ""
    assert obj.get("publication_or_site_name") == ""
    assert obj.get("primary_date") == ""
    assert obj.get("key_facts") == []


def test_run_source_skips_junk_payload(tmp_path: Path) -> None:
    db = tmp_path / "junk.db"
    storage = Storage(db)
    settings = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="ollama",
        http_timeout=5.0,
        user_agent="test-agent",
        database_path=db,
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    source = SourceConfig(
        id="junk1", type="search", schedule_cron="* * * * *",
        extract="raw", query="x",
    )
    for payload in (
        SourcePayload(text="(no search results — empty)", meta={}),
        SourcePayload(text="(feed fetch error: 404)", meta={"format": "error"}),
        SourcePayload(text="   ", meta={}),
    ):
        with patch("src.pipeline.collect_payload", return_value=payload):
            res = run_source(source, storage, settings, None)
        assert res.changed is False
        assert res.skipped_reason == "empty_or_error"
        assert res.document_id is None
    assert storage.latest_for_source("junk1") is None


def test_is_junk_payload_blockwall() -> None:
    from src.pipeline import _is_junk_payload

    # Tường chặn + text ngắn → junk
    assert _is_junk_payload(SourcePayload(text="Cookies Policy. Accept cookies to continue.", meta={}))
    assert _is_junk_payload(SourcePayload(text="Please enable JavaScript and verify you are human.", meta={}))
    # soft-404: HTTP 200 nhưng nội dung là trang không tồn tại
    assert _is_junk_payload(SourcePayload(text="Page not found. Nội dung không tồn tại.!", meta={"status": 200}))
    # Bài viết dài có nhắc 'captcha' → KHÔNG phải junk
    long_article = "Bài viết về bảo mật. " * 200 + " captcha "
    assert not _is_junk_payload(SourcePayload(text=long_article, meta={}))
    # HTTP 404/403 (browser fallback vẫn render menu) → junk
    assert _is_junk_payload(SourcePayload(text=long_article, meta={"status": 404}))
    assert not _is_junk_payload(SourcePayload(text=long_article, meta={"status": 200}))


def test_is_junk_payload_too_short_and_boilerplate() -> None:
    from src.pipeline import _is_junk_payload

    # footer-only extraction từ trang JS-nặng (gov portal) → junk
    assert _is_junk_payload(SourcePayload(text="↑\nĐã kết nối EMC\nTrực thuộc BTTTT", meta={"format": "html"}))
    # nội dung quá ngắn cho một bài viết → junk
    assert _is_junk_payload(SourcePayload(text="Vài chữ ngắn ngủi.", meta={"format": "html"}))
    # nhưng search/rss gộp nhiều kết quả ngắn thì KHÔNG bị phạt độ dài
    assert not _is_junk_payload(SourcePayload(text="Tiêu đề ngắn", meta={"query": "x"}))
    assert not _is_junk_payload(SourcePayload(text="RSS ngắn", meta={"format": "rss"}))


def test_run_source_unchanged_hash_skips_second_insert(tmp_path: Path) -> None:
    db = tmp_path / "q.db"
    storage = Storage(db)
    settings = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="ollama",
        http_timeout=5.0,
        user_agent="test-agent",
        database_path=db,
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    source = SourceConfig(
        id="src2",
        type="url",
        schedule_cron="* * * * *",
        extract="raw",
        url="https://example.com",
    )
    payload = SourcePayload(
        text="Nội dung giống nhau, đủ dài để vượt ngưỡng tối thiểu và không bị coi là rác.",
        meta={}, etag=None, last_modified=None,
    )
    with patch("src.pipeline.collect_payload", return_value=payload):
        r1 = run_source(source, storage, settings, None)
    assert r1.changed is True
    with patch("src.pipeline.collect_payload", return_value=payload):
        r2 = run_source(source, storage, settings, None)
    assert isinstance(r2, PipelineResult)
    assert r2.changed is False
    assert r2.skipped_reason == "unchanged_hash"


def test_run_source_not_modified_304(tmp_path: Path) -> None:
    db = tmp_path / "r.db"
    storage = Storage(db)
    storage.insert_document(
        source_id="src3",
        content_hash="oldhash",
        raw_text="x",
        structured_json="{}",
        meta={},
        etag="abc",
    )
    settings = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen2.5:7b",
        ollama_api_key="ollama",
        http_timeout=5.0,
        user_agent="test-agent",
        database_path=db,
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    source = SourceConfig(
        id="src3",
        type="url",
        schedule_cron="* * * * *",
        extract="raw",
        url="https://example.com",
    )
    with patch("src.pipeline.collect_payload", return_value=None):
        res = run_source(source, storage, settings, None)
    assert res.changed is False
    assert res.skipped_reason == "not_modified_304"
    assert res.content_hash == "oldhash"
