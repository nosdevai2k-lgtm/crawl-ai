"""Schema structured_record."""

from __future__ import annotations

from src.structured_record import (
    EMPTY_STRUCTURED_RECORD,
    normalize_structured,
)


def test_normalize_fills_defaults() -> None:
    raw = {"title": "T", "topics": ["a", "b"]}
    n = normalize_structured(raw)
    assert n["title"] == "T"
    assert n["topics"] == ["a", "b"]
    assert n["summary"] == ""
    assert "primary_date" in n


def test_normalize_keeps_simple_extra() -> None:
    n = normalize_structured({"title": "x", "custom_score": 0.9})
    assert n["title"] == "x"
    assert n["custom_score"] == 0.9


def test_empty_template_has_all_keys() -> None:
    assert "model_keeps_note" in EMPTY_STRUCTURED_RECORD
    assert isinstance(EMPTY_STRUCTURED_RECORD["key_facts"], list)
