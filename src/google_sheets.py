"""Google Sheets: URL trình duyệt → tải CSV công khai (không cần headless)."""

from __future__ import annotations

import re


def spreadsheet_csv_export_url(browser_url: str) -> str | None:
    """
    Nếu `browser_url` là link mở Google Sheet (docs.google.com/.../d/<id>/...),
    trả về URL `.../export?format=csv&gid=...` để lấy nội dung ô (sheet **public**
    hoặc “Anyone with the link can view”).

    Trả về None nếu không phải URL Sheets hợp lệ.
    """
    u = (browser_url or "").strip()
    if "docs.google.com/spreadsheets/d/" not in u:
        return None
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", u)
    if not m:
        return None
    sid = m.group(1)
    gid = "0"
    gm = re.search(r"gid=(\d+)", u)
    if gm:
        gid = gm.group(1)
    return (
        f"https://docs.google.com/spreadsheets/d/{sid}/export"
        f"?format=csv&gid={gid}"
    )


def looks_like_csv_text(text: str) -> bool:
    """Loại HTML login / shell; chấp nhận CSV có dấu phẩy hoặc chấm phẩy."""
    s = text.strip()
    if len(s) < 2:
        return False
    low = s[:800].lstrip().lower()
    if low.startswith("<!doctype") or low.startswith("<html"):
        return False
    if "<table" in low[:2000]:
        return False
    first = s.splitlines()[0] if s else ""
    return "," in first or ";" in first
