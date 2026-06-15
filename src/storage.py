"""SQLite persistence: latest snapshot per source + history rows."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class DocumentRow:
    id: int | str
    source_id: str
    fetched_at: str
    content_hash: str
    raw_text: str
    structured_json: Optional[str]
    meta: dict[str, Any]
    etag: Optional[str]
    last_modified: Optional[str]


class Storage:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    structured_json TEXT,
                    meta TEXT NOT NULL DEFAULT '{}',
                    etag TEXT,
                    last_modified TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_source_time "
                "ON documents (source_id, fetched_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_source_hash "
                "ON documents (source_id, content_hash)"
            )

    def latest_for_source(self, source_id: str) -> Optional[DocumentRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, source_id, fetched_at, content_hash, raw_text,
                       structured_json, meta, etag, last_modified
                FROM documents
                WHERE source_id = ?
                ORDER BY fetched_at DESC, id DESC
                LIMIT 1
                """,
                (source_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_doc(row)

    def insert_document(
        self,
        source_id: str,
        content_hash: str,
        raw_text: str,
        structured_json: Optional[str],
        meta: dict[str, Any],
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> int:
        fetched_at = _utc_now_iso()
        meta_json = json.dumps(meta, ensure_ascii=False)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents (
                    source_id, fetched_at, content_hash, raw_text,
                    structured_json, meta, etag, last_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_id,
                    fetched_at,
                    content_hash,
                    raw_text,
                    structured_json,
                    meta_json,
                    etag,
                    last_modified,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_recent(self, limit: int = 50) -> list[DocumentRow]:
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, source_id, fetched_at, content_hash, raw_text,
                       structured_json, meta, etag, last_modified
                FROM documents
                ORDER BY fetched_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [self._row_to_doc(r) for r in cur.fetchall()]

    def get_document_by_id(self, doc_id: int | str) -> Optional[DocumentRow]:
        rid: int
        if isinstance(doc_id, int):
            rid = doc_id
        elif isinstance(doc_id, str) and doc_id.isdigit():
            rid = int(doc_id)
        else:
            return None
        with self._connect() as conn:
            cur = conn.execute(
                """
                SELECT id, source_id, fetched_at, content_hash, raw_text,
                       structured_json, meta, etag, last_modified
                FROM documents WHERE id = ?
                """,
                (rid,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_doc(row)

    def patch_document_meta(self, doc_id: int | str, meta_patch: dict[str, Any]) -> bool:
        row = self.get_document_by_id(doc_id)
        if row is None:
            return False
        meta = dict(row.meta)
        meta.update(meta_patch)
        meta_json = json.dumps(meta, ensure_ascii=False)
        rid = int(doc_id) if isinstance(doc_id, int) else int(doc_id) if str(doc_id).isdigit() else None
        if rid is None:
            return False
        with self._connect() as conn:
            conn.execute(
                "UPDATE documents SET meta = ? WHERE id = ?",
                (meta_json, rid),
            )
            conn.commit()
        return True

    @staticmethod
    def _row_to_doc(row: sqlite3.Row) -> DocumentRow:
        meta_raw = row["meta"] or "{}"
        try:
            meta = json.loads(meta_raw)
        except json.JSONDecodeError:
            meta = {}
        return DocumentRow(
            id=int(row["id"]),
            source_id=str(row["source_id"]),
            fetched_at=str(row["fetched_at"]),
            content_hash=str(row["content_hash"]),
            raw_text=str(row["raw_text"] or ""),
            structured_json=row["structured_json"],
            meta=meta,
            etag=row["etag"],
            last_modified=row["last_modified"],
        )
