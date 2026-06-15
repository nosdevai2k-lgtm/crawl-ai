"""Entity alias registry for person/location matching."""

from __future__ import annotations

from .normalize import ascii_norm, node_id
from .storage import KGStorage

# Alias thủ công phổ biến (mở rộng dần)
_BUILTIN: dict[str, tuple[str, str]] = {
    "to lam": ("Tô Lâm", "Person"),
    "tong bi thu to lam": ("Tô Lâm", "Person"),
    "pham minh chinh": ("Phạm Minh Chính", "Person"),
    "thu tuong pham minh chinh": ("Phạm Minh Chính", "Person"),
    "ha long": ("Vịnh Hạ Long", "Location"),
    "vinh ha long": ("Vịnh Hạ Long", "Location"),
    "ha noi": ("Hà Nội", "Location"),
    "thanh pho ha noi": ("Hà Nội", "Location"),
    "da nang": ("Đà Nẵng", "Location"),
    "hue": ("Huế", "Location"),
    "tp hcm": ("TP. Hồ Chí Minh", "Location"),
    "ho chi minh": ("TP. Hồ Chí Minh", "Location"),
    "sai gon": ("TP. Hồ Chí Minh", "Location"),
}


def seed_builtin_aliases(kg: KGStorage) -> int:
    n = 0
    for alias_norm, (canonical, label) in _BUILTIN.items():
        nid = node_id(label, canonical)
        kg.upsert_node(nid, label, canonical, ascii_norm(canonical))
        kg.register_alias(alias_norm, nid, canonical)
        n += 1
    return n


def register_entity_aliases(kg: KGStorage, label: str, name: str, node_id_str: str) -> None:
    """Register display name + ascii variant as aliases."""
    if label not in ("Person", "Location", "Organization", "Event", "Festival"):
        return
    norm = ascii_norm(name)
    if norm:
        kg.register_alias(norm, node_id_str, name)
    # token subsets for locations: "ha long" from "Vịnh Hạ Long"
    parts = norm.split()
    if len(parts) >= 2:
        kg.register_alias(" ".join(parts[-2:]), node_id_str, name)


def resolve_name(kg: KGStorage, query: str, *, labels: list[str] | None = None) -> tuple[str | None, str | None, str | None]:
    """Return (canonical_name, label, node_id) or (None, None, None)."""
    qnorm = ascii_norm(query)
    if not qnorm:
        return None, None, None
    hit = kg.lookup_alias(qnorm)
    if hit:
        node = kg.get_node(hit["node_id"])
        if node and (not labels or node.label in labels):
            return node.name, node.label, node.id
    nodes = kg.find_nodes(query, labels=labels, limit=1)
    if nodes:
        return nodes[0].name, nodes[0].label, nodes[0].id
    return None, None, None
