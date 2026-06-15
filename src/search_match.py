"""Shared name resolution and token matching for KG + image search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .kg.aliases import resolve_name
from .kg.normalize import ascii_norm, tokens
from .kg.storage import KGStorage

# Token quá ngắn / chung — không dùng để match chủ đề hoặc tên.
STOP_TOKENS = {
    "nha", "le", "su", "kien", "tet", "ngay", "the", "and", "cua", "tai", "cho", "cac",
    "mot", "nhieu", "du", "lich", "viet", "nam", "city", "tour", "travel", "anh", "dep",
    "phong", "canh", "tin", "tuc", "bai", "viec", "thong", "tin", "ve", "la", "co",
}

PRESET_BY_LABEL = {
    "Person": "nhan_vat",
    "Location": "dia_diem",
    "Event": "le_su_kien",
    "Festival": "le_su_kien",
    "Topic": "tin_tuc",
}

_LABEL_ICON = {
    "Person": "👤",
    "Location": "📍",
    "Event": "🎌",
    "Festival": "🎌",
    "Topic": "📰",
}


def resolve_search_context(
    db_path: Path,
    *,
    entities: str = "",
    topics: str = "",
) -> dict[str, Any]:
    """Resolve semicolon-separated names via KG aliases."""
    import re

    kg = KGStorage(db_path)
    entity_names = [p.strip() for p in re.split(r"[;|,]+", entities or "") if p.strip()]
    topic_names = [p.strip() for p in re.split(r"[;|,]+", topics or "") if p.strip()]
    resolved: list[dict[str, Any]] = []
    unresolved: list[str] = []
    node_ids: set[str] = set()
    presets: set[str] = set()

    for name in entity_names + topic_names:
        canon, label, nid = resolve_name(kg, name)
        if canon and nid:
            resolved.append({
                "input": name,
                "canonical": canon,
                "label": label,
                "node_id": nid,
                "tokens": tokens(canon) | tokens(name),
                "preset": PRESET_BY_LABEL.get(label or "", "tong_hop"),
            })
            node_ids.add(nid)
            if label in PRESET_BY_LABEL:
                presets.add(PRESET_BY_LABEL[label])
        else:
            unresolved.append(name)

    query_tokens: set[str] = set()
    for n in entity_names + topic_names:
        query_tokens |= tokens(n)
    for r in resolved:
        query_tokens |= r["tokens"]

    # Chủ đề nhiều từ: ưu tiên cụm, bỏ stop token đơn lẻ
    topic_tokens = tokens(" ".join(topic_names)) - STOP_TOKENS

    return {
        "entity_names": entity_names,
        "topic_names": topic_names,
        "resolved": resolved,
        "unresolved": unresolved,
        "node_ids": node_ids,
        "query_tokens": query_tokens,
        "topic_tokens": topic_tokens,
        "suggested_presets": sorted(presets) or ["tong_hop"],
        "primary_preset": sorted(presets)[0] if presets else "tong_hop",
    }


def meaningful_overlap(query_tokens: set[str], blob_tokens: set[str], *, min_len: int = 3) -> int:
    """Count overlapping tokens, ignoring stop words and very short tokens."""
    q = {t for t in query_tokens if len(t) >= min_len and t not in STOP_TOKENS}
    b = {t for t in blob_tokens if len(t) >= min_len and t not in STOP_TOKENS}
    if not q:
        return 0
    return len(q & b)


def compact_why(raw: str, *, max_parts: int = 4) -> str:
    parts: list[str] = []
    for chunk in (raw or "").replace("·", ";").split(";"):
        p = chunk.strip()
        if p and p not in parts:
            parts.append(p)
        if len(parts) >= max_parts:
            break
    return " · ".join(parts)


def normalize_score(value: float, *, src: str) -> float:
    """Map heterogeneous scores onto ~0..100 for fair merge."""
    if src in ("local", "kg"):
        return float(value) * 12.0
    if src in ("image_index", "image"):
        return float(value) * 8.0
    if src in ("document_index", "doc"):
        return float(value) * 6.0
    return float(value)
