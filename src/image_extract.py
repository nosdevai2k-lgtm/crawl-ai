"""Trích URL ảnh từ HTML và tải ảnh về đĩa."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .fetch import fetch_url

_IMG_EXT = re.compile(r"\.(jpe?g|png|gif|webp|bmp|svg|avif)(\?|$)", re.I)

# URL ảnh giao diện/khung trang (không phải nội dung) — loại bỏ.
_NOISE_URL = re.compile(
    r"static/images|resources/assets|/footer/|Special:Central"
    r"|/thumb/[^?]*?/(?:Logo|Stub)|mediawiki|wikimedia\.svg",
    re.I,
)
# Tên file ảnh rác (loading/spinner/icon/placeholder/pixel) — bỏ.
_NOISE_IMG_NAME = re.compile(
    r"loading|spinner|placeholder|sprite|blank|pixel|1x1|/icon", re.I
)
# Caption/tên là nhãn khung Wikipedia, bỏ.
_NOISE_NAMES = frozenset({
    "wikipedia", "bách khoa toàn thư mở", "stub icon", "wikimedia foundation",
    "powered by mediawiki", "biểu tượng định hướng",
})


def _is_noise_url(url: str) -> bool:
    return bool(_NOISE_URL.search(url))


def extract_page_title(html: str) -> str:
    """Tên trang/địa điểm: ưu tiên og:title, sau đó <title> (bỏ hậu tố site)."""
    soup = BeautifulSoup(html, "html.parser")
    raw = ""
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        raw = og["content"].strip()
    elif soup.title and soup.title.string:
        raw = soup.title.string.strip()
    if not raw:
        return ""
    return re.split(r"\s+[–\-|]\s+", raw)[0].strip()


def extract_image_urls(html: str, base_url: str = "", *, limit: int = 100) -> list[str]:
    """Lấy URL ảnh từ <img src/data-src/srcset>, og:image, twitter:image (bỏ ảnh khung trang)."""
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []

    def _add(u: str) -> None:
        u = (u or "").strip()
        if not u or u.startswith(("data:", "javascript:")):
            return
        absu = urljoin(base_url, u) if base_url else u
        if absu not in urls and not _is_noise_url(absu):
            urls.append(absu)

    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in ("og:image", "twitter:image", "og:image:url"):
            _add(meta.get("content", ""))

    for img in soup.find_all("img"):
        cand = ""
        # ưu tiên các thuộc tính lazy-load (ảnh thật), src thường là placeholder base64
        for attr in ("data-src", "data-original", "data-lazy-src", "data-lazy", "data-url", "src"):
            v = (img.get(attr) or "").strip()
            if v and not v.startswith("data:"):
                cand = v
                break
        if not cand:
            srcset = img.get("srcset") or img.get("data-srcset") or ""
            cand = srcset.split(",")[0].strip().split(" ")[0] if srcset else ""
        _add(cand)

    return urls[:limit]


def extract_image_names(html: str, base_url: str = "") -> dict[str, str]:
    """Map URL ảnh -> tên (alt/title của <img>, figcaption, hoặc tiêu đề trang cho og:image)."""
    soup = BeautifulSoup(html, "html.parser")
    names: dict[str, str] = {}

    def _abs(u: str) -> str:
        u = (u or "").strip()
        return urljoin(base_url, u) if (u and base_url) else u

    page_title = ""
    if soup.title and soup.title.string:
        page_title = soup.title.string.strip()
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        page_title = og["content"].strip()

    for meta in soup.find_all("meta"):
        prop = (meta.get("property") or meta.get("name") or "").lower()
        if prop in ("og:image", "twitter:image", "og:image:url"):
            u = _abs(meta.get("content", ""))
            if u and page_title:
                names.setdefault(u, page_title)

    for img in soup.find_all("img"):
        name = _following_caption(img) or (img.get("alt") or img.get("title") or "").strip()
        if not name:
            fig = img.find_parent("figure")
            if fig:
                cap = fig.find("figcaption")
                if cap:
                    name = cap.get_text(" ", strip=True)
        if not name or name.lower() in _NOISE_NAMES:
            continue
        for attr in ("src", "data-src"):
            u = _abs(img.get(attr, ""))
            if u and not _is_noise_url(u):
                names.setdefault(u, name)
    return names


def _following_caption(img, *, max_len: int = 200) -> str:
    """Caption đứng ngay sau <img> (figcaption/<p>), trước img/heading kế tiếp."""
    for el in img.find_all_next(["img", "figcaption", "p", "h1", "h2", "h3", "h4"]):
        if el.name == "img" or el.name in ("h1", "h2", "h3", "h4"):
            return ""
        txt = el.get_text(" ", strip=True)
        return txt if (txt and len(txt) <= max_len) else ""
    return ""


def _filename_for(url: str, content_type: str | None) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    name = Path(urlparse(url).path).name
    ext = Path(name).suffix
    if not ext:
        ct = (content_type or "").lower()
        ext = ".jpg" if "jpeg" in ct else "." + ct.split("/")[-1] if "image/" in ct else ".img"
    return f"{digest}{ext}"


def _slug_name(caption: str, max_len: int = 60) -> str:
    """Slug ASCII từ caption (bỏ dấu) để đặt tên file."""
    import unicodedata

    s = unicodedata.normalize("NFKD", caption)
    s = s.replace("đ", "d").replace("Đ", "D")
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s[:max_len].strip("-")


def _filename_for_named(url: str, content_type: str | None, caption: str) -> str:
    """Tên file theo caption (slug); nếu không có, dùng tên file gốc trong URL; fallback hash."""
    base = _filename_for(url, content_type)
    ext = Path(base).suffix
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
    slug = _slug_name(caption)
    if not slug:
        # Không caption → thử slug từ tên file gốc trong URL path.
        stem = Path(urlparse(url).path).stem
        slug = _slug_name(stem)
    if not slug:
        return base
    return f"{slug}-{digest}{ext}"


def download_images(
    urls: list[str],
    out_dir: Path,
    *,
    user_agent: str,
    timeout: float,
    max_images: int = 50,
    names: dict[str, str] | None = None,
    place: str = "",
    min_bytes: int = 3000,
) -> list[dict[str, str]]:
    """Tải ảnh về out_dir (song song); trả về list {url, path, content_type, name, place}.

    Bỏ ảnh rác: tên loading/spinner/icon, hoặc file quá nhỏ (< min_bytes).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    names = names or {}
    from .async_fetch import fetch_many_sync

    selected = urls[:max_images]
    results = fetch_many_sync(
        selected, user_agent=user_agent, timeout=timeout, max_concurrent=10
    )
    saved: list[dict[str, str]] = []
    for url, fr in zip(selected, results):
        if not fr.ok or not fr.body:
            continue
        is_image = (fr.content_type or "").lower().startswith("image/")
        if not is_image and not _IMG_EXT.search(url):
            continue
        if len(fr.body) < min_bytes or _NOISE_IMG_NAME.search(url):
            continue
        path = out_dir / _filename_for_named(url, fr.content_type, names.get(url, ""))
        path.write_bytes(fr.body)
        saved.append({
            "url": url,
            "path": str(path),
            "content_type": fr.content_type or "",
            "name": names.get(url, ""),
            "place": place,
        })
    return saved
