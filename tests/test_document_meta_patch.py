"""get_document_by_id + patch_document_meta."""

from __future__ import annotations

import json
from pathlib import Path

from src.storage import Storage


def test_patch_document_meta_merges(tmp_path: Path) -> None:
    db = tmp_path / "m.db"
    st = Storage(db)
    i = st.insert_document(
        source_id="s1",
        content_hash="h",
        raw_text="x",
        structured_json="{}",
        meta={"a": 1},
    )
    row = st.get_document_by_id(i)
    assert row is not None
    assert row.meta.get("a") == 1
    ok = st.patch_document_meta(i, {"user_extract_fields": ["title"], "b": 2})
    assert ok
    row2 = st.get_document_by_id(i)
    assert row2 is not None
    assert row2.meta["user_extract_fields"] == ["title"]
    assert row2.meta["a"] == 1
    assert row2.meta["b"] == 2


def test_get_document_by_id_invalid(tmp_path: Path) -> None:
    st = Storage(tmp_path / "x.db")
    assert st.get_document_by_id("not-an-int") is None
