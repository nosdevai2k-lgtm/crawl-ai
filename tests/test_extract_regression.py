"""Hồi quy trích xuất: article vs raw, RSS HTML → text, Atom content ưu tiên."""

from __future__ import annotations

import pytest

from src.extract import extract_from_html, extract_from_rss_feed


def test_article_keeps_main_and_raw_is_larger_or_equal() -> None:
    html = """<!DOCTYPE html>
<html><body>
<nav><p>NAV_FILLER_TEXT_NAV_FILLER_TEXT_NAV_FILLER_TEXT</p></nav>
<article><h1>Title</h1><p>UNIQUE_CORE_SENTENCE_FOR_TEST</p></article>
</body></html>"""
    raw = extract_from_html(html, mode="raw")
    art = extract_from_html(html, mode="article")
    assert "UNIQUE_CORE_SENTENCE_FOR_TEST" in art
    assert "UNIQUE_CORE_SENTENCE_FOR_TEST" in raw
    assert len(raw) >= len(art)


def test_rss_description_html_becomes_plain_text() -> None:
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>c</title>
<item><title>T</title><link>https://example.com/a</link>
<description><![CDATA[<p>Hello <b>world</b> and <a href="#">link</a></p>]]></description>
</item></channel></rss>"""
    out = extract_from_rss_feed(xml, max_entries=5)
    assert "Hello" in out and "world" in out
    assert "<p>" not in out
    assert "https://example.com/a" in out


def test_rss_prefers_atom_content_when_longer() -> None:
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>t</title>
  <entry>
    <title>E</title>
    <link href="https://ex.org/e"/>
    <summary type="html"><![CDATA[<p>short</p>]]></summary>
    <content type="html"><![CDATA[<div><p>ATOM_LONG_BODY_PARAGRAPH_UNIQUE_999</p></div>]]></content>
  </entry>
</feed>"""
    out = extract_from_rss_feed(xml, max_entries=3)
    assert "ATOM_LONG_BODY_PARAGRAPH_UNIQUE_999" in out


def test_search_to_text_empty_lists_returns_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    class _M:
        def __enter__(self) -> _M:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def text(self, *_a: object, **_k: object) -> list[dict[str, str]]:
            return []

    monkeypatch.setattr("src.extract.DDGS", _M)
    from src.extract import search_to_text

    out = search_to_text("query", max_results=3)
    assert "DuckDuckGo" in out or "RSS" in out
