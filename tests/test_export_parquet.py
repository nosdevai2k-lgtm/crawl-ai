"""Export documents → Parquet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pyarrow = pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402

from src.export_parquet import export_recent_to_parquet
from src.storage import Storage


def test_export_parquet_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "e.db"
    st = Storage(db)
    st.insert_document(
        source_id="s1",
        content_hash="h1",
        raw_text="hello " * 100,
        structured_json=json.dumps(
            {
                "title": "T",
                "summary": "S",
                "primary_date": "2026-01-15",
                "publication_or_site_name": "Example News",
                "topics": ["news", "tech"],
                "primary_topic": "tech",
                "key_facts": ["Fact one"],
            },
            ensure_ascii=False,
        ),
        meta={"content_profile": {"kind": "html"}},
        etag=None,
    )
    out = tmp_path / "out.parquet"
    n = export_recent_to_parquet(st, out, limit=50, truncate_raw=500)
    assert n == 1
    t = pq.read_table(out)
    assert t.num_rows == 1
    d = t.to_pylist()[0]
    assert d["source_id"] == "s1"
    assert d["title"] == "T"
    assert d["topics"] == ["news", "tech"]
    assert d["primary_date"] == "2026-01-15"
    assert d["publication_or_site_name"] == "Example News"
    assert d["key_facts"] == ["Fact one"]


def test_export_parquet_empty_db(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    st = Storage(db)
    out = tmp_path / "empty.parquet"
    n = export_recent_to_parquet(st, out, limit=10)
    assert n == 0
    t = pq.read_table(out)
    assert t.num_rows == 0
