"""Heuristic entity classification (Person / Location / Event / Festival / Organization / Topic)."""

from __future__ import annotations

import re

_EVENT_KW = {
    "su kien", "le", "hoi", "festival", "giai", "cuoc thi", "hoi nghi", "ky niem",
    "congress", "summit", "conference", "ceremony", "opening", "khai mac", "le khai mac",
    "event", "meeting", "election", "bau cu",
}
_FESTIVAL_KW = {
    "le hoi", "tet", "festival", "carnival", "parade", "ngay le", "holiday",
    "trung thu", "noel", "giang sinh",
}
_ORG_KW = {
    "cong ty", "tap doan", "bo ", "ngan hang", "quoc hoi", "chinh phu", "ubnd",
    "dai hoc", "truong", "vien", "committee", "party", "bank", "ministry", "corp",
    "ltd", "jsc", "inc", "vtv", "vov",
}
_LOC_KW = {
    "tinh", "thanh pho", "quan", "huyen", "xa", "phuong", "duong", "pho",
    "province", "city", "district", "ward", "street", "island", "bay", "beach",
    "mountain", "river", "lake", "park", "vn", "viet nam",
}
_PERSON_TITLE = re.compile(
    r"(?i)\b(tổng bí thư|thủ tướng|chủ tịch|bộ trưởng|phó|ông|bà|gs\.?|pgs\.?|tiến sĩ|dr\.?)\b"
)


def classify_entity(name: str, *, topic_hint: str = "") -> str:
    n = (name or "").strip()
    if not n:
        return "Entity"
    low = n.lower()
    norm = low.replace("đ", "d")
    blob = f"{norm} {topic_hint.lower()}"

    if any(k in blob for k in _FESTIVAL_KW):
        return "Festival"
    if any(k in blob for k in _EVENT_KW):
        return "Event"
    if _PERSON_TITLE.search(n) and len(n.split()) <= 8:
        return "Person"
    if any(k in blob for k in _ORG_KW):
        return "Organization"
    if any(k in blob for k in _LOC_KW):
        return "Location"
    # Vietnamese proper name heuristic: 2-4 capitalized tokens
    parts = n.split()
    if 2 <= len(parts) <= 5 and all(p[:1].isupper() for p in parts if p):
        return "Person"
    return "Entity"
