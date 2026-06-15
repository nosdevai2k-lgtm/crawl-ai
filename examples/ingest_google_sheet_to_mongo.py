"""
Một lần: crawl URL Google Sheet (browser) → CSV nội bộ → lưu MongoDB.

Chạy (PowerShell)::

  cd D:\\crawl-ai
  $env:MONGODB_URI="mongodb://localhost:27017"
  $env:SKIP_LLM="1"
  .\\.venv\\Scripts\\python.exe examples\\ingest_google_sheet_to_mongo.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from src.document_store import get_document_store  # noqa: E402
from src.pipeline import run_source  # noqa: E402
from src.quick_sources import quick_url_source  # noqa: E402
from src.settings import load_settings  # noqa: E402


SHEET_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1URI1ACueo3gk7LCurg2o4oaQe5fop_LqA9blovzTuGI/edit?gid=0#gid=0"
)


def main() -> None:
    uri = (os.environ.get("MONGODB_URI") or "").strip()
    if not uri:
        print("Thiếu MONGODB_URI (vd. mongodb://localhost:27017)", file=sys.stderr)
        sys.exit(2)
    os.environ.setdefault("SKIP_LLM", "1")
    settings = load_settings(ROOT / ".env" if (ROOT / ".env").is_file() else None)
    if not settings.mongodb_uri:
        print("load_settings không thấy MONGODB_URI trong môi trường.", file=sys.stderr)
        sys.exit(2)
    storage = get_document_store(settings)
    src = quick_url_source(
        SHEET_URL,
        extract="raw",
        source_id="google_sheet_URI1ACueo3",
    )
    res = run_source(src, storage, settings, None)
    print("source_id:", src.id)
    print("changed:", res.changed)
    print("document_id:", res.document_id)
    print("skipped_reason:", res.skipped_reason)
    if res.changed:
        row = storage.latest_for_source(src.id)
        if row:
            preview = (row.raw_text or "")[:500].replace("\r", "")
            print("raw_text_preview:\n", preview)


if __name__ == "__main__":
    main()
