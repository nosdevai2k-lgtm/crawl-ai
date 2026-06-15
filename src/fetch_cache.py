"""Fetch cache: avoid re-downloading the same URL within a TTL.

Inspired by crawl4ai's CacheMode (ENABLED, BYPASS, WRITE_ONLY).
Uses SQLite for simplicity and persistence across sessions.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CachedResponse:
    url: str
    body: bytes
    content_type: str
    status_code: int
    etag: Optional[str]
    last_modified: Optional[str]
    cached_at: float


class FetchCache:
    """Simple URL-based fetch cache with TTL."""

    def __init__(self, db_path: Path | None = None, ttl_sec: int = 3600):
        self.ttl_sec = ttl_sec
        self.db_path = db_path or Path("data/fetch_cache.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    url_hash TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    body BLOB NOT NULL,
                    content_type TEXT,
                    status_code INTEGER,
                    etag TEXT,
                    last_modified TEXT,
                    cached_at REAL NOT NULL
                )
            """)

    @staticmethod
    def _hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def get(self, url: str) -> Optional[CachedResponse]:
        """Get cached response if it exists and is not expired."""
        h = self._hash(url)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT url, body, content_type, status_code, etag, last_modified, cached_at "
                "FROM cache WHERE url_hash = ?", (h,)
            ).fetchone()
        if row is None:
            return None
        cached_at = row[6]
        if time.time() - cached_at > self.ttl_sec:
            return None  # Expired
        return CachedResponse(
            url=row[0], body=row[1], content_type=row[2] or "",
            status_code=row[3], etag=row[4], last_modified=row[5],
            cached_at=cached_at,
        )

    def put(self, url: str, body: bytes, content_type: str, status_code: int,
            etag: str | None = None, last_modified: str | None = None) -> None:
        """Store a response in cache."""
        h = self._hash(url)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (url_hash, url, body, content_type, status_code, etag, last_modified, cached_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (h, url, body, content_type, status_code, etag, last_modified, time.time()),
            )

    def invalidate(self, url: str) -> None:
        """Remove a URL from cache."""
        h = self._hash(url)
        with self._connect() as conn:
            conn.execute("DELETE FROM cache WHERE url_hash = ?", (h,))

    def clear(self) -> int:
        """Clear all cached entries. Returns count removed."""
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM cache")
            count = cur.fetchone()[0]
            conn.execute("DELETE FROM cache")
        return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        cutoff = time.time() - self.ttl_sec
        with self._connect() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM cache WHERE cached_at < ?", (cutoff,))
            count = cur.fetchone()[0]
            conn.execute("DELETE FROM cache WHERE cached_at < ?", (cutoff,))
        return count
