"""Xuất các bản ghi documents gần đây ra Parquet (pyarrow)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .document_store import DocumentStore


def _pick(obj: dict[str, Any], key: str, default: str = "") -> str:
    v = obj.get(key)
    if v is None:
        return default
    if isinstance(v, str):
        return v
    return str(v)


def _pick_list(obj: dict[str, Any], key: str, cap: int = 30) -> list[str]:
    v = obj.get(key)
    if isinstance(v, list):
        return [str(x) for x in v[:cap]]
    return []


def _row_dict(r: Any, *, truncate_raw: int) -> dict[str, Any]:
    raw = r.raw_text or ""
    if len(raw) > truncate_raw:
        raw = raw[: truncate_raw - 20] + "\n...[truncated]..."
    sj = r.structured_json or ""
    obj: dict[str, Any] = {}
    try:
        if sj:
            parsed = json.loads(sj)
            if isinstance(parsed, dict):
                obj = parsed
    except json.JSONDecodeError:
        pass

    cp = r.meta.get("content_profile") if isinstance(r.meta, dict) else None
    kind = ""
    if isinstance(cp, dict):
        kind = str(cp.get("kind") or "")

    return {
        "doc_id": str(r.id),
        "source_id": str(r.source_id),
        "fetched_at": str(r.fetched_at),
        "content_hash": str(r.content_hash),
        "raw_text": raw,
        "structured_json": sj,
        "title": _pick(obj, "title"),
        "summary": _pick(obj, "summary"),
        "language": _pick(obj, "language"),
        "publication_or_site_name": _pick(obj, "publication_or_site_name"),
        "author_or_byline": _pick(obj, "author_or_byline"),
        "primary_date": _pick(obj, "primary_date"),
        "dates_mentioned": _pick_list(obj, "dates_mentioned"),
        "locations_mentioned": _pick_list(obj, "locations_mentioned"),
        "key_entities": _pick_list(obj, "key_entities"),
        "key_facts": _pick_list(obj, "key_facts"),
        "numbers_and_stats": _pick_list(obj, "numbers_and_stats"),
        "topics": _pick_list(obj, "topics", cap=20),
        "primary_topic": _pick(obj, "primary_topic"),
        "document_kind": _pick(obj, "document_kind"),
        "audience_or_domain": _pick(obj, "audience_or_domain"),
        "links_or_references": _pick_list(obj, "links_or_references"),
        "open_questions": _pick_list(obj, "open_questions", cap=12),
        "model_keeps_note": _pick(obj, "model_keeps_note"),
        "content_kind": kind,
        "meta_json": json.dumps(r.meta, ensure_ascii=False) if r.meta else "{}",
    }


def _empty_parquet_schema(pa: Any) -> Any:
    return {
        "doc_id": pa.array([], pa.string()),
        "source_id": pa.array([], pa.string()),
        "fetched_at": pa.array([], pa.string()),
        "content_hash": pa.array([], pa.string()),
        "raw_text": pa.array([], pa.string()),
        "structured_json": pa.array([], pa.string()),
        "title": pa.array([], pa.string()),
        "summary": pa.array([], pa.string()),
        "language": pa.array([], pa.string()),
        "publication_or_site_name": pa.array([], pa.string()),
        "author_or_byline": pa.array([], pa.string()),
        "primary_date": pa.array([], pa.string()),
        "dates_mentioned": pa.array([], pa.list_(pa.string())),
        "locations_mentioned": pa.array([], pa.list_(pa.string())),
        "key_entities": pa.array([], pa.list_(pa.string())),
        "key_facts": pa.array([], pa.list_(pa.string())),
        "numbers_and_stats": pa.array([], pa.list_(pa.string())),
        "topics": pa.array([], pa.list_(pa.string())),
        "primary_topic": pa.array([], pa.string()),
        "document_kind": pa.array([], pa.string()),
        "audience_or_domain": pa.array([], pa.string()),
        "links_or_references": pa.array([], pa.list_(pa.string())),
        "open_questions": pa.array([], pa.list_(pa.string())),
        "model_keeps_note": pa.array([], pa.string()),
        "content_kind": pa.array([], pa.string()),
        "meta_json": pa.array([], pa.string()),
    }


def export_recent_to_parquet(
    storage: DocumentStore,
    out_path: Path,
    *,
    limit: int = 10_000,
    truncate_raw: int = 32_000,
) -> int:
    """
    Ghi Parquet từ list_recent. Trả về số dòng.
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "Thiếu pyarrow. Chạy: python -m pip install pyarrow"
        ) from exc

    rows = storage.list_recent(limit=max(1, min(limit, 500_000)))
    pylist = [_row_dict(r, truncate_raw=truncate_raw) for r in rows]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not pylist:
        tab = pa.table(_empty_parquet_schema(pa))
        pq.write_table(tab, out_path)
        return 0
    table = pa.Table.from_pylist(pylist)
    pq.write_table(table, out_path)
    return len(pylist)
