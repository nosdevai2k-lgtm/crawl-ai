"""Build scene segments from key_facts and video metadata."""

from __future__ import annotations

import re
from typing import Any

from .models import ExtractedMedia

_TIME_RE = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{2})")
_SCENE_DEFAULT_SPACING = 30.0


def _parse_duration(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)) and val > 0:
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    m = _TIME_RE.search(s)
    if m:
        h, mi, sec = m.groups()
        return int(h or 0) * 3600 + int(mi) * 60 + int(sec)
    if s.isdigit():
        return float(s)
    return None


def _format_time(sec: float) -> str:
    s = max(0, int(sec))
    return f"{s // 60}:{s % 60:02d}"


def scenes_from_key_facts(
    facts: list[str],
    *,
    video_ref: str,
    title: str,
    date: str,
    duration_sec: float | None,
    base_props: dict[str, Any] | None = None,
    max_scenes: int = 12,
) -> list[ExtractedMedia]:
    """Turn key_facts into timestamped scene media rows."""
    props_base = dict(base_props or {})
    cleaned = [f.strip() for f in facts if (f or "").strip()][:max_scenes]
    if not cleaned:
        return []

    dur = duration_sec or max(_SCENE_DEFAULT_SPACING * len(cleaned), _SCENE_DEFAULT_SPACING)
    step = dur / max(len(cleaned), 1)
    out: list[ExtractedMedia] = []
    for i, fact in enumerate(cleaned):
        t = round(i * step, 2)
        end = round(min((i + 1) * step, dur), 2)
        out.append(ExtractedMedia(
            media_kind="scene",
            media_ref=f"{video_ref}#{t:.0f}",
            title=title,
            snippet=fact[:400],
            date=date,
            timestamp_sec=t,
            props={
                **props_base,
                "end_sec": end,
                "time_label": _format_time(t),
                "scene_index": i,
                "from_key_fact": True,
            },
        ))
    return out


def scenes_for_video(vid: dict[str, Any], structured: dict[str, Any], *, source_id: str) -> list[ExtractedMedia]:
    ref = vid.get("file_path") or vid.get("url") or vid.get("id") or "video"
    title = vid.get("title") or structured.get("title") or ""
    date = vid.get("upload_date") or structured.get("primary_date") or ""
    dur = _parse_duration(vid.get("duration"))
    facts = structured.get("key_facts") or []
    if not facts and structured.get("summary"):
        facts = [structured["summary"][:300]]
    base = {
        "source_id": source_id,
        "video_id": vid.get("id", ""),
        "parent_video": str(ref),
        "channel": vid.get("channel", ""),
    }
    scenes = scenes_from_key_facts(
        [str(x) for x in facts],
        video_ref=str(ref),
        title=title,
        date=date,
        duration_sec=dur,
        base_props=base,
    )
    if not scenes:
        scenes = [ExtractedMedia(
            media_kind="scene",
            media_ref=f"{ref}#0",
            title=title,
            snippet=(structured.get("summary") or "")[:300],
            date=date,
            timestamp_sec=0.0,
            props={**base, "time_label": "0:00"},
        )]
    return scenes
