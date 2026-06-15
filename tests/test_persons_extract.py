"""Tests for personal info extraction mode (llm_mode='persons')."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.config_loader import SourceConfig, source_config_as_dict, source_config_from_dict
from src.llm import extract_persons
from src.pipeline import run_source
from src.settings import Settings
from src.storage import Storage


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


def test_source_config_llm_mode_default():
    src = SourceConfig(id="x", type="url", schedule_cron="0 * * * *", extract="raw", url="https://example.com")
    assert src.llm_mode == "general"


def test_source_config_llm_mode_persons():
    src = SourceConfig(id="x", type="url", schedule_cron="0 * * * *", extract="raw", url="https://example.com", llm_mode="persons")
    assert src.llm_mode == "persons"


def test_source_config_roundtrip_llm_mode():
    src = SourceConfig(id="x", type="browser", schedule_cron="0 * * * *", extract="raw", url="https://example.com", llm_mode="persons")
    d = source_config_as_dict(src)
    assert d["llm_mode"] == "persons"
    restored = source_config_from_dict(d)
    assert restored.llm_mode == "persons"


def test_extract_persons_normalizes_single_person():
    """If model returns a flat person dict instead of {persons: [...]}, normalize it."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "full_name": "Nguyen Van A",
        "date_of_birth": "1990-01-15",
        "address": "Ha Noi",
    })
    mock_client.chat.completions.create.return_value = mock_resp

    result = extract_persons(mock_client, "test-model", "some text", max_retries=1, backoff_sec=0)
    assert "persons" in result
    assert len(result["persons"]) == 1
    assert result["persons"][0]["full_name"] == "Nguyen Van A"


def test_extract_persons_returns_list():
    """Normal case: model returns {persons: [...]}."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps({
        "persons": [
            {"full_name": "Alice", "date_of_birth": "1985-03-20", "phone": "0901234567"},
            {"full_name": "Bob", "date_of_birth": "", "email": "bob@example.com"},
        ]
    })
    mock_client.chat.completions.create.return_value = mock_resp

    result = extract_persons(mock_client, "test-model", "some text", max_retries=1, backoff_sec=0)
    assert len(result["persons"]) == 2
    assert result["persons"][0]["full_name"] == "Alice"
    assert result["persons"][1]["email"] == "bob@example.com"


def test_run_source_persons_mode_skip_llm(settings, tmp_path):
    """With skip_llm, persons mode still stores a document (no LLM call)."""
    db = tmp_path / "test.db"
    storage = Storage(db)
    src = SourceConfig(
        id="test_persons", type="file", schedule_cron="0 * * * *",
        extract="raw", llm_mode="persons",
    )
    # Create a temp file
    f = tmp_path / "people.txt"
    f.write_text("Nguyen Van A, born 1990-01-15, Ha Noi\nTran Thi B, born 1985-03-20, HCM", encoding="utf-8")
    src.file_path = str(f)

    res = run_source(src, storage, settings, None)
    assert res.changed is True
    assert res.document_id is not None
