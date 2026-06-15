"""Convert KG data to vis-network graph (Video KG compatible)."""

from __future__ import annotations

from typing import Any

COLORS = {
    "Person": "#4f9dff",
    "Title": "#f4c542",
    "Topic": "#c98bff",
    "Organization": "#ff7a59",
    "Location": "#36c275",
    "Video": "#ff5d8f",
    "Scene": "#5bd1d7",
    "TextMention": "#9aa4b2",
    "Event": "#f4c542",
    "Festival": "#e879f9",
    "Document": "#94a3b8",
    "Image": "#22d3ee",
    "Node": "#888888",
}


def to_vis_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    vis_nodes = []
    for n in nodes:
        grp = n.get("label") or n.get("group") or "Node"
        vis_nodes.append({
            "id": n["id"],
            "label": (n.get("name") or n.get("label") or n["id"])[:40],
            "group": grp,
            "vid": n.get("vid"),
            "t": n.get("t"),
            "end": n.get("end"),
        })
    vis_edges = []
    for e in edges:
        vis_edges.append({
            "from": e.get("from") or e.get("src_id"),
            "to": e.get("to") or e.get("dst_id"),
            "label": (e.get("rel") or e.get("rel_type") or "")[:20],
        })
    return {"nodes": vis_nodes, "edges": vis_edges}


def legend_from_stats(by_label: dict[str, int]) -> list[dict[str, Any]]:
    order = ["Scene", "Person", "Location", "Topic", "Event", "Festival", "Organization", "Video", "Document", "Image"]
    items = []
    for lbl in order:
        if lbl in by_label:
            items.append({"label": lbl, "count": by_label[lbl], "color": COLORS.get(lbl, COLORS["Node"])})
    for lbl, cnt in by_label.items():
        if lbl not in order:
            items.append({"label": lbl, "count": cnt, "color": COLORS.get(lbl, COLORS["Node"])})
    return items
