"""Crawl các địa điểm nổi tiếng miền Bắc VN (text + ảnh + tên) vào store."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from src.document_store import get_document_store
from src.pipeline import run_source
from src.quick_sources import quick_url_source
from src.settings import load_settings

PLACES = [
    ("Vịnh Hạ Long", "https://vi.wikipedia.org/wiki/V%E1%BB%8Bnh_H%E1%BA%A1_Long"),
    ("Sa Pa", "https://vi.wikipedia.org/wiki/Sa_Pa"),
    ("Hồ Hoàn Kiếm", "https://vi.wikipedia.org/wiki/H%E1%BB%93_Ho%C3%A0n_Ki%E1%BA%BFm"),
    ("Tràng An", "https://vi.wikipedia.org/wiki/Tr%C3%A0ng_An"),
    ("Chùa Hương", "https://vi.wikipedia.org/wiki/Ch%C3%B9a_H%C6%B0%C6%A1ng"),
    ("Cao nguyên đá Đồng Văn", "https://vi.wikipedia.org/wiki/Cao_nguy%C3%AAn_%C4%91%C3%A1_%C4%90%E1%BB%93ng_V%C4%83n"),
    ("Mộc Châu", "https://vi.wikipedia.org/wiki/M%E1%BB%99c_Ch%C3%A2u"),
    ("Tam Đảo", "https://vi.wikipedia.org/wiki/Tam_%C4%90%E1%BA%A3o"),
]

settings = load_settings()
storage = get_document_store(settings)

for name, url in PLACES:
    src = quick_url_source(url, extract="article", source_id=None)
    src.crawl_images = True
    try:
        res = run_source(src, storage, settings, None)
        imgs = 0
        latest = storage.latest_for_source(src.id)
        if latest:
            imgs = len(latest.meta.get("images") or [])
        status = "OK" if res.changed else f"skip({res.skipped_reason})"
        print(f"[{status}] {name} — imgs={imgs} id={res.document_id}")
    except Exception as exc:  # noqa: BLE001
        print(f"[ERR] {name} — {type(exc).__name__}: {exc}")
