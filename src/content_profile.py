"""Heuristic profile of fetched bytes (MIME + magic + light sniffing).

Dùng để gắn meta phục vụ lọc/index sau crawl — không thay thế parser chuyên sâu.
"""

from __future__ import annotations

from typing import Any


def profile_http_bytes(
    body: bytes,
    content_type: str | None,
    status_code: int,
    *,
    max_sniff: int = 8192,
) -> dict[str, Any]:
    """
    Trả về dict JSON-serializable: kind, mime, độ dài, vài tín hiệu heuristic.
    """
    ct_raw = (content_type or "").strip()
    mime = ct_raw.split(";")[0].strip().lower() if ct_raw else ""
    head = body[:max_sniff].lstrip()
    hl = head.lower()
    signals: list[str] = []
    kind = "unknown"

    if head[:4] == b"%PDF":
        kind = "pdf"
        signals.append("magic:%PDF")
    elif mime == "application/json" or head[:1] in (b"{", b"["):
        kind = "json_like"
        if mime == "application/json":
            signals.append("mime:application/json")
        else:
            signals.append("prefix:json_array_or_object")
    elif mime in ("text/csv", "application/csv") or (
        mime.startswith("text/") and "csv" in mime
    ):
        kind = "csv_tabular"
        signals.append(f"mime:{mime}")
    elif b"<rss" in hl[:4000] or b"<feed" in hl[:4000] or b"xmlns=\"http://www.w3.org/2005/atom\"" in hl[:4000]:
        kind = "xml_feed_like"
        signals.append("xml:rss_or_atom_hint")
    elif "text/html" in mime or b"<html" in hl[:2000] or b"<!doctype html" in hl[:2000]:
        kind = "html"
        if "text/html" in mime:
            signals.append("mime:text/html")
        else:
            signals.append("bytes:html_tag")
    elif "text/xml" in mime or "application/xml" in mime:
        kind = "xml"
        signals.append(f"mime:{mime}")
    elif mime.startswith("text/"):
        kind = "text"
        signals.append(f"mime:{mime}")
    elif mime:
        kind = "other_typed"
        signals.append(f"mime:{mime}")
    else:
        kind = "opaque_bytes"
        if head[:2] == b"PK":
            signals.append("magic:zip_family")

    return {
        "kind": kind,
        "mime_reported": content_type,
        "mime_primary": mime or None,
        "http_status": status_code,
        "byte_length": len(body),
        "signals": signals,
    }


def profile_search_payload(query: str, max_results: int) -> dict[str, Any]:
    return {
        "kind": "search_snippets",
        "query": query,
        "max_results": max_results,
        "signals": ["source:duckduckgo_text"],
    }
