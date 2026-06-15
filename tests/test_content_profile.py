"""Tests cho nhận diện heuristic kiểu nội dung."""

from __future__ import annotations

from src.content_profile import profile_http_bytes, profile_search_payload


def test_profile_pdf_magic() -> None:
    p = profile_http_bytes(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", "application/octet-stream", 200)
    assert p["kind"] == "pdf"
    assert "magic:%PDF" in p["signals"]


def test_profile_json_mime() -> None:
    p = profile_http_bytes(b'{"a":1}', "application/json; charset=utf-8", 200)
    assert p["kind"] == "json_like"
    assert p["mime_primary"] == "application/json"


def test_profile_json_prefix() -> None:
    p = profile_http_bytes(b'  [{"x":true}]', None, 200)
    assert p["kind"] == "json_like"


def test_profile_html_mime() -> None:
    p = profile_http_bytes(b"<html><body>x</body></html>", "text/html", 200)
    assert p["kind"] == "html"


def test_profile_xml_feed_sniff() -> None:
    xml = b'<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    p = profile_http_bytes(xml, "application/rss+xml", 200)
    assert p["kind"] == "xml_feed_like"


def test_profile_csv_mime() -> None:
    p = profile_http_bytes(b"a,b\n1,2\n", "text/csv; charset=utf-8", 200)
    assert p["kind"] == "csv_tabular"


def test_profile_search() -> None:
    p = profile_search_payload("tin moi", 10)
    assert p["kind"] == "search_snippets"
    assert p["max_results"] == 10
