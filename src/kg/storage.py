"""SQLite persistence for KG nodes, edges, and media links."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class KGNode:
    id: str
    label: str
    name: str
    name_norm: str
    props: dict[str, Any]


@dataclass
class KGMediaRow:
    id: int
    doc_id: str
    source_id: str
    media_kind: str
    media_ref: str
    title: str
    snippet: str
    date: str
    timestamp_sec: float | None
    props: dict[str, Any]


class KGStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS kg_nodes (
                    id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    name TEXT NOT NULL,
                    name_norm TEXT NOT NULL,
                    props TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_label ON kg_nodes(label);
                CREATE INDEX IF NOT EXISTS idx_kg_nodes_norm ON kg_nodes(name_norm);

                CREATE TABLE IF NOT EXISTS kg_edges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    src_id TEXT NOT NULL,
                    dst_id TEXT NOT NULL,
                    rel_type TEXT NOT NULL,
                    weight REAL NOT NULL DEFAULT 1.0,
                    props TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(src_id, dst_id, rel_type)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_edges_src ON kg_edges(src_id);
                CREATE INDEX IF NOT EXISTS idx_kg_edges_dst ON kg_edges(dst_id);

                CREATE TABLE IF NOT EXISTS kg_media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    media_kind TEXT NOT NULL,
                    media_ref TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    snippet TEXT NOT NULL DEFAULT '',
                    date TEXT NOT NULL DEFAULT '',
                    timestamp_sec REAL,
                    props TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(doc_id, media_kind, media_ref)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_media_kind ON kg_media(media_kind);
                CREATE INDEX IF NOT EXISTS idx_kg_media_doc ON kg_media(doc_id);

                CREATE TABLE IF NOT EXISTS kg_media_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    media_id INTEGER NOT NULL,
                    node_id TEXT NOT NULL,
                    why TEXT NOT NULL DEFAULT '',
                    UNIQUE(media_id, node_id)
                );
                CREATE INDEX IF NOT EXISTS idx_kg_me_node ON kg_media_entities(node_id);

                CREATE TABLE IF NOT EXISTS kg_aliases (
                    alias_norm TEXT PRIMARY KEY,
                    node_id TEXT NOT NULL,
                    alias_display TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_kg_aliases_node ON kg_aliases(node_id);
                """
            )

    def get_node(self, node_id: str) -> KGNode | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT id, label, name, name_norm, props FROM kg_nodes WHERE id=?",
                (node_id,),
            ).fetchone()
        if not r:
            return None
        return KGNode(
            id=r["id"], label=r["label"], name=r["name"], name_norm=r["name_norm"],
            props=json.loads(r["props"] or "{}"),
        )

    def register_alias(self, alias_norm: str, node_id: str, alias_display: str) -> None:
        if not alias_norm:
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_aliases (alias_norm, node_id, alias_display)
                VALUES (?, ?, ?)
                ON CONFLICT(alias_norm) DO UPDATE SET node_id=excluded.node_id, alias_display=excluded.alias_display
                """,
                (alias_norm, node_id, alias_display),
            )

    def lookup_alias(self, alias_norm: str) -> dict[str, str] | None:
        with self._connect() as conn:
            r = conn.execute(
                "SELECT alias_norm, node_id, alias_display FROM kg_aliases WHERE alias_norm=?",
                (alias_norm,),
            ).fetchone()
        if not r:
            return None
        return {"alias_norm": r["alias_norm"], "node_id": r["node_id"], "alias_display": r["alias_display"]}

    def suggest_entities(self, query: str, labels: list[str] | None = None, limit: int = 8) -> list[dict[str, Any]]:
        from .normalize import ascii_norm, tokens

        qnorm = ascii_norm(query)
        qtok = tokens(query)
        hits: list[tuple[float, dict[str, Any]]] = []
        with self._connect() as conn:
            alias_rows = conn.execute(
                """
                SELECT a.alias_display, a.alias_norm, n.label, n.name, n.id
                FROM kg_aliases a
                JOIN kg_nodes n ON n.id = a.node_id
                """
            ).fetchall()
            node_rows = conn.execute("SELECT id, label, name, name_norm FROM kg_nodes").fetchall()
            degree = {
                r["node_id"]: r["c"]
                for r in conn.execute(
                    "SELECT node_id, COUNT(*) AS c FROM kg_media_entities GROUP BY node_id"
                ).fetchall()
            }
        for r in alias_rows:
            if labels and r["label"] not in labels:
                continue
            score = 0.0
            if qnorm and qnorm in (r["alias_norm"] or ""):
                score += 5
            if qtok & tokens(r["name"]):
                score += len(qtok & tokens(r["name"])) * 2
            if query and query.lower() in (r["name"] or "").lower():
                score += 3
            if score <= 0 and qnorm:
                continue
            if not qnorm:
                score = 0.1
            hits.append((score, {
                "name": r["name"],
                "label": r["label"],
                "degree": degree.get(r["id"], 0),
                "node_id": r["id"],
            }))
        seen = {h[1]["node_id"] for h in hits}
        for r in node_rows:
            if labels and r["label"] not in labels:
                continue
            if r["id"] in seen:
                continue
            score = 0.0
            if qtok & set((r["name_norm"] or "").split()):
                score += len(qtok & set((r["name_norm"] or "").split())) * 2
            if query and query.lower() in (r["name"] or "").lower():
                score += 3
            if score <= 0 and qnorm:
                continue
            if not qnorm:
                score = 0.1
            hits.append((score, {
                "name": r["name"],
                "label": r["label"],
                "degree": degree.get(r["id"], 0),
                "node_id": r["id"],
            }))
        hits.sort(key=lambda x: (x[0], x[1]["degree"]), reverse=True)
        out: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for _, item in hits:
            if item["name"] in seen_names:
                continue
            seen_names.add(item["name"])
            out.append({"name": item["name"], "label": item["label"], "degree": item["degree"]})
            if len(out) >= limit:
                break
        return out

    def upsert_node(self, node_id: str, label: str, name: str, name_norm: str, props: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_nodes (id, label, name, name_norm, props, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    name_norm=excluded.name_norm,
                    props=excluded.props,
                    updated_at=excluded.updated_at
                """,
                (node_id, label, name, name_norm, json.dumps(props or {}, ensure_ascii=False), _utc_now()),
            )

    def add_edge(self, src_id: str, dst_id: str, rel_type: str, *, weight: float = 1.0, props: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_edges (src_id, dst_id, rel_type, weight, props)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(src_id, dst_id, rel_type) DO UPDATE SET
                    weight=excluded.weight,
                    props=excluded.props
                """,
                (src_id, dst_id, rel_type, weight, json.dumps(props or {}, ensure_ascii=False)),
            )

    def upsert_media(
        self,
        *,
        doc_id: str,
        source_id: str,
        media_kind: str,
        media_ref: str,
        title: str = "",
        snippet: str = "",
        date: str = "",
        timestamp_sec: float | None = None,
        props: dict[str, Any] | None = None,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO kg_media (doc_id, source_id, media_kind, media_ref, title, snippet, date, timestamp_sec, props)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id, media_kind, media_ref) DO UPDATE SET
                    source_id=excluded.source_id,
                    title=excluded.title,
                    snippet=excluded.snippet,
                    date=excluded.date,
                    timestamp_sec=excluded.timestamp_sec,
                    props=excluded.props
                RETURNING id
                """,
                (
                    str(doc_id), source_id, media_kind, media_ref,
                    title, snippet, date, timestamp_sec,
                    json.dumps(props or {}, ensure_ascii=False),
                ),
            )
            row = cur.fetchone()
            return int(row[0])

    def link_media_entity(self, media_id: int, node_id: str, why: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO kg_media_entities (media_id, node_id, why)
                VALUES (?, ?, ?)
                ON CONFLICT(media_id, node_id) DO UPDATE SET why=excluded.why
                """,
                (media_id, node_id, why),
            )

    def delete_doc_index(self, doc_id: str) -> None:
        with self._connect() as conn:
            mids = [r[0] for r in conn.execute("SELECT id FROM kg_media WHERE doc_id=?", (str(doc_id),))]
            if mids:
                conn.executemany("DELETE FROM kg_media_entities WHERE media_id=?", [(m,) for m in mids])
            conn.execute("DELETE FROM kg_media WHERE doc_id=?", (str(doc_id),))

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            nodes = conn.execute("SELECT COUNT(*) FROM kg_nodes").fetchone()[0]
            edges = conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0]
            media = conn.execute("SELECT COUNT(*) FROM kg_media").fetchone()[0]
            by_label = {
                r["label"]: r["c"]
                for r in conn.execute("SELECT label, COUNT(*) AS c FROM kg_nodes GROUP BY label ORDER BY c DESC")
            }
            by_kind = {
                r["media_kind"]: r["c"]
                for r in conn.execute("SELECT media_kind, COUNT(*) AS c FROM kg_media GROUP BY media_kind ORDER BY c DESC")
            }
        return {"nodes": nodes, "edges": edges, "media": media, "by_label": by_label, "by_kind": by_kind}

    def find_nodes(self, query: str, labels: list[str] | None = None, limit: int = 20) -> list[KGNode]:
        from .normalize import ascii_norm, tokens

        qtok = tokens(query)
        with self._connect() as conn:
            rows = conn.execute("SELECT id, label, name, name_norm, props FROM kg_nodes").fetchall()
        out: list[tuple[float, KGNode]] = []
        for r in rows:
            if labels and r["label"] not in labels:
                continue
            nt = set((r["name_norm"] or "").split())
            score = len(qtok & nt) * 2
            if query and query.lower() in (r["name"] or "").lower():
                score += 3
            if ascii_norm(query) == (r["name_norm"] or ""):
                score += 5
            if score <= 0 and qtok:
                continue
            if not qtok:
                score = 0.1
            out.append((score, KGNode(
                id=r["id"], label=r["label"], name=r["name"], name_norm=r["name_norm"],
                props=json.loads(r["props"] or "{}"),
            )))
        out.sort(key=lambda x: x[0], reverse=True)
        return [n for _, n in out[:limit]]

    def neighbors(self, node_id: str, limit: int = 60) -> dict[str, Any]:
        with self._connect() as conn:
            edges = conn.execute(
                """
                SELECT e.src_id, e.dst_id, e.rel_type, n.label, n.name
                FROM kg_edges e
                JOIN kg_nodes n ON n.id = CASE WHEN e.src_id = ? THEN e.dst_id ELSE e.src_id END
                WHERE e.src_id = ? OR e.dst_id = ?
                LIMIT ?
                """,
                (node_id, node_id, node_id, limit),
            ).fetchall()
        nodes = {node_id}
        edge_list = []
        for e in edges:
            other = e["dst_id"] if e["src_id"] == node_id else e["src_id"]
            nodes.add(other)
            edge_list.append({"from": e["src_id"], "to": e["dst_id"], "rel": e["rel_type"], "label": e["rel_type"]})
        with self._connect() as conn:
            node_rows = conn.execute(
                f"SELECT id, label, name FROM kg_nodes WHERE id IN ({','.join('?' * len(nodes))})",
                list(nodes),
            ).fetchall()
        return {
            "nodes": [{"id": r["id"], "label": r["label"], "name": r["name"]} for r in node_rows],
            "edges": edge_list,
        }
