"""KG extract, index, search."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.kg.aliases import resolve_name, seed_builtin_aliases
from src.kg.extract import extract_from_document
from src.kg.indexer import index_document_kg, rebuild_kg_from_store
from src.kg.scenes import scenes_from_key_facts
from src.kg.search import structured_search
from src.kg.unified_search import unified_search, _dedupe_merged
from src.kg.storage import KGStorage
from src.storage import Storage


@pytest.fixture()
def kg_db(tmp_path: Path) -> Path:
    return tmp_path / "crawl.db"


def test_extract_locations_events(tmp_path: Path) -> None:
    structured = {
        "title": "Lễ hội Hạ Long 2026",
        "summary": "Lễ hội diễn ra tại Vịnh Hạ Long, Quảng Ninh.",
        "primary_date": "2026-05-01",
        "locations_mentioned": ["Vịnh Hạ Long", "Quảng Ninh"],
        "events_mentioned": ["Lễ hội Du lịch Hạ Long"],
        "festivals_mentioned": ["Lễ hội Hạ Long"],
        "topics": ["du lịch", "lễ hội"],
        "key_entities": ["UBND Quảng Ninh"],
    }
    meta = {"format": "url", "images": [{"local_path": "/tmp/a.jpg", "alt": "Vịnh"}]}
    ex = extract_from_document(structured, meta, doc_id=1, source_id="test")
    labels = {e.label for e in ex.entities}
    assert "Location" in labels
    assert "Event" in labels or "Festival" in labels
    kinds = {m.media_kind for m in ex.media}
    assert "document" in kinds
    assert "image" in kinds


def test_index_and_search(tmp_path: Path, kg_db: Path) -> None:
    store = Storage(kg_db)
    structured = {
        "title": "Khai mạc sự kiện tại Hà Nội",
        "summary": "Sự kiện chuyển đổi số tại Hà Nội.",
        "primary_date": "2026-06-01",
        "locations_mentioned": ["Hà Nội"],
        "events_mentioned": ["Hội nghị chuyển đổi số"],
        "topics": ["chuyển đổi số"],
        "key_entities": ["Phạm Minh Chính"],
    }
    doc_id = store.insert_document(
        source_id="news",
        content_hash="abc",
        raw_text="text",
        structured_json=json.dumps(structured, ensure_ascii=False),
        meta={"format": "url"},
    )
    counts = index_document_kg(kg_db, doc_id, "news", structured, {"format": "url"})
    assert counts["entities"] >= 3
    assert counts["media"] >= 1

    res = structured_search(kg_db, entities="Hà Nội", topics="chuyển đổi số", top_k=10)
    assert res["count"] >= 1
    assert any("Hà Nội" in (r.get("why") or "") or "chuyển" in (r.get("snippet") or "").lower()
               for r in res["results"])


def test_scenes_from_key_facts() -> None:
    scenes = scenes_from_key_facts(
        ["Mở đầu sự kiện", "Phát biểu chính", "Kết thúc"],
        video_ref="vid1",
        title="Hội nghị",
        date="2026-06-01",
        duration_sec=180.0,
    )
    assert len(scenes) == 3
    assert scenes[0].timestamp_sec == 0.0
    assert scenes[1].timestamp_sec == 60.0
    assert scenes[0].props.get("time_label") == "0:00"


def test_alias_resolution(tmp_path: Path, kg_db: Path) -> None:
    kg = KGStorage(kg_db)
    seed_builtin_aliases(kg)
    name, label, nid = resolve_name(kg, "to lam", labels=["Person"])
    assert name == "Tô Lâm"
    assert label == "Person"
    assert nid


def test_unified_search_merges(tmp_path: Path, kg_db: Path) -> None:
    store = Storage(kg_db)
    structured = {
        "title": "Du lịch Hạ Long",
        "summary": "Vịnh Hạ Long Quảng Ninh",
        "locations_mentioned": ["Hạ Long"],
        "topics": ["du lịch"],
    }
    doc_id = store.insert_document(
        source_id="tour",
        content_hash="h2",
        raw_text="x",
        structured_json=json.dumps(structured, ensure_ascii=False),
        meta={},
    )
    index_document_kg(kg_db, doc_id, "tour", structured, {})
    res = unified_search(kg_db, entities="Hạ Long", topics="du lịch", top_k=10, storage=store)
    assert res["count"] >= 1
    assert res.get("graph") is not None


def test_dedupe_merged_collapses_cross_source() -> None:
    # Same article from local KG, document_index and video_kg -> one card.
    results = [
        {"_source": "local", "kind": "document", "doc_id": "d1", "source_id": "s1",
         "title": "Hạ Long", "score": 9},
        {"_source": "document_index", "kind": "document", "source_id": "s1",
         "title": "Hạ Long", "score": 7},
        {"_source": "video_kg", "kind": "document", "doc_id": "d1",
         "title": "Hạ Long", "score": 5},
        # a scene of the same doc collapses into the document card
        {"_source": "local", "kind": "scene", "doc_id": "d1", "title": "Hạ Long",
         "time": "1:20", "score": 4},
        # a different article stays
        {"_source": "local", "kind": "document", "doc_id": "d2", "title": "Đà Nẵng",
         "score": 3},
        # an image of d1 is kept (separate media)
        {"_source": "image_index", "kind": "image", "path": "/img/halong_01.jpg",
         "score": 2},
    ]
    out = _dedupe_merged(results)
    kinds = [(r.get("kind"), r.get("doc_id") or r.get("source_id") or r.get("path")) for r in out]
    assert ("document", "d1") in kinds          # kept once (highest score)
    assert ("document", "d2") in kinds          # different article kept
    assert ("image", "/img/halong_01.jpg") in kinds  # image kept separately
    # only ONE document/scene/video card for d1
    doc_d1 = [r for r in out if (r.get("doc_id") or r.get("source_id")) in ("d1", "s1")
              and r.get("kind") in ("document", "scene", "video")]
    assert len(doc_d1) == 1
    assert doc_d1[0]["score"] == 9              # highest-scoring survivor


def test_rebuild_from_store(tmp_path: Path, kg_db: Path) -> None:
    store = Storage(kg_db)
    store.insert_document(
        source_id="a",
        content_hash="h1",
        raw_text="x",
        structured_json=json.dumps({
            "title": "Lễ hội Đà Nẵng",
            "summary": "Lễ hội pháo hoa",
            "festivals_mentioned": ["Lễ hội pháo hoa Quốc tế"],
            "locations_mentioned": ["Đà Nẵng"],
        }),
        meta={},
    )
    stats = rebuild_kg_from_store(kg_db, store)
    assert stats["docs"] == 1
    kg = KGStorage(kg_db)
    assert kg.stats()["nodes"] >= 2
