"""field_catalog — đầy đủ theo cột CSV."""

from __future__ import annotations

from src.extract import SourcePayload
from src.field_catalog import build_field_catalog, cap_field_blob_map


def test_build_field_catalog_csv_columns() -> None:
    csv = "A,B\n1,2\n3,4\n"
    p = SourcePayload(
        text=csv,
        meta={"format": "google_sheets_csv", "content_profile": {"kind": "csv_tabular"}},
    )
    cat = build_field_catalog(p)
    assert cat["raw_text"] == csv
    assert cat["col::A"] == "1\n3"
    assert cat["col::B"] == "2\n4"


def test_cap_field_blob_map_truncates() -> None:
    big = "x" * 100
    out, t = cap_field_blob_map({"a": big}, max_per_value=50)
    assert t is True
    assert len(out["a"]) <= 55
