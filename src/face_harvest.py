"""Harvest ảnh chân dung / khuôn mặt cho nhân vật (image-search → human/<slug>)."""

from __future__ import annotations

import json
from pathlib import Path

from .async_fetch import fetch_many_sync
from .extract import image_search_results
from .image_extract import _IMG_EXT, _NOISE_IMG_NAME
from .image_harvest import _ascii_tokens, _is_real_image, _title_relevant
from .quick_sources import _readable_slug

_FACE_STOP = {
    "chan", "dung", "portrait", "official", "photo", "anh", "hinh", "face", "headshot",
    "viet", "nam", "vietnam", "president", "prime", "minister", "leader",
}


def _face_query_variants(name: str, en: str | None = None) -> list[str]:
    base = [
        f"{name} chân dung",
        f"{name} portrait",
        f"{name} official photo",
        f"{name} khuôn mặt",
        f"{name} ảnh chính thức",
        f"{name}",
    ]
    if en:
        base += [
            f"{en} portrait",
            f"{en} official photo",
            f"{en} face",
            f"{en} headshot",
            f"{en}",
        ]
    return base


def _update_names_json(images_dir: Path, rel_key: str, display: str) -> None:
    nf = images_dir / "names.json"
    names: dict[str, str] = {}
    if nf.is_file():
        try:
            names = json.loads(nf.read_text(encoding="utf-8"))
        except Exception:
            names = {}
    names[rel_key] = display
    nf.write_text(json.dumps(names, ensure_ascii=False, indent=2), encoding="utf-8")


def harvest_faces(
    name: str,
    out_dir: Path,
    *,
    user_agent: str,
    timeout: float,
    en_name: str | None = None,
    target: int = 120,
    min_bytes: int = 6000,
    images_root: Path | None = None,
) -> dict[str, int]:
    """Tải ảnh khuôn mặt vào data/images/human/<slug>/ và cập nhật names.json."""
    out_dir.mkdir(parents=True, exist_ok=True)
    name_tokens = (_ascii_tokens(name) | _ascii_tokens(en_name or "")) - _FACE_STOP
    # yêu cầu title chứa ít nhất 1 token họ/tên
    urls: list[str] = []
    seen_url: set[str] = set()
    stats_filtered = 0
    for q in _face_query_variants(name, en_name):
        for u, title in image_search_results(q, max_results=150):
            if u in seen_url:
                continue
            seen_url.add(u)
            if name_tokens and not _title_relevant(title, name_tokens):
                stats_filtered += 1
                continue
            urls.append(u)
        if len(urls) >= target * 3:
            break

    saved = 0
    seen_hash: set[str] = set()
    idx = len([f for f in out_dir.iterdir() if f.is_file() and f.suffix.lower() != ".json"])
    slug = out_dir.name
    stats = {
        "urls": len(urls),
        "saved": 0,
        "too_small": 0,
        "dup": 0,
        "failed": 0,
        "not_image": 0,
        "off_topic": stats_filtered,
    }
    batch = 50
    for i in range(0, len(urls), batch):
        if saved >= target:
            break
        chunk = urls[i : i + batch]
        results = fetch_many_sync(chunk, user_agent=user_agent, timeout=timeout, max_concurrent=10)
        for u, fr in zip(chunk, results):
            if saved >= target:
                break
            if not fr.ok or not fr.body:
                stats["failed"] += 1
                continue
            is_img = (fr.content_type or "").lower().startswith("image/")
            if not is_img and not _IMG_EXT.search(u):
                stats["not_image"] += 1
                continue
            if len(fr.body) < min_bytes or _NOISE_IMG_NAME.search(u):
                stats["too_small"] += 1
                continue
            if not _is_real_image(fr.body):
                stats["not_image"] += 1
                continue
            import hashlib

            h = hashlib.sha256(fr.body).hexdigest()
            if h in seen_hash:
                stats["dup"] += 1
                continue
            seen_hash.add(h)
            idx += 1
            ext = ".jpg"
            from pathlib import PurePosixPath

            suf = PurePosixPath(u.split("?")[0]).suffix.lower()
            if suf in (".jpg", ".jpeg", ".png", ".webp"):
                ext = ".jpg" if suf in (".jpg", ".jpeg") else suf
            (out_dir / f"{slug}_{idx:03d}{ext}").write_bytes(fr.body)
            saved += 1

    stats["saved"] = saved
    root = images_root or out_dir.parent.parent
    display = name if not en_name else f"{name} {en_name}"
    try:
        rel_slug = out_dir.relative_to(root).as_posix()
    except ValueError:
        rel_slug = f"human/{slug}"
    _update_names_json(root, rel_slug, display)
    return stats


def default_face_out_dir(name: str, images_root: Path | None = None) -> Path:
    from .quick_sources import _readable_slug

    root = images_root or Path("data/images")
    slug = _readable_slug(name) or "person"
    return root / "human" / slug
