"""Default overview subgraph (like Video KG /api/overview)."""

from __future__ import annotations

from .graph_format import to_vis_graph
from .storage import KGStorage


def build_overview_graph(kg: KGStorage, *, limit_nodes: int = 40) -> dict[str, list]:
    """Sample well-connected entity nodes + edges between them."""
    with kg._connect() as conn:  # noqa: SLF001
        rows = conn.execute(
            """
            SELECT n.id, n.label, n.name, COUNT(me.id) AS deg
            FROM kg_nodes n
            LEFT JOIN kg_media_entities me ON me.node_id = n.id
            WHERE n.label IN ('Person','Location','Topic','Event','Festival','Organization','Document')
            GROUP BY n.id
            ORDER BY deg DESC, n.updated_at DESC
            LIMIT ?
            """,
            (limit_nodes,),
        ).fetchall()
        if not rows:
            rows = conn.execute(
                "SELECT id, label, name FROM kg_nodes ORDER BY updated_at DESC LIMIT ?",
                (limit_nodes,),
            ).fetchall()
        node_ids = {r["id"] for r in rows}
        edge_rows = conn.execute(
            "SELECT src_id, dst_id, rel_type FROM kg_edges ORDER BY weight DESC LIMIT 120"
        ).fetchall()

    nodes = [{"id": r["id"], "label": r["label"], "name": r["name"]} for r in rows]
    edges = [
        {"from": e["src_id"], "to": e["dst_id"], "rel": e["rel_type"]}
        for e in edge_rows
        if e["src_id"] in node_ids and e["dst_id"] in node_ids
    ]
    return to_vis_graph(nodes, edges)


def neighbors_vis(kg: KGStorage, node_id: str, limit: int = 30) -> dict:
    raw = kg.neighbors(node_id, limit=limit)
    return to_vis_graph(raw.get("nodes") or [], raw.get("edges") or [])
