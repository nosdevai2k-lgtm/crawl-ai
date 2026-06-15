"""Schema bản ghi có cấu trúc (LLM) — đủ trường để model quyết địch giữ gì."""

from __future__ import annotations

import json
from typing import Any


EMPTY_STRUCTURED_RECORD: dict[str, Any] = {
    "title": "",
    "summary": "",
    "language": "",
    "publication_or_site_name": "",
    "author_or_byline": "",
    "primary_date": "",
    "dates_mentioned": [],
    "locations_mentioned": [],
    "events_mentioned": [],
    "festivals_mentioned": [],
    "key_entities": [],
    "key_facts": [],
    "numbers_and_stats": [],
    "topics": [],
    "primary_topic": "",
    "document_kind": "",
    "audience_or_domain": "",
    "links_or_references": [],
    "open_questions": [],
    "model_keeps_note": "",
}


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    return str(v)


def _as_str_list(v: Any, *, cap: int = 40) -> list[str]:
    if v is None:
        return []
    if isinstance(v, list):
        out = [_as_str(x).strip() for x in v if _as_str(x).strip()]
        return out[:cap]
    if isinstance(v, str) and v.strip():
        return [v.strip()][:cap]
    return []


def normalize_structured(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Gộp output model với schema mặc định; giữ thêm các key đơn giản do model thêm (tối đa 24 key lạ).
    """
    out: dict[str, Any] = {}
    for key, default in EMPTY_STRUCTURED_RECORD.items():
        val = raw.get(key, default)
        if isinstance(default, list):
            out[key] = _as_str_list(val)
        else:
            out[key] = _as_str(val).strip()

    extras = 0
    for k, v in raw.items():
        if k in out or extras >= 24:
            continue
        if isinstance(v, (str, int, float, bool)):
            out[str(k)[:80]] = v if not isinstance(v, str) else v[:4000]
            extras += 1
        elif isinstance(v, list) and all(
            isinstance(x, (str, int, float)) for x in v[:60]
        ):
            out[str(k)[:80]] = _as_str_list(v, cap=30)
            extras += 1

    return out


def structured_preview_json(structured: dict[str, Any], *, max_chars: int = 12_000) -> str:
    """JSON gọn để hiển thị / log (cắt nếu quá dài)."""
    s = json.dumps(structured, ensure_ascii=False)
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 30] + "\n/* ...truncated... */\n"

