"""Harvest nhiều ảnh cho một địa danh: image-search đa truy vấn → tải → khử trùng → tự duyệt."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .async_fetch import fetch_many_sync
from .extract import image_search_results
from .image_extract import _IMG_EXT, _NOISE_IMG_NAME

# Magic bytes của định dạng ảnh raster phổ biến (loại SVG/HTML/file hỏng).
_IMG_SIGS = (b"\xff\xd8\xff", b"\x89PNG\r\n", b"GIF87a", b"GIF89a", b"BM")


def _is_real_image(body: bytes) -> bool:
    head = body[:16]
    if any(head.startswith(s) for s in _IMG_SIGS):
        return True
    if head[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return True
    return False


def _query_variants(name: str, en: str | None = None) -> list[str]:
    base = [name, f"{name} du lịch", f"{name} phong cảnh", f"{name} đẹp",
            f"{name} check in", f"{name} ảnh", f"{name} toàn cảnh", f"{name} về đêm"]
    if en:
        base += [en, f"{en} travel", f"{en} landscape", f"{en} scenery",
                 f"{en} tourism", f"{en} photography", f"{en} aerial view", f"{en} sunset"]
    return base


def _ascii_tokens(text: str) -> set[str]:
    """Token ASCII không dấu, viết thường (để so khớp title không phụ thuộc dấu tiếng Việt)."""
    import re
    import unicodedata

    s = unicodedata.normalize("NFKD", text).replace("đ", "d").replace("Đ", "D")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 3}


# Token chung (du lịch/địa lý) — không tính là "khớp tên địa danh".
_STOP = {"du", "lich", "lịch", "viet", "nam", "vietnam", "travel", "tourism", "landscape",
         "scenery", "photography", "aerial", "view", "sunset", "city", "beach", "national",
         "park", "the", "and", "tour", "guide", "anh", "dep", "phong", "canh"}


def _title_relevant(title: str, name_tokens: set[str]) -> bool:
    """Title coi là liên quan nếu chứa ≥1 token đặc trưng của tên địa danh."""
    if not title.strip():
        return False  # không có title → không xác minh được → bỏ (tránh ảnh rác)
    return bool(name_tokens & _ascii_tokens(title))


def harvest_landmark(
    name: str,
    out_dir: Path,
    *,
    user_agent: str,
    timeout: float,
    en_name: str | None = None,
    target: int = 400,
    min_bytes: int = 8000,
) -> dict[str, int]:
    """Tải tối đa `target` ảnh cho địa danh vào out_dir. Trả thống kê. Tự duyệt: bỏ ảnh nhỏ/trùng/hỏng."""
    out_dir.mkdir(parents=True, exist_ok=True)
    # token đặc trưng của tên địa danh (loại token du lịch/địa lý chung)
    name_tokens = (_ascii_tokens(name) | _ascii_tokens(en_name or "")) - _STOP
    # 1) gom URL từ nhiều truy vấn, chỉ giữ ảnh có title khớp tên địa danh
    urls: list[str] = []
    seen_url: set[str] = set()
    stats_filtered = 0
    for q in _query_variants(name, en_name):
        for u, title in image_search_results(q, max_results=200):
            if u in seen_url:
                continue
            seen_url.add(u)
            if name_tokens and not _title_relevant(title, name_tokens):
                stats_filtered += 1
                continue
            urls.append(u)
        if len(urls) >= target * 3:  # dư để bù ảnh hỏng/nhỏ/trùng
            break

    # 2) tải song song theo lô, khử trùng theo nội dung (hash bytes)
    saved = 0
    seen_hash: set[str] = set()
    # đánh số tiếp theo ảnh đã có trong thư mục (hỗ trợ chạy bổ sung)
    idx = len([f for f in out_dir.iterdir() if f.is_file() and f.suffix.lower() != ".json"])
    slug = out_dir.name
    stats = {"urls": len(urls), "saved": 0, "too_small": 0, "dup": 0, "failed": 0, "not_image": 0, "off_topic": stats_filtered}
    batch = 60
    for i in range(0, len(urls), batch):
        if saved >= target:
            break
        chunk = urls[i:i + batch]
        results = fetch_many_sync(chunk, user_agent=user_agent, timeout=timeout, max_concurrent=12)
        for u, fr in zip(chunk, results):
            if saved >= target:
                break
            if not fr.ok or not fr.body:
                stats["failed"] += 1
                continue
            is_img = (fr.content_type or "").lower().startswith("image/")
            if not is_img and not _IMG_EXT.search(u):
                stats["not_image"] += 1
                continue
            if len(fr.body) < min_bytes or _NOISE_IMG_NAME.search(u):
                stats["too_small"] += 1
                continue
            if not _is_real_image(fr.body):
                stats["not_image"] += 1
                continue
            h = hashlib.sha256(fr.body).hexdigest()
            if h in seen_hash:
                stats["dup"] += 1
                continue
            seen_hash.add(h)
            idx += 1
            ext = ".jpg" if (fr.content_type or "").lower().endswith(("jpeg", "jpg")) else ""
            if not ext:
                from pathlib import PurePosixPath
                ext = PurePosixPath(u.split("?")[0]).suffix.lower() or ".jpg"
                if ext == ".jpeg":
                    ext = ".jpg"
            (out_dir / f"{slug}_{idx:03d}{ext}").write_bytes(fr.body)
            saved += 1
    stats["saved"] = saved
    return stats
