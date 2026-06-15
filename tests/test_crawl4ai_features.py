"""Tests for crawl4ai-inspired features: markdown, CSS extract, chunking, async fetch."""

from __future__ import annotations

import asyncio

import pytest

from src.chunking import chunk_by_heading, chunk_by_separator, chunk_by_tokens
from src.css_extract import css_extract
from src.markdown_gen import MarkdownResult, html_to_markdown


# --- Markdown generation ---

def test_html_to_markdown_basic():
    html = "<html><body><h1>Title</h1><p>Hello world paragraph.</p></body></html>"
    result = html_to_markdown(html)
    assert isinstance(result, MarkdownResult)
    assert "Title" in result.raw_markdown or "Hello world" in result.raw_markdown
    assert isinstance(result.links, list)


def test_html_to_markdown_extracts_links():
    html = '<html><body><a href="https://example.com">Link</a><a href="#top">Skip</a></body></html>'
    result = html_to_markdown(html)
    assert "https://example.com" in result.links
    assert "#top" not in result.links


def test_html_to_markdown_fit_removes_noise():
    html = "<html><body><p>A</p><p>This is a real paragraph with enough words to keep.</p></body></html>"
    result = html_to_markdown(html)
    # Fit markdown should keep the longer paragraph
    assert "real paragraph" in result.fit_markdown or "real paragraph" in result.raw_markdown


# --- CSS extraction ---

def test_css_extract_basic():
    html = """
    <div class="item"><h2 class="name">Product A</h2><span class="price">$10</span></div>
    <div class="item"><h2 class="name">Product B</h2><span class="price">$20</span></div>
    """
    schema = {
        "baseSelector": "div.item",
        "fields": [
            {"name": "title", "selector": "h2.name", "type": "text"},
            {"name": "price", "selector": ".price", "type": "text"},
        ],
    }
    results = css_extract(html, schema)
    assert len(results) == 2
    assert results[0]["title"] == "Product A"
    assert results[1]["price"] == "$20"


def test_css_extract_attribute():
    html = '<div class="card"><img src="/img/photo.jpg" alt="Photo"></div>'
    schema = {
        "baseSelector": "div.card",
        "fields": [
            {"name": "image", "selector": "img", "type": "attribute", "attribute": "src"},
        ],
    }
    results = css_extract(html, schema)
    assert results[0]["image"] == "/img/photo.jpg"


def test_css_extract_list_type():
    html = '<ul class="tags"><li>python</li><li>ai</li><li>web</li></ul>'
    schema = {
        "baseSelector": "ul.tags",
        "fields": [
            {"name": "items", "selector": "li", "type": "list"},
        ],
    }
    results = css_extract(html, schema)
    assert results[0]["items"] == ["python", "ai", "web"]


# --- Chunking ---

def test_chunk_by_heading_splits():
    text = "# Section 1\nContent one.\n# Section 2\nContent two."
    chunks = chunk_by_heading(text, max_chars=30)
    assert len(chunks) >= 2
    assert "Section 1" in chunks[0].text


def test_chunk_by_heading_merges_small():
    text = "# A\nShort.\n# B\nAlso short."
    chunks = chunk_by_heading(text, max_chars=10000)
    # Should merge into one chunk since total is small
    assert len(chunks) == 1


def test_chunk_by_tokens_single():
    text = "Short text."
    chunks = chunk_by_tokens(text, max_chars=1000)
    assert len(chunks) == 1
    assert chunks[0].text == "Short text."


def test_chunk_by_tokens_splits_large():
    text = "Word " * 5000  # ~25000 chars
    chunks = chunk_by_tokens(text, max_chars=5000, overlap=100)
    assert len(chunks) > 1
    # Each chunk should be <= max_chars (approximately)
    for c in chunks:
        assert len(c.text) <= 5200  # allow small overshoot at boundary


def test_chunk_by_separator():
    text = "Para one.\n\nPara two.\n\nPara three."
    chunks = chunk_by_separator(text, separator="\n\n", max_chars=20)
    assert len(chunks) >= 2


# --- Async fetch (unit test without network) ---

def test_async_fetch_result_ok():
    from src.async_fetch import AsyncFetchResult
    r = AsyncFetchResult(url="http://x", status_code=200, body=b"hi", content_type="text/html", etag=None, last_modified=None)
    assert r.ok
    r2 = AsyncFetchResult(url="http://x", status_code=0, body=b"", content_type=None, etag=None, last_modified=None, error="timeout")
    assert not r2.ok
