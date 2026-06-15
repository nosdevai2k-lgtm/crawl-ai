"""Google Sheets URL → CSV export."""

from __future__ import annotations

import pytest

from src.google_sheets import looks_like_csv_text, spreadsheet_csv_export_url


def test_spreadsheet_csv_export_url_with_hash_gid() -> None:
    u = "https://docs.google.com/spreadsheets/d/ABC123xyz/edit?gid=0#gid=0"
    out = spreadsheet_csv_export_url(u)
    assert out is not None
    assert "ABC123xyz" in out
    assert "format=csv" in out
    assert "gid=0" in out


def test_spreadsheet_csv_export_url_query_gid() -> None:
    u = "https://docs.google.com/spreadsheets/d/ZZZ/edit?gid=7&usp=sharing"
    out = spreadsheet_csv_export_url(u)
    assert out is not None
    assert "gid=7" in out


def test_spreadsheet_csv_export_non_sheet() -> None:
    assert spreadsheet_csv_export_url("https://example.com") is None


def test_looks_like_csv_text() -> None:
    assert looks_like_csv_text("a,b,c\n1,2,3\n")
    assert not looks_like_csv_text("<html><title>x</title>")
    assert not looks_like_csv_text("")


def test_collect_payload_prefers_google_sheet_csv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.fetch import FetchResult
    from src.pipeline import collect_payload

    calls: list[str] = []

    def fake_fetch(
        url: str,
        *,
        user_agent: str,
        timeout: float,
        if_none_match=None,
        if_modified_since=None,
        method: str = "GET",
        headers=None,
    ) -> FetchResult:
        calls.append(url)
        if "export?format=csv" in url:
            return FetchResult(
                url=url,
                status_code=200,
                body="ColA,ColB\n1,2\n".encode("utf-8"),
                content_type="text/csv; charset=utf-8",
                etag='"e1"',
                last_modified=None,
            )
        return FetchResult(
            url=url,
            status_code=200,
            body=b"<html><title>only</title></html>",
            content_type="text/html",
            etag=None,
            last_modified=None,
        )

    monkeypatch.setattr("src.pipeline.fetch_url", fake_fetch)
    from src.config_loader import SourceConfig
    from pathlib import Path
    from src.settings import Settings

    src = SourceConfig(
        id="gs",
        type="url",
        schedule_cron="* * * * *",
        extract="raw",
        url="https://docs.google.com/spreadsheets/d/ABC/edit#gid=0",
    )
    st = Settings(
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="m",
        ollama_api_key="k",
        http_timeout=5.0,
        user_agent="ua",
        database_path=Path("x.db"),
        max_text_chars=1000,
        llm_max_retries=1,
        llm_retry_backoff_sec=0.01,
        skip_llm=True,
        mongodb_uri=None,
        mongodb_database="crawl_ai",
        mongodb_collection="documents",
    )
    pl = collect_payload(src, st)
    assert pl is not None
    assert "ColA" in pl.text
    assert pl.meta.get("format") == "google_sheets_csv"
    assert len(calls) == 1
    assert "export?format=csv" in calls[0]
