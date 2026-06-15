"""OPML → config sources."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.opml_import import (
    feeds_to_yaml_sources,
    merge_opml_into_config,
    parse_opml_feeds,
)

_SAMPLE_OPML = """<?xml version="1.0" encoding="UTF-8"?>
<opml version="1.0">
  <head><title>Test</title></head>
  <body>
    <outline text="A1" title="Alpha One" type="rss" xmlUrl="https://a.example/feed.xml"/>
    <outline text="Dup" xmlUrl="https://a.example/feed.xml"/>
    <outline text="B2" xmlUrl="https://b.example/rss"/>
  </body>
</opml>
"""


def test_parse_opml_feeds_unique_xmlurl(tmp_path: Path) -> None:
    p = tmp_path / "f.opml"
    p.write_text(_SAMPLE_OPML, encoding="utf-8")
    feeds = parse_opml_feeds(p)
    urls = [u for _t, u in feeds]
    assert "https://a.example/feed.xml" in urls
    assert "https://b.example/rss" in urls
    assert feeds[0][0]


def test_merge_opml_idempotent(tmp_path: Path) -> None:
    opml = tmp_path / "in.opml"
    opml.write_text(_SAMPLE_OPML, encoding="utf-8")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("sources: []\n", encoding="utf-8")
    a1, s1 = merge_opml_into_config(opml, cfg)
    assert a1 == 2
    assert s1 == 1
    data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
    assert len(data["sources"]) == 2
    a2, s2 = merge_opml_into_config(opml, cfg)
    assert a2 == 0
    assert s2 == 3


def test_feeds_to_yaml_sources_cron() -> None:
    rows = feeds_to_yaml_sources([("T", "https://x/1")], schedule_cron="0 0 * * *")
    assert rows[0]["schedule_cron"] == "0 0 * * *"
    assert rows[0]["type"] == "rss"
