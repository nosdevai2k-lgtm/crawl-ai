"""Đọc OPML (outline + xmlUrl) và gộp thành mục sources kiểu RSS trong config.yaml."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from .quick_sources import rss_feed_source_id


def parse_opml_feeds(path: Path) -> list[tuple[str, str]]:
    """
    Trả về danh sách (title_or_text, xml_url) cho mọi <outline> có xmlUrl.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    root = ET.fromstring(text)
    out: list[tuple[str, str]] = []
    for el in root.iter("outline"):
        xml_url = (el.get("xmlUrl") or el.get("xmlurl") or "").strip()
        if not xml_url:
            continue
        title = (
            el.get("title")
            or el.get("text")
            or el.get("description")
            or "feed"
        ).strip()
        out.append((title, xml_url))
    return out


def feeds_to_yaml_sources(
    feeds: list[tuple[str, str]],
    schedule_cron: str = "15 * * * *",
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for title, xml_url in feeds:
        sid = rss_feed_source_id(title, xml_url)
        rows.append(
            {
                "id": sid,
                "type": "rss",
                "schedule_cron": schedule_cron,
                "extract": "article",
                "url": xml_url,
                "rss_max_entries": 25,
            }
        )
    return rows


def merge_opml_into_config(
    opml_path: Path,
    config_path: Path,
    *,
    default_cron: str = "15 * * * *",
) -> tuple[int, int]:
    """
    Gộp feed từ OPML vào config.yaml (bỏ qua trùng id hoặc trùng url).
    Trả về (số_mục_thêm, số_mục_bỏ_qua).
    """
    feeds = parse_opml_feeds(opml_path)
    if config_path.is_file():
        data: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    else:
        data = {"sources": []}
    sources: list[dict[str, Any]] = list(data.get("sources") or [])
    existing_ids = {str(s.get("id")) for s in sources if s.get("id")}
    existing_urls = {
        str(s.get("url"))
        for s in sources
        if s.get("type") == "rss" and s.get("url")
    }
    added = 0
    skipped = 0
    for entry in feeds_to_yaml_sources(feeds, schedule_cron=default_cron):
        sid = str(entry["id"])
        xml_url = str(entry["url"])
        if sid in existing_ids or xml_url in existing_urls:
            skipped += 1
            continue
        sources.append(entry)
        existing_ids.add(sid)
        existing_urls.add(xml_url)
        added += 1
    data["sources"] = sources
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            data,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return added, skipped
