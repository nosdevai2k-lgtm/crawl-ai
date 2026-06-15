"""Tìm kiếm ảnh đã crawl theo preset (lấy cảm hứng từ pipelines 8002).

Preset đổi cách lọc/xếp hạng theo đặc điểm dữ liệu ảnh:
- phong_canh : ưu tiên ảnh khổ ngang, độ phân giải cao
- di_tich    : chỉ địa danh kiến trúc (chùa/tháp/thành/đền/nhà thờ...), rank theo độ nét
- dia_diem   : khớp mạnh theo tên địa danh/địa điểm, gom theo folder
- le_su_kien : lễ hội + sự kiện + ngày lễ (folder festival/events/holidays)
- tin_tuc    : tìm trong document (DB) theo từ khoá + ngày mới nhất
- tong_hop   : trộn tất cả, điểm cân bằng
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

IMAGES_DIR = Path("data/images")
INDEX_FILE = IMAGES_DIR / "index.json"
_IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

PRESETS = {
    "phong_canh": {"label": "🏞️ Phong cảnh", "hint": "ảnh khổ ngang · độ phân giải cao"},
    "di_tich": {"label": "🏛️ Di tích / kiến trúc", "hint": "chùa/tháp/thành/đền · rank theo độ nét"},
    "dia_diem": {"label": "📍 Theo địa điểm", "hint": "khớp mạnh tên địa danh, gom theo folder"},
    "nhan_vat": {"label": "👤 Nhân vật / lãnh đạo", "hint": "nhóm human · chân dung người"},
    "le_su_kien": {
        "label": "🎌 Lễ hội / sự kiện / ngày lễ",
        "hint": "nhóm festival + events + holidays",
    },
    "tin_tuc": {"label": "📰 Tin tức / tư liệu", "hint": "document text · ưu tiên ngày mới"},
    "tong_hop": {"label": "🌐 Tổng hợp", "hint": "trộn tất cả, điểm cân bằng"},
}

# Alias cũ (UI/session có thể còn lưu su_kien / le_tet)
_PRESET_ALIASES = {
    "su_kien": "le_su_kien",
    "le_tet": "le_su_kien",
}

# preset ràng buộc theo group của index (None = không ràng buộc)
_PRESET_GROUPS = {
    "nhan_vat": {"human"},
    "le_su_kien": {"events", "holidays", "festival"},
}

_ARCH_KW = {"chua", "thap", "thanh", "den", "dinh", "lang", "nha", "tho",
            "dia", "dao", "hoang", "cot", "thien", "mu", "po", "nagar", "son"}


def _ascii_tokens(text: str) -> set[str]:
    s = unicodedata.normalize("NFKD", text).replace("đ", "d").replace("Đ", "D")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    return {t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 2}


def build_index(images_dir: Path = IMAGES_DIR, *, save: bool = True) -> dict[str, Any]:
    """Quét folder ảnh (phẳng <slug> hoặc lồng <group>/<slug>) → index {key: {...}}."""
    try:
        from PIL import Image
    except Exception:
        Image = None
    index: dict[str, Any] = {}
    if not images_dir.is_dir():
        return index
    names: dict[str, str] = {}
    nf = images_dir / "names.json"
    if nf.is_file():
        try:
            names = json.loads(nf.read_text(encoding="utf-8"))
        except Exception:
            names = {}

    def _scan_leaf(d: Path) -> list[dict[str, Any]]:
        imgs = []
        for f in sorted(d.iterdir()):
            if not f.is_file() or f.suffix.lower() not in _IMG_EXT:
                continue
            w = h = 0
            if Image is not None:
                try:
                    with Image.open(f) as im:
                        w, h = im.size
                except Exception:
                    pass
            imgs.append({"file": f.name, "w": w, "h": h})
        return imgs

    def _add(key: str, slug: str, d: Path, group: str = "") -> None:
        imgs = _scan_leaf(d)
        if not imgs:
            return
        toks = _ascii_tokens(slug) | _ascii_tokens(names.get(slug, "")) | _ascii_tokens(group)
        index[key] = {"name": names.get(slug, slug), "group": group, "tokens": sorted(toks),
                      "count": len(imgs), "images": imgs}

    for d in sorted(p for p in images_dir.iterdir() if p.is_dir()):
        subdirs = [p for p in d.iterdir() if p.is_dir()]
        has_imgs = any(f.is_file() and f.suffix.lower() in _IMG_EXT for f in d.iterdir())
        if subdirs and not has_imgs:  # folder nhóm: <group>/<slug>
            for sub in sorted(subdirs):
                _add(f"{d.name}/{sub.name}", sub.name, sub, group=d.name)
        else:  # folder phẳng: <slug>
            _add(d.name, d.name, d)
    if save:
        images_dir.mkdir(parents=True, exist_ok=True)
        INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    return index


def load_index(images_dir: Path = IMAGES_DIR) -> dict[str, Any]:
    if INDEX_FILE.is_file():
        try:
            return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return build_index(images_dir)


def _folder_match(qtokens: set[str], ftokens: set[str]) -> int:
    return len(qtokens & set(ftokens))


def search_images(
    query: str,
    preset: str = "tong_hop",
    *,
    tools: dict[str, str] | None = None,
    top_k: int = 30,
    index: dict[str, Any] | None = None,
    storage: Any = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Trả {request, results}. results: list {kind, path/source_id, slug, score, why}."""
    tools = tools or {}
    preset = _PRESET_ALIASES.get(preset, preset)
    preset = preset if preset in PRESETS else "tong_hop"
    qtokens = _ascii_tokens(query)
    loc_tokens = {t for t in _ascii_tokens(tools.get("location", "")) if len(t) >= 3}

    # Resolve tên qua KG → boost token + preset gợi ý
    if db_path is not None:
        try:
            from .search_match import meaningful_overlap, resolve_search_context

            ctx = resolve_search_context(db_path, entities=query, topics="")
            for r in ctx["resolved"]:
                qtokens |= r["tokens"]
                if r["label"] == "Location" and not loc_tokens:
                    loc_tokens |= {t for t in r["tokens"] if len(t) >= 3}
        except Exception:
            pass

    request = {"query": query, "preset": preset, "top_k": top_k,
               "tools": {k: v for k, v in tools.items() if v}}

    # preset tin_tuc → tìm trong document store
    if preset == "tin_tuc":
        results = _search_docs(query, qtokens, tools, top_k, storage)
        return {"request": request, "results": results}

    idx = index if index is not None else load_index()
    want_groups = _PRESET_GROUPS.get(preset)
    tool_group = (tools.get("group") or "").strip().lower()
    results: list[dict[str, Any]] = []
    for slug, info in idx.items():
        group = (info.get("group") or "").lower()
        if want_groups and group not in want_groups:
            continue
        if tool_group and group != tool_group:
            continue
        ftokens = set(info.get("tokens") or [])
        from .search_match import meaningful_overlap

        rel = meaningful_overlap(qtokens, ftokens) if qtokens else 1
        if qtokens and rel == 0:
            continue
        if loc_tokens and not meaningful_overlap(loc_tokens, ftokens):
            continue
        if preset == "di_tich" and not (ftokens & _ARCH_KW):
            continue
        for im in info.get("images", []):
            w, h = im.get("w", 0), im.get("h", 0)
            area = w * h
            landscape = 1 if w > h else 0
            portrait = 1 if h >= w else 0
            if preset == "phong_canh":
                score = rel * 5 + landscape * 3 + min(area / 2_000_000, 3)
                why = "ngang+nét" if landscape else "độ nét"
            elif preset == "di_tich":
                score = rel * 5 + min(area / 2_000_000, 2)
                why = "kiến trúc"
            elif preset == "dia_diem":
                score = rel * 10 + (5 if loc_tokens else 0)
                why = "khớp địa điểm"
            elif preset == "nhan_vat":  # chân dung: ưu tiên ảnh dọc
                score = rel * 6 + portrait * 2 + min(area / 3_000_000, 1)
                why = "chân dung" if portrait else "nhân vật"
            elif preset == "le_su_kien":
                score = rel * 6 + min(area / 3_000_000, 2)
                why = "lễ hội/sự kiện"
            else:  # tong_hop
                score = rel * 4 + landscape + min(area / 3_000_000, 2)
                why = "tổng hợp"
            results.append({
                "kind": "image", "slug": slug, "group": group,
                "path": str(IMAGES_DIR / slug / im["file"]),
                "score": round(float(score), 3), "w": w, "h": h, "why": why,
            })
    results.sort(key=lambda r: r["score"], reverse=True)
    return {"request": request, "results": results[:top_k]}


def _search_docs(query: str, qtokens: set[str], tools: dict[str, str], top_k: int, storage: Any) -> list[dict[str, Any]]:
    if storage is None:
        return []
    from .search_match import meaningful_overlap

    rows = storage.list_recent(limit=300)
    dfrom, dto = tools.get("date_from", ""), tools.get("date_to", "")
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            d = json.loads(r.structured_json or "{}")
        except Exception:
            d = {}
        title, summary = d.get("title") or "", d.get("summary") or ""
        date = d.get("primary_date") or ""
        if dfrom and date and date < dfrom:
            continue
        if dto and date and date > dto:
            continue
        ttok = _ascii_tokens(title)
        stok = _ascii_tokens(summary)
        topics = _ascii_tokens(" ".join(d.get("topics") or []))
        rel = meaningful_overlap(qtokens, ttok) * 3 + meaningful_overlap(qtokens, topics) * 2 + meaningful_overlap(qtokens, stok)
        if qtokens and rel < 2:
            continue
        kind = (d.get("document_kind") or "").lower()
        score = rel + (2 if "news" in kind else 0) + (1 if date else 0)
        out.append({"kind": "doc", "source_id": r.source_id, "title": title,
                    "snippet": summary[:160], "date": date, "score": round(float(score), 3)})
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:top_k]
