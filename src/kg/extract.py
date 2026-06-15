"""Extract KG entities from structured JSON + crawl meta."""

from __future__ import annotations

from typing import Any

from .classify import classify_entity
from .models import ExtractedEntity, ExtractedMedia, ExtractionResult
from .normalize import node_id
from .scenes import scenes_for_video, scenes_from_key_facts


def _add_entity(out: list[ExtractedEntity], seen: set[str], name: str, label: str, why: str) -> None:
    n = (name or "").strip()
    if not n:
        return
    nid = node_id(label, n)
    if nid in seen:
        return
    seen.add(nid)
    out.append(ExtractedEntity(id=nid, label=label, name=n, why=why))


def extract_from_document(
    structured: dict[str, Any],
    meta: dict[str, Any],
    *,
    doc_id: str | int,
    source_id: str,
) -> ExtractionResult:
    res = ExtractionResult(
        doc_title=(structured.get("title") or "").strip(),
        doc_summary=(structured.get("summary") or "").strip(),
        doc_date=(structured.get("primary_date") or "").strip(),
    )
    seen: set[str] = set()
    entities = res.entities
    topic_blob = " ".join(structured.get("topics") or []) + " " + (structured.get("primary_topic") or "")

    for loc in structured.get("locations_mentioned") or []:
        _add_entity(entities, seen, str(loc), "Location", "địa điểm trong bài")

    for ev in structured.get("events_mentioned") or []:
        _add_entity(entities, seen, str(ev), "Event", "sự kiện trong bài")

    for fest in structured.get("festivals_mentioned") or []:
        _add_entity(entities, seen, str(fest), "Festival", "lễ hội trong bài")

    for topic in structured.get("topics") or []:
        _add_entity(entities, seen, str(topic), "Topic", "chủ đề")

    pt = (structured.get("primary_topic") or "").strip()
    if pt:
        _add_entity(entities, seen, pt, "Topic", "chủ đề chính")

    for ent in structured.get("key_entities") or []:
        label = classify_entity(str(ent), topic_hint=topic_blob)
        _add_entity(entities, seen, str(ent), label, "thực thể chính")

    for person in structured.get("persons") or []:
        if isinstance(person, dict):
            name = (person.get("full_name") or "").strip()
            if name:
                _add_entity(entities, seen, name, "Person", "nhân vật trích xuất")
                org = (person.get("organization") or "").strip()
                if org:
                    _add_entity(entities, seen, org, "Organization", "tổ chức liên quan")

    # Document media node
    res.media.append(ExtractedMedia(
        media_kind="document",
        media_ref=str(doc_id),
        title=res.doc_title or source_id,
        snippet=res.doc_summary[:500],
        date=res.doc_date,
        props={"source_id": source_id, "format": meta.get("format", "")},
    ))

    for i, img in enumerate(meta.get("images") or []):
        if not isinstance(img, dict):
            continue
        path = img.get("local_path") or img.get("path") or img.get("url") or f"img:{i}"
        res.media.append(ExtractedMedia(
            media_kind="image",
            media_ref=str(path),
            title=img.get("alt") or img.get("name") or res.doc_title,
            snippet=img.get("caption") or res.doc_summary[:200],
            date=res.doc_date,
            props={"source_id": source_id, **{k: v for k, v in img.items() if k in ("url", "w", "h")}},
        ))

    for i, vid in enumerate(meta.get("videos") or []):
        if not isinstance(vid, dict):
            continue
        ref = vid.get("file_path") or vid.get("url") or vid.get("id") or f"vid:{i}"
        res.media.append(ExtractedMedia(
            media_kind="video",
            media_ref=str(ref),
            title=vid.get("title") or res.doc_title,
            snippet=(vid.get("description") or res.doc_summary)[:500],
            date=vid.get("upload_date") or res.doc_date,
            props={
                "source_id": source_id,
                "channel": vid.get("channel", ""),
                "duration": vid.get("duration"),
                "video_id": vid.get("id", ""),
            },
        ))
        res.media.extend(scenes_for_video(vid, structured, source_id=source_id))

    # Scenes từ key_facts cho document (không có video)
    if not meta.get("videos") and structured.get("key_facts"):
        doc_ref = f"doc:{doc_id}"
        res.media.extend(scenes_from_key_facts(
            [str(x) for x in structured.get("key_facts") or []],
            video_ref=doc_ref,
            title=res.doc_title or source_id,
            date=res.doc_date,
            duration_sec=None,
            base_props={"source_id": source_id, "parent_doc": str(doc_id)},
        ))

    # Image index folders linked as scenes for location/event presets
    for slug, info in (meta.get("image_index") or {}).items():
        if not isinstance(info, dict):
            continue
        res.media.append(ExtractedMedia(
            media_kind="image",
            media_ref=str(slug),
            title=info.get("name") or slug,
            snippet=info.get("group") or "",
            date=res.doc_date,
            props={"group": info.get("group", ""), "from_index": True},
        ))

    return res
