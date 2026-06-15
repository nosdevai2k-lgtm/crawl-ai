"""Test crawl ảnh (image_extract) và crawl tự động bằng prompt (auto_crawl)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.fetch import FetchResult
from src.image_extract import download_images, extract_image_urls, extract_image_names


HTML = """
<html><head>
<meta property="og:image" content="https://site/og.png">
<meta name="twitter:image" content="https://site/tw.jpg">
</head><body>
<img src="/a.jpg">
<img data-src="https://cdn/b.png" srcset="https://cdn/b-2x.png 2x">
<img src="data:image/gif;base64,xxxx">
</body></html>
"""


def test_extract_image_urls_sources_and_dedup() -> None:
    urls = extract_image_urls(HTML, "https://site/page")
    assert "https://site/og.png" in urls
    assert "https://site/tw.jpg" in urls
    assert "https://site/a.jpg" in urls  # joined to base
    assert "https://cdn/b.png" in urls          # ưu tiên data-src
    assert "https://cdn/b-2x.png" not in urls    # không lấy biến thể srcset của cùng img
    assert not any(u.startswith("data:") for u in urls)  # data URI bị bỏ
    assert len(urls) == len(set(urls))  # không trùng


def test_extract_image_names_alt_caption_ogtitle() -> None:
    html = """
    <html><head><title>Vịnh Hạ Long</title>
    <meta property="og:title" content="Vịnh Hạ Long - Kỳ quan">
    <meta property="og:image" content="https://site/hl.jpg"></head><body>
    <img src="/a.jpg" alt="Chùa Một Cột">
    <figure><img src="/b.jpg"><figcaption>Phố cổ Hội An</figcaption></figure>
    </body></html>
    """
    names = extract_image_names(html, "https://site/p")
    assert names["https://site/a.jpg"] == "Chùa Một Cột"
    assert names["https://site/b.jpg"] == "Phố cổ Hội An"
    assert names["https://site/hl.jpg"] == "Vịnh Hạ Long - Kỳ quan"

def test_extract_image_urls_filters_chrome_and_place() -> None:
    from src.image_extract import extract_page_title
    noisy = """
    <html><head><title>Sa Pa – Wikipedia tiếng Việt</title>
    <meta property="og:title" content="Sa Pa"></head><body>
    <img src="https://vi.wikipedia.org/static/images/icons/wikipedia.png" alt="Wikipedia">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/x/Fansipan.jpg" alt="Cáp treo Fansipan">
    <img src="https://upload.wikimedia.org/wikipedia/vi/thumb/3/Logo_tinh.png" alt="Stub icon">
    </body></html>
    """
    urls = extract_image_urls(noisy, "https://vi.wikipedia.org/wiki/Sa_Pa")
    assert any("Fansipan" in u for u in urls)
    assert not any("static/images" in u for u in urls)
    assert not any("Logo_tinh" in u for u in urls)
    names = extract_image_names(noisy, "https://vi.wikipedia.org/wiki/Sa_Pa")
    assert all(n.lower() != "wikipedia" for n in names.values())
    assert "stub icon" not in [n.lower() for n in names.values()]
    assert extract_page_title(noisy) == "Sa Pa"




def test_download_images_includes_name(tmp_path: Path, monkeypatch) -> None:
    from src.async_fetch import AsyncFetchResult

    def fake_many(urls, **kwargs):
        return [
            AsyncFetchResult(
                url=u, status_code=200, body=b"\xff\xd8\xff" + b"x" * 4000,
                content_type="image/jpeg", etag=None, last_modified=None,
            )
            for u in urls
        ]

    monkeypatch.setattr("src.async_fetch.fetch_many_sync", fake_many)
    saved = download_images(
        ["https://site/a.jpg"], tmp_path, user_agent="t", timeout=5.0,
        names={"https://site/a.jpg": "Chùa Một Cột"},
    )
    assert saved[0]["name"] == "Chùa Một Cột"


def test_download_images_writes_files(tmp_path: Path, monkeypatch) -> None:
    from src.async_fetch import AsyncFetchResult

    def fake_many(urls, **kwargs):
        return [
            AsyncFetchResult(
                url=u, status_code=200, body=b"\xff\xd8\xff" + b"x" * 4000,
                content_type="image/jpeg", etag=None, last_modified=None,
            )
            for u in urls
        ]

    monkeypatch.setattr("src.async_fetch.fetch_many_sync", fake_many)
    saved = download_images(
        ["https://site/a.jpg", "https://site/b.png"],
        tmp_path, user_agent="t", timeout=5.0,
    )
    assert len(saved) == 2
    for item in saved:
        assert Path(item["path"]).is_file()
        assert item["content_type"] == "image/jpeg"


def test_download_images_skips_non_image(tmp_path: Path, monkeypatch) -> None:
    from src.async_fetch import AsyncFetchResult

    def fake_many(urls, **kwargs):
        return [
            AsyncFetchResult(
                url=u, status_code=200, body=b"<html>" + b"x" * 4000,
                content_type="text/html", etag=None, last_modified=None,
            )
            for u in urls
        ]

    monkeypatch.setattr("src.async_fetch.fetch_many_sync", fake_many)
    # URL không có đuôi ảnh + content-type không phải image -> bỏ qua
    saved = download_images(["https://site/page"], tmp_path, user_agent="t", timeout=5.0)
    assert saved == []


# ---- auto_crawl ----

from src.auto_crawl import auto_crawl, suggestion_to_source
from src.pipeline import PipelineResult


def test_suggestion_to_source_maps_kinds() -> None:
    assert suggestion_to_source({"kind": "URL", "value": "https://a"}).type == "url"
    assert suggestion_to_source({"kind": "RSS", "value": "https://a/feed"}).type == "rss"
    assert suggestion_to_source({"kind": "Search", "value": "abc"}).type == "search"
    with pytest.raises(ValueError):
        suggestion_to_source({"kind": "BAD", "value": "x"})


def test_suggestion_to_source_images_flag() -> None:
    src = suggestion_to_source({"kind": "URL", "value": "https://a"}, crawl_images=True)
    assert src.crawl_images is True


def test_auto_crawl_runs_each_suggestion(monkeypatch) -> None:
    suggestions = [
        {"kind": "URL", "value": "https://a", "title": "A", "rationale": ""},
        {"kind": "Search", "value": "q", "title": "Q", "rationale": ""},
    ]
    monkeypatch.setattr(
        "src.auto_crawl.suggest_crawl_sources", lambda *a, **k: suggestions
    )

    calls: list[str] = []

    def fake_run(src, storage, settings, client):
        calls.append(src.type)
        return PipelineResult(
            source_id=src.id, changed=True, skipped_reason=None,
            content_hash="h", document_id=1,
        )

    monkeypatch.setattr("src.auto_crawl.run_source", fake_run)
    items = auto_crawl("goal", storage=None, settings=None)
    assert len(items) == 2
    assert calls == ["url", "search"]
    assert all(it.result and it.result.changed for it in items)


def test_auto_crawl_captures_errors(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.auto_crawl.suggest_crawl_sources",
        lambda *a, **k: [{"kind": "URL", "value": "https://a", "title": "", "rationale": ""}],
    )

    def boom(*a, **k):
        raise RuntimeError("fail")

    monkeypatch.setattr("src.auto_crawl.run_source", boom)
    items = auto_crawl("goal", storage=None, settings=None)
    assert len(items) == 1
    assert items[0].error and "RuntimeError" in items[0].error
