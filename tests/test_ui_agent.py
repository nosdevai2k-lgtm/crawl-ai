"""ui_agent: khi Skip LLM thì không gọi HTTP."""

from __future__ import annotations

from pathlib import Path

from src.settings import Settings
from src.ui_agent import chat_ui_assistant


def test_chat_ui_assistant_skip_llm_returns_notice() -> None:
    s = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="dummy",
        ollama_api_key="ollama",
        http_timeout=1.0,
        user_agent="test",
        database_path=Path("."),
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.1,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    out = chat_ui_assistant([{"role": "user", "content": "Xin chào"}], settings=s)
    assert "Skip LLM" in out
