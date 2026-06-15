"""Download YouTube videos via yt-dlp."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yt_dlp

DEFAULT_DOWNLOAD_DIR = Path(r"\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl")


@dataclass
class VideoResult:
    id: str
    title: str
    url: str
    duration: int
    upload_date: str
    channel: str
    playlist: str
    file_path: str
    description: str
    view_count: int
    tags: list[str]


def _get_download_dir() -> Path:
    d = Path(os.environ.get("YOUTUBE_DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR)))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_dirname(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*]', '_', name).strip('. ')
    return s[:100] or "unknown"


def _download_playlist(playlist_url: str, playlist_title: str, base_dir: Path, max_videos: int) -> list[VideoResult]:
    """Download videos from a single playlist into a named folder."""
    folder = base_dir / _safe_dirname(playlist_title)
    folder.mkdir(parents=True, exist_ok=True)

    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "playlistend": max_videos,
        "ignoreerrors": True,
        "outtmpl": str(folder / "%(title)s [%(id)s].%(ext)s"),
        "format": "best[height<=720]/best",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(playlist_url, download=True)

    if info is None:
        return []

    entries = info.get("entries")
    if entries is None:
        entries = [info]

    results: list[VideoResult] = []
    for e in entries:
        if e is None:
            continue
        vid_id = e.get("id", "")
        ext = e.get("ext", "mp4")
        title = e.get("title", vid_id)
        fpath = folder / f"{title} [{vid_id}].{ext}"
        if not fpath.exists():
            matches = list(folder.glob(f"*[{vid_id}].*"))
            fpath = matches[0] if matches else fpath

        results.append(VideoResult(
            id=vid_id,
            title=title,
            url=e.get("webpage_url") or e.get("url", ""),
            duration=int(e.get("duration") or 0),
            upload_date=e.get("upload_date") or "",
            channel=e.get("channel") or e.get("uploader") or "",
            playlist=playlist_title,
            file_path=str(fpath),
            description=e.get("description") or "",
            view_count=int(e.get("view_count") or 0),
            tags=e.get("tags") or [],
        ))
    return results


def fetch_youtube(url: str, *, max_videos: int = 10) -> list[VideoResult]:
    """Download videos from a YouTube URL (video, playlist, channel, or playlists page)."""
    base_dir = _get_download_dir()

    # Extract flat info first to understand the structure
    flat_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "ignoreerrors": True,
    }
    with yt_dlp.YoutubeDL(flat_opts) as ydl:
        meta = ydl.extract_info(url, download=False)

    if meta is None:
        return []

    entries = meta.get("entries") or []

    # Check if this is a page of playlists (entries are playlists, not videos)
    is_playlists_page = any(
        e.get("_type") == "playlist" or "/playlist?list=" in (e.get("url") or "")
        for e in entries if e
    )

    if is_playlists_page:
        # Each entry is a playlist — enumerate and download each
        all_results: list[VideoResult] = []
        for entry in entries:
            if entry is None:
                continue
            pl_url = entry.get("url") or ""
            pl_title = entry.get("title") or "unnamed_playlist"
            if not pl_url:
                continue
            # Make absolute URL if needed
            if not pl_url.startswith("http"):
                pl_url = f"https://www.youtube.com{pl_url}" if pl_url.startswith("/") else f"https://www.youtube.com/playlist?list={pl_url}"
            vids = _download_playlist(pl_url, pl_title, base_dir, max_videos)
            all_results.extend(vids)
        return all_results

    # Single playlist or channel videos
    is_playlist = meta.get("_type") == "playlist" or len(entries) > 0
    if is_playlist:
        pl_title = meta.get("title") or meta.get("uploader") or "playlist"
        return _download_playlist(url, pl_title, base_dir, max_videos)

    # Single video
    folder = base_dir / _safe_dirname(meta.get("channel") or meta.get("uploader") or "single")
    folder.mkdir(parents=True, exist_ok=True)
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
        "outtmpl": str(folder / "%(title)s [%(id)s].%(ext)s"),
        "format": "best[height<=720]/best",
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    if info is None:
        return []
    vid_id = info.get("id", "")
    ext = info.get("ext", "mp4")
    title = info.get("title", vid_id)
    fpath = folder / f"{title} [{vid_id}].{ext}"
    if not fpath.exists():
        matches = list(folder.glob(f"*[{vid_id}].*"))
        fpath = matches[0] if matches else fpath
    return [VideoResult(
        id=vid_id,
        title=title,
        url=info.get("webpage_url") or url,
        duration=int(info.get("duration") or 0),
        upload_date=info.get("upload_date") or "",
        channel=info.get("channel") or info.get("uploader") or "",
        playlist="",
        file_path=str(fpath),
        description=info.get("description") or "",
        view_count=int(info.get("view_count") or 0),
        tags=info.get("tags") or [],
    )]


def videos_to_text(videos: list[VideoResult]) -> str:
    if not videos:
        return "(no videos downloaded)"
    parts: list[str] = []
    for v in videos:
        dur_min = v.duration // 60
        dur_sec = v.duration % 60
        status = "✓ downloaded" if Path(v.file_path).exists() else "✗ failed"
        pl = f" | Playlist: {v.playlist}" if v.playlist else ""
        parts.append(
            f"## {v.title}\n"
            f"ID: {v.id} | Channel: {v.channel}{pl}\n"
            f"Duration: {dur_min}m{dur_sec:02d}s | Views: {v.view_count:,} | Date: {v.upload_date}\n"
            f"File: {v.file_path}\n"
            f"Status: {status}\n"
            f"Tags: {', '.join(v.tags[:20]) if v.tags else ''}\n"
            f"Description: {v.description[:500] if v.description else ''}"
        )
    return "\n---\n".join(parts)
