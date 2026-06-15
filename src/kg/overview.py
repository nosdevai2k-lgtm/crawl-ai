"""Default overview subgraph (like Video KG /api/overview)."""

from __future__ import annotations

from .graph_format import to_vis_graph
from .storage import KGStorage


def build_overview_graph(kg: KGStorage, *, limit_nodes: int = 40) -> dict[str, list]:
    """Edge-driven overview: take the strongest relations and the nodes they
    connect, so the default graph is actually connected (not a scattered cloud)
    and every node has neighbours to expand."""
    _DISPLAY = ("Person", "Location", "Topic", "Event", "Festival", "Organization", "Document")
    with kg._connect() as conn:  # noqa: SLF001
        placeholders = ",".join("?" * len(_DISPLAY))
        # Strongest edges between two displayable entity nodes (skip media links).
        edge_rows = conn.execute(
            f"""
            SELECT e.src_id, e.dst_id, e.rel_type, e.weight
            FROM kg_edges e
            JOIN kg_nodes a ON a.id = e.src_id AND a.label IN ({placeholders})
            JOIN kg_nodes b ON b.id = e.dst_id AND b.label IN ({placeholders})
            ORDER BY e.weight DESC, e.id DESC
            LIMIT ?
            """,
            (*_DISPLAY, *_DISPLAY, max(limit_nodes * 3, 120)),
        ).fetchall()

        node_ids: list[str] = []
        seen: set[str] = set()
        edges: list[dict] = []
        for e in edge_rows:
            if len(seen) >= limit_nodes and e["src_id"] not in seen and e["dst_id"] not in seen:
                continue
            for nid in (e["src_id"], e["dst_id"]):
                if nid not in seen and len(seen) < limit_nodes:
                    seen.add(nid)
                    node_ids.append(nid)
            if e["src_id"] in seen and e["dst_id"] in seen:
                edges.append({"from": e["src_id"], "to": e["dst_id"], "rel": e["rel_type"]})

        if node_ids:
            sel = ",".join("?" * len(node_ids))
            rows = conn.execute(
                f"SELECT id, label, name FROM kg_nodes WHERE id IN ({sel})", node_ids
            ).fetchall()
        else:
            # Fallback: no entity-entity edges at all — show most-recent nodes.
            rows = conn.execute(
                f"""
                SELECT id, label, name FROM kg_nodes
                WHERE label IN ({placeholders})
                ORDER BY updated_at DESC LIMIT ?
                """,
                (*_DISPLAY, limit_nodes),
            ).fetchall()
            edges = []

    nodes = [{"id": r["id"], "label": r["label"], "name": r["name"]} for r in rows]
    return to_vis_graph(nodes, edges)


def neighbors_vis(kg: KGStorage, node_id: str, limit: int = 30) -> dict:
    raw = kg.neighbors(node_id, limit=limit)
    return to_vis_graph(raw.get("nodes") or [], raw.get("edges") or [])
