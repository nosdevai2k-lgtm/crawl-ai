"""Structured KG search — local + federated Video KG."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .aliases import resolve_name
from .normalize import tokens
from .storage import KGStorage
from ..search_match import compact_why, meaningful_overlap, resolve_search_context
from .video_kg_client import video_kg_structured

_MEDIA_KINDS = {"document", "image", "video", "scene", "both", "any", ""}
_RESOLVE_LABELS = ["Person", "Location", "Event", "Festival", "Topic", "Organization"]


def _parse_semicolon_list(s: str) -> list[str]:
    return [p.strip() for p in re.split(r"[;|,]+", s or "") if p.strip()]


def _resolve_entities(kg: KGStorage, names: list[str]) -> tuple[dict[str, str], dict[str, Any], list[str], set[str]]:
    resolved: dict[str, str] = {}
    detail: dict[str, Any] = {}
    unresolved: list[str] = []
    node_ids: set[str] = set()
    for name in names:
        canon, label, nid = resolve_name(kg, name, labels=_RESOLVE_LABELS)
        if canon and nid:
            resolved[name] = canon
            detail[name] = {"name": canon, "label": label, "approx": canon.lower() != name.lower()}
            node_ids.add(nid)
        else:
            unresolved.append(name)
    return resolved, detail, unresolved, node_ids


def _dedupe_media_results(results: list[dict[str, Any]], *, max_scenes_per_doc: int = 1) -> list[dict[str, Any]]:
    """Giảm scene trùng doc; giữ điểm cao nhất."""
    scene_counts: dict[str, int] = {}
    seen_doc_kind: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for item in results:
        doc_id = str(item.get("doc_id") or "")
        kind = item.get("kind") or ""
        if kind == "scene" and doc_id:
            n = scene_counts.get(doc_id, 0)
            if n >= max_scenes_per_doc:
                continue
            scene_counts[doc_id] = n + 1
        key = (doc_id, kind)
        if kind == "document" and key in seen_doc_kind:
            continue
        seen_doc_kind.add(key)
        out.append(item)
    return out


def structured_search(
    db_path: Path,
    *,
    entities: str = "",
    topics: str = "",
    has_people: str = "any",
    media: str = "both",
    top_k: int = 30,
) -> dict[str, Any]:
    from .normalize import ascii_norm

    kg = KGStorage(db_path)
    ctx = resolve_search_context(db_path, entities=entities, topics=topics)
    entity_names = ctx["entity_names"]
    topic_names = ctx["topic_names"]
    resolved_map = {r["input"]: r["canonical"] for r in ctx["resolved"]}
    resolved_detail = {
        r["input"]: {
            "name": r["canonical"],
            "label": r["label"],
            "approx": ascii_norm(r["input"]) != ascii_norm(r["canonical"]),
        }
        for r in ctx["resolved"]
    }
    unresolved = ctx["unresolved"]
    node_ids = ctx["node_ids"]
    query_tokens = ctx["query_tokens"]
    topic_tokens = ctx["topic_tokens"]
    location_resolved = [r for r in ctx["resolved"] if r["label"] == "Location"]
    person_resolved = [r for r in ctx["resolved"] if r["label"] == "Person"]

    want_media = media if media in _MEDIA_KINDS else "both"
    if want_media in ("both", "any", ""):
        kinds = {"document", "image", "video", "scene"}
    else:
        kinds = {want_media}

    results: list[dict[str, Any]] = []
    with kg._connect() as conn:  # noqa: SLF001
        rows = conn.execute(
            """
            SELECT m.id, m.doc_id, m.source_id, m.media_kind, m.media_ref, m.title, m.snippet, m.date,
                   m.timestamp_sec, m.props,
                   GROUP_CONCAT(n.name, '; ') AS entity_names,
                   GROUP_CONCAT(n.label, '; ') AS entity_labels,
                   GROUP_CONCAT(me.why, '; ') AS whys,
                   GROUP_CONCAT(me.node_id, ';') AS linked_node_ids
            FROM kg_media m
            LEFT JOIN kg_media_entities me ON me.media_id = m.id
            LEFT JOIN kg_nodes n ON n.id = me.node_id
            GROUP BY m.id
            ORDER BY m.date DESC, m.id DESC
            LIMIT 2000
            """
        ).fetchall()

    for r in rows:
        if r["media_kind"] not in kinds:
            continue
        title = r["title"] or ""
        snippet = r["snippet"] or ""
        blob_tokens = tokens(f"{title} {snippet} {r['entity_names'] or ''}")
        linked = {x for x in (r["linked_node_ids"] or "").split(";") if x}
        entity_hit = bool(node_ids and linked & node_ids)
        rel = meaningful_overlap(query_tokens, blob_tokens)
        if topic_tokens:
            rel += meaningful_overlap(topic_tokens, blob_tokens) * 2

        if node_ids:
            if entity_hit:
                rel += 8
            elif query_tokens and rel < 2:
                continue
        elif topic_tokens:
            if rel < 2:
                continue
        elif query_tokens and rel == 0:
            continue

        # Địa điểm đã resolve: bắt buộc liên kết node hoặc token địa danh trong nội dung
        if location_resolved and not person_resolved:
            loc_tokens: set[str] = set()
            for loc in location_resolved:
                loc_tokens |= loc["tokens"]
            loc_hit = entity_hit or meaningful_overlap(loc_tokens, blob_tokens) >= 2
            if not loc_hit:
                continue

        if person_resolved and not entity_hit and meaningful_overlap(
            {t for p in person_resolved for t in p["tokens"]}, blob_tokens
        ) < 2:
            continue

        min_score = 3 if (node_ids or topic_tokens) else 1
        if rel < min_score:
            continue

        labels = (r["entity_labels"] or "").split("; ")
        has_person = any(lbl == "Person" for lbl in labels)
        if has_people == "yes" and not has_person:
            continue
        if has_people == "no" and has_person:
            continue

        why_parts = []
        if r["whys"]:
            why_parts.append(r["whys"])
        if entity_names:
            why_parts.append("khớp: " + ", ".join(entity_names))
        if topic_names:
            why_parts.append("chủ đề: " + ", ".join(topic_names))

        props = {}
        try:
            import json
            props = json.loads(r["props"] or "{}")
        except Exception:
            props = {}

        why_raw = " · ".join(p for p in why_parts if p) or "khớp từ khoá"
        item: dict[str, Any] = {
            "kind": r["media_kind"],
            "doc_id": r["doc_id"],
            "source_id": r["source_id"],
            "media_ref": r["media_ref"],
            "title": title,
            "date": r["date"] or "",
            "snippet": snippet[:300],
            "why": compact_why(why_raw),
            "score": rel,
            "_has_person": has_person,
            "_source": "local",
        }
        if r["media_kind"] == "scene" and r["timestamp_sec"] is not None:
            sec = int(r["timestamp_sec"])
            item["time"] = props.get("time_label") or f"{sec // 60}:{sec % 60:02d}"
            item["t"] = r["timestamp_sec"]
            if props.get("end_sec") is not None:
                item["end"] = props["end_sec"]
        if r["media_kind"] == "video":
            item["video_ref"] = r["media_ref"]
        results.append(item)

    results.sort(key=lambda x: (x.get("score", 0), x.get("date", "")), reverse=True)
    results = _dedupe_media_results(results)[:top_k]

    from .overview import neighbors_vis

    graph_nodes: list[dict] = []
    graph_edges: list[dict] = []
    seen_n: set[str] = set()
    seen_e: set[str] = set()
    seed_ids = set(node_ids)
    for name in list(resolved_map.values()):
        _, _, nid = resolve_name(kg, name)
        if nid:
            seed_ids.add(nid)
    for nid in seed_ids:
        g = neighbors_vis(kg, nid, limit=25)
        for n in g.get("nodes") or []:
            if n["id"] not in seen_n:
                seen_n.add(n["id"])
                graph_nodes.append(n)
        for e in g.get("edges") or []:
            eid = f"{e.get('from')}|{e.get('to')}"
            if eid not in seen_e:
                seen_e.add(eid)
                graph_edges.append(e)
    if not graph_nodes:
        from .overview import build_overview_graph
        return_graph = build_overview_graph(kg, limit_nodes=35)
        graph_nodes = return_graph.get("nodes") or []
        graph_edges = return_graph.get("edges") or []

    return {
        "query": "; ".join(entity_names + topic_names),
        "intent": "structured",
        "count": len(results),
        "results": results,
        "notes": {
            "resolved": resolved_map,
            "resolved_detail": resolved_detail,
            "unresolved": unresolved,
            "entities": entity_names,
            "topics": topic_names,
            "suggested_presets": ctx["suggested_presets"],
        },
        "stats": kg.stats(),
        "graph": {"nodes": graph_nodes[:50], "edges": graph_edges[:80]},
        "_source": "local",
    }


def federated_search(
    db_path: Path,
    *,
    entities: str = "",
    topics: str = "",
    has_people: str = "any",
    media: str = "both",
    top_k: int = 30,
    source: str = "both",
    video_kg_url: str = "",
) -> dict[str, Any]:
    """source: local | video_kg | both"""
    src = (source or "both").lower()
    local_res: dict[str, Any] = {"count": 0, "results": []}
    remote_res: dict[str, Any] = {"count": 0, "results": []}

    if src in ("local", "both"):
        local_res = structured_search(
            db_path, entities=entities, topics=topics,
            has_people=has_people, media=media, top_k=top_k,
        )
    if src in ("video_kg", "both") and video_kg_url:
        remote_res = video_kg_structured(
            video_kg_url, entities=entities, topics=topics,
            has_people=has_people, media=media, top_k=top_k,
        )

    merged: list[dict[str, Any]] = []
    if src == "local":
        merged = list(local_res.get("results") or [])
    elif src == "video_kg":
        merged = list(remote_res.get("results") or [])
    else:
        half = max(top_k // 2, 5)
        merged = (local_res.get("results") or [])[:half] + (remote_res.get("results") or [])[:half]
        merged.sort(key=lambda x: x.get("score", 0), reverse=True)

    return {
        "query": local_res.get("query") or remote_res.get("query") or "",
        "intent": "federated",
        "count": len(merged[:top_k]),
        "results": merged[:top_k],
        "local": local_res,
        "video_kg": remote_res,
        "notes": local_res.get("notes") or remote_res.get("notes") or {},
        "stats": {
            "local": local_res.get("stats"),
            "video_kg": remote_res.get("stats"),
        },
        "graph": local_res.get("graph") or {"nodes": [], "edges": []},
        "_source": src,
    }


SAMPLE_QUERIES = [
    {"entities": "Hạ Long", "topics": "du lịch", "label": "🏞️ Hạ Long"},
    {"entities": "Hà Nội", "topics": "", "label": "📍 Hà Nội"},
    {"entities": "", "topics": "lễ hội", "label": "🎌 lễ hội"},
    {"entities": "Phạm Minh Chính", "topics": "", "label": "👤 lãnh đạo"},
    {"entities": "", "topics": "nhà ở xã hội", "label": "🏠 NƠXH"},
    {"entities": "", "topics": "chuyển đổi số", "label": "💻 CĐS"},
]
