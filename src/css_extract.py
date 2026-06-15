"""CSS/XPath schema-based extraction — no LLM needed.

Inspired by crawl4ai's JsonCssExtractionStrategy. Define a schema with
CSS selectors and get structured JSON data from any page.

Usage:
    schema = {
        "name": "Products",
        "baseSelector": "div.product-card",
        "fields": [
            {"name": "title", "selector": "h2.title", "type": "text"},
            {"name": "price", "selector": ".price", "type": "text"},
            {"name": "image", "selector": "img", "type": "attribute", "attribute": "src"},
            {"name": "link", "selector": "a", "type": "attribute", "attribute": "href"},
        ]
    }
    results = css_extract(html, schema)
"""

from __future__ import annotations

import json
from typing import Any

from bs4 import BeautifulSoup, Tag


def css_extract(html: str, schema: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract structured data from HTML using CSS selectors.

    Args:
        html: Raw HTML string.
        schema: Dict with keys:
            - baseSelector: CSS selector for repeating container elements
            - fields: list of field defs, each with:
                - name: output key name
                - selector: CSS selector relative to base element
                - type: "text", "html", "attribute", "list"
                - attribute: (for type="attribute") which attr to extract

    Returns:
        List of dicts, one per matched base element.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_selector = schema.get("baseSelector", "body")
    fields = schema.get("fields", [])

    containers = soup.select(base_selector)
    results: list[dict[str, Any]] = []

    for container in containers:
        record: dict[str, Any] = {}
        for field in fields:
            name = field["name"]
            selector = field.get("selector", "")
            ftype = field.get("type", "text")
            attr = field.get("attribute", "")

            if not selector:
                record[name] = _extract_value(container, ftype, attr)
            else:
                if ftype == "list":
                    els = container.select(selector)
                    record[name] = [_extract_value(el, "text", "") for el in els]
                else:
                    el = container.select_one(selector)
                    record[name] = _extract_value(el, ftype, attr) if el else ""
        results.append(record)

    return results


def _extract_value(el: Tag | None, ftype: str, attr: str) -> str:
    """Extract a value from a BeautifulSoup element."""
    if el is None:
        return ""
    if ftype == "attribute":
        return str(el.get(attr, "")).strip()
    if ftype == "html":
        return str(el)
    # default: text
    return el.get_text(separator=" ", strip=True)


def css_extract_json(html: str, schema: dict[str, Any]) -> str:
    """Extract and return as JSON string."""
    return json.dumps(css_extract(html, schema), ensure_ascii=False, indent=2)
