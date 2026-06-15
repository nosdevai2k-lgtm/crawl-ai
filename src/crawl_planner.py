"""Gợi ý nguồn crawl (URL / RSS / Search) bằng LLM — người dùng phải xác nhận trên UI."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from openai import OpenAI

from .extract import extract_from_html, extract_from_pdf_bytes, is_pdf_bytes
from .fetch import fetch_url
from .llm import make_llm_client
from .settings import Settings

ALLOWED_KINDS_UI = frozenset({"URL", "RSS", "Search"})

PLANNER_SYSTEM = """You are a crawl planner for the app "crawl-ai".
The user describes what they want to monitor or archive. You suggest concrete sources ONLY as:
- kind "URL": one public https URL to a single HTML page or PDF (not a whole site crawl).
- kind "RSS": one https URL of an RSS or Atom feed.
- kind "Search": a short DuckDuckGo-style search query (no secrets).

Return ONE JSON object with key "suggestions" (array, max 6 items). Each item:
- "kind": one of "URL", "RSS", "Search"
- "value": the URL or query string (required)
- "title": short label in Vietnamese (max 80 chars)
- "rationale": one sentence in Vietnamese why this helps the goal

Rules:
- Prefer official docs, reputable feeds, or narrow queries — no login walls, no paywalled content as primary.
- Do not invent URLs: only suggest URLs you are confident exist or are standard (e.g. known doc paths). If unsure, use "Search" instead.
- If the user goal is vague, still give useful generic suggestions (e.g. site docs + feed + search).
- No markdown, no extra keys outside the wrapper object."""


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def assert_safe_http_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        raise ValueError("URL gốc để trống.")
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        raise ValueError("Chỉ cho phép URL http(s).")
    if not p.netloc:
        raise ValueError("URL không hợp lệ.")
    return u


def fetch_seed_context(url: str, settings: Settings, *, max_body_bytes: int = 220_000) -> str:
    """
    GET một lần (không If-None-Match), trích đoạn text ngắn làm ngữ cảnh cho planner.
    """
    u = assert_safe_http_url(url)
    fr = fetch_url(
        u,
        user_agent=settings.user_agent,
        timeout=min(settings.http_timeout, 45.0),
    )
    if fr.not_modified or fr.status_code == 304:
        return "(URL trả 304 — không có nội dung mới để làm ngữ cảnh.)"
    body = fr.body[:max_body_bytes]
    ct = (fr.content_type or "").lower()
    if "pdf" in ct or is_pdf_bytes(body):
        text = extract_from_pdf_bytes(body)
    else:
        html = body.decode("utf-8", errors="replace")
        text = extract_from_html(html, mode="raw")
    text = (text or "").strip()
    if len(text) > 14_000:
        text = text[:14_000] + "\n...[truncated]..."
    if not text:
        return "(Không trích được chữ từ trang — vẫn có thể gợi ý từ mục tiêu.)"
    return text


def normalize_suggestions(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind not in ALLOWED_KINDS_UI:
            continue
        value = str(item.get("value") or "").strip()
        if not value:
            continue
        title = str(item.get("title") or value)[:200]
        rationale = str(item.get("rationale") or "").strip()[:500]
        out.append(
            {
                "kind": kind,
                "value": value,
                "title": title,
                "rationale": rationale,
            }
        )
    return out[:6]


def suggest_crawl_sources(
    settings: Settings,
    *,
    user_goal: str,
    seed_url: str | None = None,
    seed_excerpt: str | None = None,
    client: OpenAI | None = None,
) -> list[dict[str, str]]:
    if settings.skip_llm:
        raise ValueError("Tắt «Skip LLM» trong sidebar để dùng gợi ý nguồn crawl.")
    goal = (user_goal or "").strip()
    if len(goal) < 4:
        raise ValueError("Nhập mục tiêu rõ hơn (ít nhất vài từ).")

    llm = client or make_llm_client(settings)
    blocks: list[str] = []
    blocks.append("User goal (Vietnamese or English):\n" + goal)
    if seed_url:
        blocks.append("Optional seed URL (context only):\n" + seed_url.strip())
    if seed_excerpt and seed_excerpt.strip():
        blocks.append(
            "Excerpt from seed page (may be truncated):\n\n" + seed_excerpt.strip()[:15_000]
        )
    user_content = "\n\n---\n\n".join(blocks)

    kwargs: dict[str, Any] = {
        "model": settings.ollama_model,
        "messages": [
            {"role": "system", "content": PLANNER_SYSTEM},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = llm.chat.completions.create(**kwargs)
    except Exception:
        kwargs.pop("response_format", None)
        resp = llm.chat.completions.create(**kwargs)

    raw_text = resp.choices[0].message.content or "{}"
    raw_text = _strip_json_fence(raw_text)
    data = json.loads(raw_text)
    sug = data.get("suggestions") if isinstance(data, dict) else None
    normalized = normalize_suggestions(sug)
    if not normalized:
        raise ValueError("Model không trả gợi ý hợp lệ — thử mô tả mục tiêu khác hoặc thêm URL gốc.")
    return normalized
