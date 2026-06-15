"""Abstract document store + factory (SQLite vs MongoDB)."""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .settings import Settings
from .storage import DocumentRow


@runtime_checkable
class DocumentStore(Protocol):
    def latest_for_source(self, source_id: str) -> Optional[DocumentRow]: ...

    def insert_document(
        self,
        source_id: str,
        content_hash: str,
        raw_text: str,
        structured_json: Optional[str],
        meta: dict[str, Any],
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> int | str: ...

    def list_recent(self, limit: int = 50) -> list[DocumentRow]: ...

    def get_document_by_id(self, doc_id: int | str) -> Optional[DocumentRow]: ...

    def patch_document_meta(self, doc_id: int | str, meta_patch: dict[str, Any]) -> bool: ...


def get_document_store(settings: Settings) -> DocumentStore:
    if settings.mongodb_uri:
        try:
            from .mongo_storage import MongoStorage
        except ModuleNotFoundError as exc:
            name = getattr(exc, "name", None) or "pymongo"
            raise ModuleNotFoundError(
                f"{name}: chưa cài trong venv. Mở terminal tại thư mục crawl-ai, kích hoạt .venv, "
                "chạy: python -m pip install -r requirements.txt  (hoặc: python -m pip install pymongo)"
            ) from exc

        return MongoStorage(
            settings.mongodb_uri,
            settings.mongodb_database,
            settings.mongodb_collection,
        )
    from .storage import Storage

    return Storage(settings.database_path)
