"""MongoDB persistence (same logical fields as SQLite documents)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import ASCENDING, DESCENDING, MongoClient

from .storage import DocumentRow


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MongoStorage:
    """One document = one crawl snapshot (append-only)."""

    def __init__(self, uri: str, database: str, collection: str) -> None:
        self._client = MongoClient(uri, serverSelectionTimeoutMS=8000)
        self._coll = self._client[database][collection]
        self._coll.create_index(
            [("source_id", ASCENDING), ("fetched_at", DESCENDING)]
        )
        self._coll.create_index([("fetched_at", DESCENDING)])

    def latest_for_source(self, source_id: str) -> Optional[DocumentRow]:
        doc = self._coll.find_one(
            {"source_id": source_id},
            sort=[("fetched_at", DESCENDING), ("_id", DESCENDING)],
        )
        if doc is None:
            return None
        return self._doc_to_row(doc)

    def insert_document(
        self,
        source_id: str,
        content_hash: str,
        raw_text: str,
        structured_json: Optional[str],
        meta: dict[str, Any],
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> str:
        fetched_at = _utc_now_iso()
        doc = {
            "source_id": source_id,
            "fetched_at": fetched_at,
            "content_hash": content_hash,
            "raw_text": raw_text,
            "structured_json": structured_json,
            "meta": meta,
            "etag": etag,
            "last_modified": last_modified,
        }
        res = self._coll.insert_one(doc)
        return str(res.inserted_id)

    def list_recent(self, limit: int = 50) -> list[DocumentRow]:
        cur = self._coll.find().sort("fetched_at", DESCENDING).limit(limit)
        return [self._doc_to_row(d) for d in cur]

    def get_document_by_id(self, doc_id: int | str) -> Optional[DocumentRow]:
        from bson import ObjectId
        from bson.errors import InvalidId

        oid: Any = doc_id
        if isinstance(doc_id, str):
            try:
                oid = ObjectId(doc_id)
            except (InvalidId, ValueError):
                return None
        doc = self._coll.find_one({"_id": oid})
        if doc is None:
            return None
        return self._doc_to_row(doc)

    def patch_document_meta(self, doc_id: int | str, meta_patch: dict[str, Any]) -> bool:
        from bson import ObjectId
        from bson.errors import InvalidId

        if isinstance(doc_id, str):
            try:
                oid = ObjectId(doc_id)
            except (InvalidId, ValueError):
                return False
        else:
            return False
        doc = self._coll.find_one({"_id": oid}, projection={"meta": 1})
        if doc is None:
            return False
        meta = dict(doc.get("meta") or {})
        meta.update(meta_patch)
        self._coll.update_one({"_id": oid}, {"$set": {"meta": meta}})
        return True

    @staticmethod
    def _doc_to_row(doc: dict[str, Any]) -> DocumentRow:
        meta_raw = doc.get("meta")
        if isinstance(meta_raw, dict):
            meta = meta_raw
        elif isinstance(meta_raw, str):
            try:
                meta = json.loads(meta_raw)
            except json.JSONDecodeError:
                meta = {}
        else:
            meta = {}
        oid = doc.get("_id")
        rid: int | str = str(oid) if oid is not None else ""
        return DocumentRow(
            id=rid,
            source_id=str(doc["source_id"]),
            fetched_at=str(doc["fetched_at"]),
            content_hash=str(doc["content_hash"]),
            raw_text=str(doc.get("raw_text") or ""),
            structured_json=doc.get("structured_json"),
            meta=meta,
            etag=doc.get("etag"),
            last_modified=doc.get("last_modified"),
        )
