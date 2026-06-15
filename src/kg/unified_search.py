"""Unified search: KG + image presets + documents + Video KG."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.search import PRESETS, search_images
from src.search_match import normalize_score, resolve_search_context

from .graph_format import legend_from_stats, to_vis_graph
from .overview import build_overview_graph, neighbors_vis
from .search import federated_search
from .storage import KGStorage


def _img_to_card(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "image",
        "video_name": it.get("slug") or Path(it.get("path", "")).stem,
        "title": it.get("slug", ""),
        "path": it.get("path", ""),
        "date": "",
        "evidence": f"{it.get('w', '?')}×{it.get('h', '?')} · {it.get('why', '')}",
        "why": f"ảnh · score {it.get('score', 0)}",
        "score": normalize_score(it.get("score", 0), src="image_index"),
        "_source": "image_index",
        "_has_person": (it.get("group") or "") == "human",
        "display_kind": "image",
    }


def _local_to_card(it: dict[str, Any]) -> dict[str, Any]:
    kind = it.get("kind", "document")
    card = dict(it)
    card["display_kind"] = kind
    card["score"] = normalize_score(it.get("score", 0), src="local")
    if kind == "scene":
        card["video_name"] = it.get("title") or it.get("media_ref")
        card["evidence"] = it.get("snippet") or ""
        card["verify"] = "Phát đúng cảnh — xem/nghe để xác minh"
    elif kind == "document":
        card["video_name"] = it.get("title") or f"doc:{it.get('doc_id')}"
        card["evidence"] = it.get("snippet") or ""
    elif kind == "image":
        card["video_name"] = it.get("title") or Path(it.get("media_ref", "")).name
        card["path"] = it.get("media_ref")
        card["evidence"] = it.get("snippet") or ""
    elif kind == "video":
        card["video_name"] = it.get("title") or it.get("media_ref")
        card["evidence"] = it.get("snippet") or ""
    return card


def _norm_title(s: Any) -> str:
    """Lowercase + collapse whitespace so titles that differ only in spacing/case
    collapse together for dedup."""
    return " ".join(str(s or "").lower().split())


def _content_keys(it: dict[str, Any]) -> set[str]:
    """All source-independent identifiers for a result. The same article from
    local KG (has doc_id+source_id), document_index (source_id only) and video_kg
    must collapse, so we match on ANY shared identifier rather than `_source`."""
    kind = it.get("display_kind") or it.get("kind") or ""
    if kind == "image":
        # Collapse to ONE representative per folder/entity (e.g. one photo per
        # person), not per file — a mixed result list shouldn't show 10 near
        # identical portraits of the same person.
        ref = it.get("path") or it.get("media_ref") or ""
        p = Path(str(ref))
        folder = p.parent.name if p.parent.name not in ("", ".", "images") else ""
        base = folder or _norm_title(it.get("title") or it.get("video_name")) or p.name.lower()
        return {"img:" + base}
    keys: set[str] = set()
    if it.get("doc_id"):
        keys.add(f"doc:{it['doc_id']}")
    if it.get("source_id"):
        keys.add(f"src:{it['source_id']}")
    title = _norm_title(it.get("video_name") or it.get("title"))
    if title:
        keys.add(f"ttl:{title}")
    if not keys and it.get("media_ref"):
        keys.add(f"ref:{it['media_ref']}")
    return keys or {"unknown"}


def _dedupe_merged(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse duplicates regardless of which source produced them.

    Results arrive sorted by score (desc), so the first time we see a piece of
    content we keep the highest-scoring card. Two rules:
      * same identifier + same kind + same scene-time  -> exact duplicate
      * a doc that already appeared as a document/scene/video card is not shown
        again under another of those kinds (keeps one "best" card per article);
        images stay separate so a doc and its photos can both surface.
    """
    seen: set[str] = set()
    seen_doc: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in results:
        kind = it.get("display_kind") or it.get("kind") or ""
        kind = "document" if kind in ("doc", "document") else kind
        keys = _content_keys(it)
        time_s = str(it.get("time") or "")
        exact = {f"{k}|{kind}|{time_s}" for k in keys}
        if exact & seen:
            continue
        is_doc = kind in ("document", "scene", "video") and any(
            k.startswith(("doc:", "src:", "ttl:")) for k in keys
        )
        if is_doc and (keys & seen_doc):
            continue
        if is_doc:
            seen_doc |= keys
        seen |= exact
        out.append(it)
    return out


def unified_search(
    db_path: Path,
    *,
    entities: str = "",
    topics: str = "",
    image_query: str = "",
    image_preset: str = "tong_hop",
    has_people: str = "any",
    media: str = "both",
    top_k: int = 30,
    source: str = "both",
    video_kg_url: str = "",
    storage: Any = None,
    image_tools: dict[str, str] | None = None,
    include_images: bool = True,
) -> dict[str, Any]:
    """Search across KG (local/video_kg) + image index + docs."""
    image_tools = image_tools or {}
    ctx = resolve_search_context(db_path, entities=entities, topics=topics)
    suggested = ctx["primary_preset"]
    if image_preset in PRESETS and image_preset != "tong_hop":
        preset = image_preset
    else:
        preset = suggested

    kg_res = federated_search(
        db_path,
        entities=entities,
        topics=topics,
        has_people=has_people,
        media=media,
        top_k=top_k,
        source=source,
        video_kg_url=video_kg_url,
    )

    merged: list[dict[str, Any]] = []
    for it in kg_res.get("results") or []:
        merged.append(_local_to_card(it))

    # Image search: query ảnh rõ ràng, hoặc entity Person/Location/Event
    img_q = image_query.strip()
    if not img_q:
        if ctx["entity_names"]:
            img_q = "; ".join(ctx["entity_names"])
        elif ctx["topic_names"]:
            img_q = "; ".join(ctx["topic_names"])

    want_images = include_images and img_q and media in ("both", "image", "any", "")
    if want_images:
        tools = dict(image_tools)
        for r in ctx["resolved"]:
            if r["label"] == "Location" and not tools.get("location"):
                tools["location"] = r["canonical"]
            if r["label"] == "Person" and not tools.get("group"):
                tools["group"] = "human"
        if entities and not tools.get("location"):
            tools["location"] = entities.split(";")[0].strip()

        img_res = search_images(
            img_q,
            preset,
            tools=tools,
            top_k=min(top_k, 24),
            storage=storage,
            db_path=db_path,
        )
        for it in img_res.get("results") or []:
            if it.get("kind") == "doc":
                merged.append({
                    "kind": "document",
                    "display_kind": "document",
                    "source_id": it.get("source_id"),
                    "video_name": it.get("title") or it.get("source_id"),
                    "title": it.get("title") or it.get("source_id"),
                    "date": it.get("date", ""),
                    "evidence": it.get("snippet", ""),
                    "why": f"tin tức · score {it.get('score', 0)}",
                    "score": normalize_score(it.get("score", 0), src="document_index"),
                    "_source": "document_index",
                })
            elif it.get("kind") == "image":
                merged.append(_img_to_card(it))

    merged.sort(key=lambda x: float(x.get("score", 0)), reverse=True)
    merged = _dedupe_merged(merged)[:top_k]

    kg = KGStorage(db_path)
    stats = kg.stats()
    graph = kg_res.get("graph") or {"nodes": [], "edges": []}
    if not graph.get("nodes"):
        graph = build_overview_graph(kg, limit_nodes=40)
    vkg = kg_res.get("video_kg") or {}
    vkg_graph = vkg.get("graph") or {}
    if vkg_graph.get("nodes"):
        seen = {n["id"] for n in graph.get("nodes") or []}
        for n in vkg_graph.get("nodes") or []:
            if n.get("id") and n["id"] not in seen:
                graph.setdefault("nodes", []).append(n)
                seen.add(n["id"])
        graph.setdefault("edges", []).extend(vkg_graph.get("edges") or [])

    neighbors: dict[str, Any] = {}
    for n in graph.get("nodes") or []:
        nid = n.get("id")
        if nid:
            neighbors[nid] = neighbors_vis(kg, nid, limit=30)

    notes = dict(kg_res.get("notes") or {})
    notes["suggested_presets"] = ctx["suggested_presets"]
    notes["image_preset_used"] = preset

    return {
        "query": kg_res.get("query") or img_q,
        "intent": "unified",
        "count": len(merged),
        "results": merged,
        "notes": notes,
        "stats": {
            "local": stats,
            "video_kg": (kg_res.get("video_kg") or {}).get("stats"),
            "legend": legend_from_stats(stats.get("by_label") or {}),
        },
        "graph": (
            graph
            if (graph.get("nodes") and graph["nodes"][0].get("group"))
            else to_vis_graph(graph.get("nodes") or [], graph.get("edges") or [])
        ),
        "neighbors": neighbors,
        "local": kg_res.get("local"),
        "video_kg": kg_res.get("video_kg"),
        "_source": source,
    }
