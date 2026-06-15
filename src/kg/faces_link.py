"""Link harvested face folders (data/images/human/<slug>) to KG Person nodes.

This is the *structural* layer of face<->event matching: it connects each
harvested portrait folder to the Person node that documents also create (same
stable node_id / alias), so the graph gains  Person --HAS_FACE--> FaceSet  edges.
Combined with the Person --ATTENDED--> Event edges added by the indexer, a
person's faces and their events become reachable in one graph.

No biometrics here — matching is by name/slug. The optional face-recognition
layer (src/faces.py) verifies and enriches these links.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .aliases import register_entity_aliases, resolve_name, seed_builtin_aliases
from .normalize import ascii_norm, node_id
from .storage import KGStorage

_IMG_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _primary_name(display: str) -> str:
    """names.json stores 'Tô Lâm To Lam' = vi + en transliteration (same word
    count). If the second half is the ASCII form of the first half, return the
    Vietnamese half; otherwise return the string unchanged."""
    display = (display or "").strip()
    words = display.split()
    if len(words) >= 2 and len(words) % 2 == 0:
        half = len(words) // 2
        first = " ".join(words[:half])
        second = " ".join(words[half:])
        if ascii_norm(first) == ascii_norm(second):
            return first
    return display


def _count_images(folder: Path) -> int:
    if not folder.is_dir():
        return 0
    return sum(1 for f in folder.iterdir() if f.suffix.lower() in _IMG_SUFFIXES)


def link_faces_to_persons(
    db_path: Path,
    images_root: Path | None = None,
) -> dict[str, Any]:
    """Create Person --HAS_FACE--> FaceSet edges for every harvested face folder.

    Resolves the folder to an existing Person node (via alias/slug) when possible
    so it merges with people mentioned in documents; otherwise creates the Person
    node. Returns {linked, created, folders}."""
    images_root = images_root or Path("data/images")
    kg = KGStorage(db_path)
    seed_builtin_aliases(kg)

    names_file = images_root / "names.json"
    names: dict[str, str] = {}
    if names_file.is_file():
        try:
            names = json.loads(names_file.read_text(encoding="utf-8"))
        except Exception:
            names = {}

    linked = 0
    created = 0
    folders = 0
    for rel_key, display in names.items():
        if not rel_key.startswith("human/"):
            continue
        slug = rel_key.split("/", 1)[1]
        folder = images_root / rel_key
        n_imgs = _count_images(folder)
        if n_imgs == 0:
            continue
        folders += 1

        # 1) resolve to an existing Person node via the slug ("to-lam" -> "to lam")
        cand = slug.replace("-", " ").replace("_", " ").strip()
        name, label, nid = resolve_name(kg, cand, labels=["Person"])
        if not nid:
            # 2) create a Person node from the display name
            primary = _primary_name(display) or cand.title()
            nid = node_id("Person", primary)
            kg.upsert_node(nid, "Person", primary, ascii_norm(primary))
            register_entity_aliases(kg, "Person", primary, nid)
            name = primary
            created += 1

        face_id = f"faceset:{slug}"
        kg.upsert_node(
            face_id, "Image", f"{name} — ảnh", ascii_norm(name),
            {"folder": rel_key, "count": n_imgs, "kind": "faceset"},
        )
        kg.add_edge(nid, face_id, "HAS_FACE", weight=1.0,
                    props={"folder": rel_key, "count": n_imgs})
        linked += 1

    return {"linked": linked, "created": created, "folders": folders}


def person_events(kg: KGStorage, person_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """Events/festivals a person is linked to (ATTENDED) or co-mentioned with."""
    with kg._connect() as conn:  # noqa: SLF001
        rows = conn.execute(
            """
            SELECT n.id, n.name, n.label, e.rel_type
            FROM kg_edges e JOIN kg_nodes n ON n.id = e.dst_id
            WHERE e.src_id = ? AND n.label IN ('Event','Festival')
            ORDER BY e.weight DESC LIMIT ?
            """,
            (person_id, limit),
        ).fetchall()
    return [{"id": r["id"], "name": r["name"], "label": r["label"], "via": r["rel_type"]} for r in rows]


def match_face_to_events(
    db_path: Path,
    image_bytes: bytes,
    images_root: Path | None = None,
    *,
    min_score: float = 0.363,
) -> dict[str, Any]:
    """Identify the face in an image and return the related events from the KG.

    Returns {available, match:{slug,name,score}|None, person_id, events:[...]}.
    `available` is False if face recognition (opencv + models) is not installed."""
    from .. import faces

    if not faces.available():
        return {"available": False, "match": None, "person_id": None, "events": []}

    refs = faces.build_references(images_root)
    match = faces.identify(image_bytes, refs, min_score=min_score)
    if not match:
        return {"available": True, "match": None, "person_id": None, "events": []}

    kg = KGStorage(db_path)
    seed_builtin_aliases(kg)
    # resolve identified person -> KG Person node (same path as link_faces)
    slug = match["slug"]
    cand = slug.replace("-", " ").replace("_", " ").strip()
    _, _, nid = resolve_name(kg, cand, labels=["Person"])
    if not nid:
        nid = node_id("Person", _primary_name(match["name"]))
    events = person_events(kg, nid) if nid else []
    return {"available": True, "match": match, "person_id": nid, "events": events}
