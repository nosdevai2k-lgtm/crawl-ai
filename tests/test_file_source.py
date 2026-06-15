"""Tests for local file crawling (type='file')."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config_loader import SourceConfig, load_config, source_config_as_dict, source_config_from_dict
from src.extract import SourcePayload
from src.pipeline import collect_payload
from src.quick_sources import quick_file_source
from src.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="test",
        ollama_api_key="ollama",
        http_timeout=30,
        user_agent="test-agent",
        database_path=Path("data/test.db"),
        max_text_chars=40000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="test",
        mongodb_collection="docs",
    )


def test_quick_file_source_basic():
    src = quick_file_source("D:\\docs\\report.pdf")
    assert src.type == "file"
    assert src.file_path == "D:\\docs\\report.pdf"
    assert src.extract == "raw"


def test_quick_file_source_custom_id():
    src = quick_file_source("/tmp/data.csv", source_id="my_csv", extract="article")
    assert src.id == "my_csv"
    assert src.file_path == "/tmp/data.csv"
    assert src.extract == "article"


def test_quick_file_source_empty_raises():
    with pytest.raises(ValueError):
        quick_file_source("")


def test_source_config_roundtrip_file():
    src = SourceConfig(
        id="local_test",
        type="file",
        schedule_cron="0 * * * *",
        extract="raw",
        file_path="D:\\data\\test.txt",
    )
    d = source_config_as_dict(src)
    assert d["file_path"] == "D:\\data\\test.txt"
    assert d["type"] == "file"
    restored = source_config_from_dict(d)
    assert restored.type == "file"
    assert restored.file_path == "D:\\data\\test.txt"


def test_collect_payload_file_txt(settings):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("Hello world\nLine two")
        f.flush()
        path = f.name
    try:
        src = SourceConfig(
            id="test_txt", type="file", schedule_cron="0 * * * *",
            extract="raw", file_path=path,
        )
        payload = collect_payload(src, settings)
        assert payload is not None
        assert "Hello world" in payload.text
        assert payload.meta["format"] == "text"
        assert payload.meta["file_path"] == str(Path(path).resolve())
    finally:
        Path(path).unlink(missing_ok=True)


def test_collect_payload_file_csv(settings):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("name,age\nAlice,30\nBob,25")
        f.flush()
        path = f.name
    try:
        src = SourceConfig(
            id="test_csv", type="file", schedule_cron="0 * * * *",
            extract="raw", file_path=path,
        )
        payload = collect_payload(src, settings)
        assert payload is not None
        assert "Alice" in payload.text
        assert payload.meta["format"] == "csv"
    finally:
        Path(path).unlink(missing_ok=True)


def test_collect_payload_file_html(settings):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write("<html><body><p>Test paragraph</p></body></html>")
        f.flush()
        path = f.name
    try:
        src = SourceConfig(
            id="test_html", type="file", schedule_cron="0 * * * *",
            extract="raw", file_path=path,
        )
        payload = collect_payload(src, settings)
        assert payload is not None
        assert "Test paragraph" in payload.text
        assert payload.meta["format"] == "html"
    finally:
        Path(path).unlink(missing_ok=True)


def test_collect_payload_file_not_found(settings):
    src = SourceConfig(
        id="missing", type="file", schedule_cron="0 * * * *",
        extract="raw", file_path="/nonexistent/path.txt",
    )
    with pytest.raises(ValueError, match="File not found"):
        collect_payload(src, settings)


def test_collect_payload_file_no_path(settings):
    src = SourceConfig(
        id="no_path", type="file", schedule_cron="0 * * * *",
        extract="raw", file_path=None,
    )
    with pytest.raises(ValueError, match="file_path missing"):
        collect_payload(src, settings)


def test_load_config_file_type(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "sources:\n"
        "  - id: local_doc\n"
        "    type: file\n"
        "    file_path: D:\\docs\\report.pdf\n"
        "    extract: raw\n",
        encoding="utf-8",
    )
    sources = load_config(cfg)
    assert len(sources) == 1
    assert sources[0].type == "file"
    assert sources[0].file_path == "D:\\docs\\report.pdf"
