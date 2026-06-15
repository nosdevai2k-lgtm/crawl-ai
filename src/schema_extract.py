"""LLM schema extraction: extract structured data from text using a JSON schema.

Inspired by crawl4ai's LLMExtractionStrategy with Pydantic schemas.
Supports any LLM via OpenAI-compatible API.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI


_SYSTEM_PROMPT = """You are a data extraction engine. Given text content and a JSON schema, extract ALL matching data.
Return ONLY a JSON object with key "items" containing an array of extracted objects matching the schema.
Each object must have exactly the fields defined in the schema. Use "" for unknown strings, 0 for unknown numbers, null for unknown optional fields.
Do NOT add markdown fences. Do NOT explain. Return raw JSON only."""


def extract_by_schema(
    client: OpenAI,
    model: str,
    text: str,
    *,
    schema: dict[str, Any],
    instruction: str = "",
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """Extract structured data from text using an LLM and a JSON schema.

    Args:
        client: OpenAI-compatible client.
        model: Model name.
        text: Source text to extract from.
        schema: JSON schema dict with "fields" list, each having "name", "type", "description".
        instruction: Additional extraction instruction.
        max_retries: Number of retry attempts.

    Returns:
        List of extracted items matching the schema.
    """
    schema_desc = json.dumps(schema, indent=2, ensure_ascii=False)
    user_msg = f"""Schema:
{schema_desc}

{f"Instruction: {instruction}" if instruction else ""}

Content to extract from:
{text[:80000]}"""

    for attempt in range(max_retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
            )
            raw = resp.choices[0].message.content or ""
            # Strip markdown fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rsplit("```", 1)[0]
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and "items" in parsed:
                return parsed["items"]
            if isinstance(parsed, list):
                return parsed
            return [parsed]
        except (json.JSONDecodeError, KeyError, IndexError):
            if attempt == max_retries:
                return []
    return []


# Pre-built schemas for common use cases

SCHEMA_PRODUCT = {
    "name": "Product",
    "fields": [
        {"name": "title", "type": "string", "description": "Product name"},
        {"name": "price", "type": "string", "description": "Price with currency"},
        {"name": "description", "type": "string", "description": "Short description"},
        {"name": "url", "type": "string", "description": "Product URL if available"},
    ],
}

SCHEMA_ARTICLE = {
    "name": "Article",
    "fields": [
        {"name": "title", "type": "string", "description": "Article headline"},
        {"name": "author", "type": "string", "description": "Author name"},
        {"name": "date", "type": "string", "description": "Publication date"},
        {"name": "summary", "type": "string", "description": "Brief summary"},
        {"name": "url", "type": "string", "description": "Article URL"},
    ],
}

SCHEMA_CONTACT = {
    "name": "Contact",
    "fields": [
        {"name": "name", "type": "string", "description": "Full name"},
        {"name": "email", "type": "string", "description": "Email address"},
        {"name": "phone", "type": "string", "description": "Phone number"},
        {"name": "organization", "type": "string", "description": "Company or org"},
        {"name": "role", "type": "string", "description": "Job title or role"},
    ],
}
