"""Gom toàn bộ nội dung theo từng “trường” logic để preview / chọn trước khi lưu."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from .extract import SourcePayload


def _csv_columns_full_strings(csv_text: str) -> dict[str, str]:
    """Mỗi cột CSV → một chuỗi (mọi dòng, đầy đủ), key dạng `col::TênCột`."""
    s = (csv_text or "").strip()
    if not s:
        return {}
    reader = csv.DictReader(StringIO(s))
    if not reader.fieldnames:
        return {}
    names = [h for h in reader.fieldnames if h is not None and str(h).strip()]
    if not names:
        return {}
    acc: dict[str, list[str]] = {h: [] for h in names}
    for row in reader:
        for h in names:
            acc[h].append((row.get(h) or "").strip())
    return {f"col::{h}": "\n".join(acc[h]) for h in names}


def build_field_catalog(payload: SourcePayload) -> dict[str, str]:
    """
    Trả về map id_trường → nội dung đầy đủ (không cắt) cho UI preview.
    """
    out: dict[str, str] = {}
    text = payload.text or ""
    out["raw_text"] = text
    meta = payload.meta if isinstance(payload.meta, dict) else {}
    for mk in (
        "fetched_url",
        "google_sheets_browser_url",
        "feed_url",
        "content_type",
        "format",
    ):
        v = meta.get(mk)
        if v is not None and str(v).strip():
            out[f"meta::{mk}"] = str(v)
    fmt = meta.get("format")
    prof = meta.get("content_profile")
    kind = ""
    if isinstance(prof, dict):
        kind = str(prof.get("kind") or "")
    if fmt == "google_sheets_csv" or kind == "csv_tabular":
        out.update(_csv_columns_full_strings(text))
    if fmt == "youtube":
        videos = meta.get("videos") or []
        for i, v in enumerate(videos):
            prefix = f"video_{i+1}"
            out[f"{prefix}::title"] = v.get("title", "")
            out[f"{prefix}::description"] = v.get("description", "")
            out[f"{prefix}::channel"] = v.get("channel", "")
            out[f"{prefix}::upload_date"] = v.get("upload_date", "")
            out[f"{prefix}::duration"] = str(v.get("duration", 0))
            out[f"{prefix}::view_count"] = str(v.get("view_count", 0))
            out[f"{prefix}::tags"] = ", ".join(v.get("tags") or [])
            out[f"{prefix}::url"] = v.get("url", "")
            out[f"{prefix}::file_path"] = v.get("file_path", "")
    images = meta.get("images") or []
    for i, im in enumerate(images):
        prefix = f"image_{i+1}"
        out[f"{prefix}::url"] = im.get("url", "")
        out[f"{prefix}::path"] = im.get("path", "")
        out[f"{prefix}::name"] = im.get("name", "")
    return out


def cap_field_blob_map(
    blobs: dict[str, str], *, max_per_value: int = 900_000
) -> tuple[dict[str, str], bool]:
    """Cắt từng giá trị để tránh BSON quá lớn. Trả về (dict, truncated_any)."""
    truncated = False
    out: dict[str, str] = {}
    for k, v in blobs.items():
        if len(v) <= max_per_value:
            out[k] = v
        else:
            truncated = True
            out[k] = v[: max_per_value - 40] + "\n...[truncated for storage limit]..."
    return out, truncated
