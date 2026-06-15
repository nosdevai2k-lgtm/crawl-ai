"""Index crawled documents into the knowledge graph."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .aliases import register_entity_aliases, seed_builtin_aliases
from .extract import extract_from_document
from .normalize import ascii_norm
from .storage import KGStorage

_log = logging.getLogger(__name__)


def get_kg_storage(db_path: Path) -> KGStorage:
    return KGStorage(db_path)


def index_document_kg(
    db_path: Path,
    doc_id: str | int,
    source_id: str,
    structured: dict[str, Any] | str,
    meta: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Index one document. Returns counts {entities, media, edges}."""
    if isinstance(structured, str):
        try:
            structured = json.loads(structured or "{}")
        except json.JSONDecodeError:
            structured = {}
    meta = meta or {}
    kg = get_kg_storage(db_path)
    seed_builtin_aliases(kg)
    kg.delete_doc_index(str(doc_id))
    extracted = extract_from_document(structured, meta, doc_id=doc_id, source_id=source_id)

    doc_node_id = f"document:{doc_id}"
    kg.upsert_node(
        doc_node_id, "Document",
        extracted.doc_title or f"doc:{doc_id}",
        ascii_norm(extracted.doc_title or str(doc_id)),
        {"source_id": source_id, "date": extracted.doc_date},
    )

    entity_ids: list[str] = []
    for ent in extracted.entities:
        kg.upsert_node(ent.id, ent.label, ent.name, ascii_norm(ent.name))
        register_entity_aliases(kg, ent.label, ent.name, ent.id)
        kg.add_edge(doc_node_id, ent.id, "MENTIONS", props={"why": ent.why})
        entity_ids.append(ent.id)

    # cross-link locations <-> events in same doc
    locs = [e.id for e in extracted.entities if e.label == "Location"]
    evs = [e.id for e in extracted.entities if e.label in ("Event", "Festival")]
    persons = [e.id for e in extracted.entities if e.label == "Person"]
    for lid in locs:
        for eid in evs:
            kg.add_edge(eid, lid, "LOCATED_IN", weight=0.5)
    # link people to events/festivals they co-occur with in the same document,
    # so "which event is this person related to" is a real graph relationship.
    for pid in persons:
        for eid in evs:
            kg.add_edge(pid, eid, "ATTENDED", weight=0.6)

    media_count = 0
    for m in extracted.media:
        mid = kg.upsert_media(
            doc_id=str(doc_id),
            source_id=source_id,
            media_kind=m.media_kind,
            media_ref=m.media_ref,
            title=m.title,
            snippet=m.snippet,
            date=m.date,
            timestamp_sec=m.timestamp_sec,
            props=m.props,
        )
        media_count += 1
        media_node_id = f"media:{mid}"
        kg.upsert_node(media_node_id, m.media_kind.capitalize(), m.title or m.media_ref, ascii_norm(m.title or m.media_ref))
        kg.add_edge(doc_node_id, media_node_id, "HAS_MEDIA", props={"kind": m.media_kind})
        for eid in entity_ids:
            why = next((e.why for e in extracted.entities if e.id == eid), "")
            kg.link_media_entity(mid, eid, why=why)

    return {"entities": len(extracted.entities), "media": media_count, "edges": len(entity_ids)}


def rebuild_kg_from_store(db_path: Path, store: Any, *, limit: int = 5000) -> dict[str, int]:
    """Re-index all recent documents from document store."""
    rows = store.list_recent(limit=limit)
    total = {"docs": 0, "entities": 0, "media": 0}
    for row in rows:
        try:
            structured = json.loads(row.structured_json or "{}")
        except json.JSONDecodeError:
            structured = {}
        meta = row.meta if isinstance(row.meta, dict) else {}
        counts = index_document_kg(db_path, row.id, row.source_id, structured, meta)
        total["docs"] += 1
        total["entities"] += counts["entities"]
        total["media"] += counts["media"]
    _log.info("KG rebuild: %s", total)
    return total
