"""Gợi ý danh sách trường để user chọn sau crawl (JSON / cột CSV)."""

from __future__ import annotations

import json
from typing import Any, Optional


def _csv_header_columns(raw_text: str) -> list[str]:
    line = raw_text.strip().splitlines()[0] if raw_text.strip() else ""
    if not line or ("," not in line and ";" not in line):
        return []
    delim = "," if line.count(",") >= line.count(";") else ";"
    parts = [p.strip().strip('"').strip("'") for p in line.split(delim)]
    return [p for p in parts if p]


def detect_extract_field_options(
    *,
    structured_json: Optional[str],
    raw_text: str,
    meta: dict[str, Any],
) -> list[str]:
    """
    Trả về danh sách nhãn trường cho multiselect (không trùng, giữ thứ tự).
    """
    seen: set[str] = set()
    out: list[str] = []

    def add_many(keys: list[str]) -> None:
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                out.append(k)

    fmt = meta.get("format")
    prof = meta.get("content_profile") if isinstance(meta.get("content_profile"), dict) else {}
    kind = prof.get("kind") if isinstance(prof, dict) else ""
    if fmt == "google_sheets_csv" or kind == "csv_tabular":
        cols = _csv_header_columns(raw_text)
        if cols:
            add_many(cols)
            add_many(["raw_text (full CSV)"])
            return out

    if structured_json:
        try:
            o = json.loads(structured_json)
            if isinstance(o, dict):
                add_many(list(o.keys()))
        except json.JSONDecodeError:
            pass

    if not out:
        add_many(["raw_text", "title", "summary"])

    return out
