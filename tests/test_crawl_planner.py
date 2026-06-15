"""crawl_planner: URL an toàn và chuẩn hoá JSON gợi ý."""

import pytest

from src.crawl_planner import assert_safe_http_url, normalize_suggestions


def test_assert_safe_http_url_ok() -> None:
    assert assert_safe_http_url("https://example.com/a").startswith("https://")


def test_assert_safe_http_url_rejects_file() -> None:
    with pytest.raises(ValueError):
        assert_safe_http_url("file:///etc/passwd")


def test_normalize_suggestions_filters() -> None:
    raw = [
        {"kind": "URL", "value": "https://a", "title": "A", "rationale": "r"},
        {"kind": "BAD", "value": "x", "title": "", "rationale": ""},
        {"kind": "RSS", "value": "", "title": "x", "rationale": ""},
    ]
    out = normalize_suggestions(raw)
    assert len(out) == 1
    assert out[0]["kind"] == "URL"
    assert out[0]["value"] == "https://a"
