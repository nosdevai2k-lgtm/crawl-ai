"""image_harvest: tải ảnh, tự duyệt (lọc nhỏ/không-ảnh/trùng)."""

from pathlib import Path
from unittest.mock import patch

from src.async_fetch import AsyncFetchResult
from src.image_harvest import _is_real_image, harvest_landmark

_JPG = b"\xff\xd8\xff" + b"x" * 20000  # ảnh jpg hợp lệ, đủ lớn


def test_is_real_image() -> None:
    assert _is_real_image(_JPG)
    assert _is_real_image(b"\x89PNG\r\n" + b"y" * 100)
    assert not _is_real_image(b"<svg xmlns=...")
    assert not _is_real_image(b"<!DOCTYPE html>")


def _afr(url: str, body: bytes, ct: str = "image/jpeg") -> AsyncFetchResult:
    return AsyncFetchResult(url=url, status_code=200, body=body, content_type=ct,
                            etag=None, last_modified=None)


def test_harvest_filters_and_dedups(tmp_path: Path) -> None:
    urls = ["http://a/1.jpg", "http://a/2.jpg", "http://a/3.jpg", "http://a/4.jpg"]
    # mỗi url kèm title chứa tên địa danh để qua được bộ lọc relevance
    pairs = [(u, "Test Place view") for u in urls]
    results = [
        _afr(urls[0], _JPG),                       # ok
        _afr(urls[1], _JPG),                       # trùng nội dung -> bỏ
        _afr(urls[2], b"\xff\xd8\xff" + b"z" * 5),  # quá nhỏ -> bỏ
        _afr(urls[3], b"<html>not image</html>" * 999, ct="text/html"),  # không ảnh -> bỏ
    ]
    with patch("src.image_harvest.image_search_results", return_value=pairs), \
         patch("src.image_harvest.fetch_many_sync", return_value=results):
        stats = harvest_landmark("Test Place", tmp_path / "out",
                                 user_agent="ua", timeout=5, target=10)
    assert stats["saved"] == 1
    assert stats["dup"] == 1
    assert stats["too_small"] == 1
    assert stats["not_image"] == 1
    assert len([f for f in (tmp_path / "out").iterdir() if f.is_file()]) == 1


def test_harvest_drops_off_topic_titles(tmp_path: Path) -> None:
    # title không liên quan -> bị loại trước khi tải (off_topic), không lưu
    pairs = [("http://x/dogfood.jpg", "Dog food recipe BARF"),
             ("http://x/menu.jpg", "")]  # title rỗng cũng bị loại
    with patch("src.image_harvest.image_search_results", return_value=pairs), \
         patch("src.image_harvest.fetch_many_sync", return_value=[]):
        stats = harvest_landmark("Vịnh Hạ Long", tmp_path / "out2",
                                 user_agent="ua", timeout=5, en_name="Ha Long Bay", target=10)
    assert stats["off_topic"] == 2
    assert stats["saved"] == 0
