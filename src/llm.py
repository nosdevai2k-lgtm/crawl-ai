"""Ollama via OpenAI-compatible chat completions."""

from __future__ import annotations

import json
import re
import time
from typing import Any

from openai import OpenAI

from .settings import Settings


STRUCTURE_SYSTEM = """You are given crawled text plus optional HTTP/source metadata.
Your job: decide what a reader must retain, and return ONE JSON object only (no markdown fences).

Fill EVERY key below. Use empty string "" or empty array [] when unknown. Do not invent dates or authors;
you may infer publication/site name from URL host only if the content does not name it.

Keys and intent:
- title: main headline or document title.
- summary: 3–6 sentences capturing the substance.
- language: BCP-47 or short label (e.g. "vi", "en").
- publication_or_site_name: newspaper, agency, site, or brand if identifiable.
- author_or_byline: writer, agency line, or "".
- primary_date: single most important calendar date (ISO-8601 if possible, else as written).
- dates_mentioned: all other notable dates/deadlines (strings, up to 25).
- locations_mentioned: places, venues, jurisdictions, địa danh, địa điểm (up to 20).
- events_mentioned: sự kiện, hội nghị, lễ khai mạc, giải đấu, cuộc họp (up to 15).
- festivals_mentioned: lễ hội, ngày lễ, tết, festival văn hóa (up to 12).
- key_entities: people, organizations, laws, products (up to 25).
- key_facts: short standalone facts worth keeping (up to 18 strings).
- numbers_and_stats: figures, percentages, counts, money (up to 18 strings).
- topics: 1–10 topical tags.
- primary_topic: one best tag.
- document_kind: e.g. news, press_release, legal, report, opinion, forum, product, other.
- audience_or_domain: who this is for or which domain (politics, tech, health, …) or "".
- links_or_references: important URLs or document titles cited (up to 20).
- open_questions: unclear points or needed follow-ups (up to 8).
- model_keeps_note: 1–3 sentences: what you prioritized, what you dropped for space, confidence.

Be generous with arrays when the source is dense; prefer precise short strings."""


def _strip_json_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def structure_content(
    client: OpenAI,
    model: str,
    text: str,
    *,
    max_retries: int,
    backoff_sec: float,
    fetch_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_err: Exception | None = None
    blocks: list[str] = []
    if fetch_context:
        ctx_json = json.dumps(fetch_context, ensure_ascii=False, indent=2)
        if len(ctx_json) > 12_000:
            ctx_json = ctx_json[:11_980] + "\n/* truncated */"
        blocks.append(
            "Crawl / HTTP / source context (facts only; do not fabricate beyond this):\n"
            + ctx_json
        )
    blocks.append("Content:\n\n" + text)
    user_content = "\n\n---\n\n".join(blocks)

    for attempt in range(max_retries):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": STRUCTURE_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception:
                kwargs.pop("response_format", None)
                resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or "{}"
            raw = _strip_json_fence(raw)
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(backoff_sec * (attempt + 1))
    raise RuntimeError(f"LLM failed after {max_retries} attempts") from last_err


def make_llm_client(settings: Settings) -> OpenAI:
    return OpenAI(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
    )


PERSONS_SYSTEM = """You are given crawled text that contains personal information about one or more people.
Extract ALL persons found and return ONE JSON object (no markdown fences) with key "persons" — an array.

Each person object MUST have these keys (use "" if unknown):
- full_name: full name as written in the source.
- date_of_birth: DOB in ISO-8601 (YYYY-MM-DD) or as written.
- gender: "male", "female", or "".
- address: home address or residential location.
- phone: phone number(s) as string (comma-separated if multiple).
- email: email address.
- id_number: national ID, passport, CCCD, CMND, or similar identifier.
- nationality: country or citizenship.
- position: job title, role, or rank.
- organization: employer, company, party, or institution.
- education: degree, school, or qualification.
- notes: any other notable personal detail (short string).

Rules:
- Extract EVERY distinct person mentioned. Do not merge different people.
- Do not invent information not present in the text.
- If the text is a list/table of people, extract each row as a separate person.
- Keep values concise and factual.
- Maximum 200 persons per response."""


def extract_persons(
    client: OpenAI,
    model: str,
    text: str,
    *,
    max_retries: int,
    backoff_sec: float,
    fetch_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract personal info records from crawled text."""
    blocks: list[str] = []
    if fetch_context:
        ctx_json = json.dumps(fetch_context, ensure_ascii=False, indent=2)
        if len(ctx_json) > 12_000:
            ctx_json = ctx_json[:11_980] + "\n/* truncated */"
        blocks.append("Source context:\n" + ctx_json)
    blocks.append("Content:\n\n" + text)
    user_content = "\n\n---\n\n".join(blocks)

    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            kwargs: dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "system", "content": PERSONS_SYSTEM},
                    {"role": "user", "content": user_content},
                ],
                "temperature": 0.1,
                "response_format": {"type": "json_object"},
            }
            try:
                resp = client.chat.completions.create(**kwargs)
            except Exception:
                kwargs.pop("response_format", None)
                resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or "{}"
            raw = _strip_json_fence(raw)
            data = json.loads(raw)
            # Normalize: ensure "persons" key exists as list
            if isinstance(data, dict) and "persons" not in data:
                # Model may have returned a single person or flat dict
                if "full_name" in data:
                    data = {"persons": [data]}
                else:
                    data = {"persons": []}
            return data
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(backoff_sec * (attempt + 1))
    raise RuntimeError(f"LLM extract_persons failed after {max_retries} attempts") from last_err
