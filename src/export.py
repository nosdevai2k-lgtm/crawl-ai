"""Export crawled data from DB to CSV, JSON, or Excel."""

from __future__ import annotations

import csv
import json
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from .storage import DocumentRow


def _row_to_flat(row: DocumentRow) -> dict[str, Any]:
    """Flatten a DocumentRow into a simple dict for export."""
    meta = row.meta or {}
    return {
        "id": row.id,
        "source_id": row.source_id,
        "url": meta.get("fetched_url") or meta.get("youtube_url") or meta.get("feed_url") or meta.get("start_url") or "",
        "format": meta.get("format", ""),
        "fetched_at": row.fetched_at,
        "text": row.raw_text[:50000],
    }


def export_to_csv(rows: list[DocumentRow]) -> bytes:
    """Export rows to CSV bytes (UTF-8 with BOM for Excel compatibility)."""
    if not rows:
        return b""
    flat = [_row_to_flat(r) for r in rows]
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=flat[0].keys())
    writer.writeheader()
    writer.writerows(flat)
    return b"\xef\xbb\xbf" + output.getvalue().encode("utf-8")


def export_to_json(rows: list[DocumentRow]) -> bytes:
    """Export rows to JSON bytes (UTF-8)."""
    flat = [_row_to_flat(r) for r in rows]
    return json.dumps(flat, ensure_ascii=False, indent=2).encode("utf-8")


def export_to_excel(rows: list[DocumentRow]) -> bytes:
    """Export rows to Excel bytes (xlsx)."""
    try:
        import openpyxl
    except ImportError:
        # Fallback: return CSV as bytes if openpyxl not installed
        return export_to_csv(rows).encode("utf-8-sig")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Crawled Data"

    if not rows:
        return b""

    flat = [_row_to_flat(r) for r in rows]
    headers = list(flat[0].keys())
    ws.append(headers)
    for item in flat:
        ws.append([str(item.get(h, ""))[:32767] for h in headers])  # Excel cell limit

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_to_file(rows: list[DocumentRow], path: str, fmt: str = "csv") -> str:
    """Export rows to a file. Returns the file path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        p.write_text(export_to_json(rows), encoding="utf-8")
    elif fmt == "excel":
        p.write_bytes(export_to_excel(rows))
    else:
        p.write_text(export_to_csv(rows), encoding="utf-8-sig")
    return str(p)
