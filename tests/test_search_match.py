"""search_match + stricter KG search."""

from pathlib import Path

import pytest

from src.kg.search import structured_search
from src.search_match import compact_why, meaningful_overlap, resolve_search_context


@pytest.fixture()
def kg_db(tmp_path: Path) -> Path:
    return tmp_path / "crawl.db"


def test_meaningful_overlap_ignores_stop() -> None:
    assert meaningful_overlap({"nha"}, {"nha", "hang"}) == 0
    assert meaningful_overlap({"chinh", "sach", "xa", "hoi"}, {"chinh", "sach", "xa", "hoi", "nha"}) >= 3


def test_compact_why_dedupes() -> None:
    raw = "a; a; b; c; d; e"
    out = compact_why(raw, max_parts=3)
    assert out.count("a") == 1
    assert " · " in out


def test_resolve_builtin_person(tmp_path: Path) -> None:
    from src.kg.storage import KGStorage
    from src.kg.aliases import seed_builtin_aliases

    db = tmp_path / "kg.db"
    kg = KGStorage(db)
    seed_builtin_aliases(kg)
    ctx = resolve_search_context(db, entities="Tô Lâm", topics="")
    assert ctx["resolved"]
    assert ctx["resolved"][0]["label"] == "Person"
    assert ctx["primary_preset"] == "nhan_vat"


def test_structured_search_strict_location(tmp_path: Path, kg_db: Path) -> None:
    """Hà Nội không nên trả Hạ Long khi chỉ khớp token yếu."""
    from src.kg.indexer import index_document_kg

    index_document_kg(
        kg_db,
        "doc_hl",
        "src_hl",
        {
            "title": "Vịnh Hạ Long thông tin du lịch",
            "summary": "Vịnh Hạ Long nổi tiếng.",
            "topics": ["du lịch"],
            "locations_mentioned": ["Vịnh Hạ Long"],
        },
        {},
    )
    index_document_kg(
        kg_db,
        "doc_hn",
        "src_hn",
        {
            "title": "Hà Nội mùa thu",
            "summary": "Thủ đô Hà Nội đẹp.",
            "topics": ["du lịch"],
            "locations_mentioned": ["Hà Nội"],
        },
        {},
    )
    res = structured_search(kg_db, entities="Hà Nội", topics="", top_k=10)
    titles = [r.get("title", "") for r in res.get("results") or []]
    assert any("Hà Nội" in t for t in titles)
    assert not any("Hạ Long" in t for t in titles)
