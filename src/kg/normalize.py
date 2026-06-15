"""Normalize entity names for matching and stable node ids."""

from __future__ import annotations

import hashlib
import re
import unicodedata


def ascii_norm(text: str) -> str:
    s = unicodedata.normalize("NFKD", text or "").replace("đ", "d").replace("Đ", "D")
    s = s.encode("ascii", "ignore").decode("ascii").lower()
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\s+", " ", s)


def tokens(text: str) -> set[str]:
    return {t for t in ascii_norm(text).split() if len(t) >= 2}


def node_id(label: str, name: str) -> str:
    norm = ascii_norm(name) or "unknown"
    h = hashlib.sha1(f"{label}:{norm}".encode()).hexdigest()[:12]
    return f"{label.lower()}:{h}"
