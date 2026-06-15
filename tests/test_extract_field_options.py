"""detect_extract_field_options."""

from __future__ import annotations

from src.extract_field_options import detect_extract_field_options


def test_csv_sheet_columns() -> None:
    raw = "A,B,C\n1,2,3\n"
    meta = {"format": "google_sheets_csv"}
    opts = detect_extract_field_options(structured_json=None, raw_text=raw, meta=meta)
    assert "A" in opts and "B" in opts
    assert "raw_text (full CSV)" in opts


def test_structured_keys() -> None:
    opts = detect_extract_field_options(
        structured_json='{"title":"T","summary":"S"}',
        raw_text="",
        meta={},
    )
    assert "title" in opts and "summary" in opts
