"""Fetch JS-rendered pages using Playwright (headless Chromium).

Handles ASP.NET WebForms (ViewState/postback), SPAs, and any page
that requires JavaScript to render content.

Usage:
    from src.fetch_browser import fetch_browser
    result = fetch_browser("https://dbqh.quochoi.vn/VI/Daibieu.aspx", wait_selector="table")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BrowserFetchResult:
    url: str
    status_code: int
    html: str
    content_type: str


def fetch_browser(
    url: str,
    *,
    wait_selector: str | None = None,
    wait_timeout_ms: int = 30_000,
    wait_until: str = "domcontentloaded",
    user_agent: str | None = None,
    extra_headers: dict[str, str] | None = None,
    js_code: list[str] | None = None,
    auto_scroll: bool = True,
) -> BrowserFetchResult:
    """Render a page with headless Chromium and return the full HTML.

    Args:
        url: Target URL.
        wait_selector: CSS selector to wait for before capturing HTML.
        wait_timeout_ms: Max ms to wait for selector/network idle.
        wait_until: Playwright load state — 'networkidle', 'domcontentloaded', or 'load'.
        user_agent: Override browser user-agent.
        extra_headers: Additional HTTP headers.
        js_code: List of JavaScript snippets to execute after page load, before extraction.
        auto_scroll: Scroll to bottom to trigger lazy-loaded SPA content.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context_kwargs: dict = {}
        if user_agent:
            context_kwargs["user_agent"] = user_agent
        if extra_headers:
            context_kwargs["extra_http_headers"] = extra_headers

        ctx = browser.new_context(**context_kwargs)
        page = ctx.new_page()

        status = 0
        try:
            resp = page.goto(url, wait_until=wait_until, timeout=wait_timeout_ms)
            status = resp.status if resp else 0
        except Exception as e:  # noqa: BLE001 — capture whatever rendered so far
            logger.warning("goto timeout/err on %s: %s", url, e)

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_timeout_ms)
            except Exception:
                logger.warning("Selector '%s' not found within %dms on %s", wait_selector, wait_timeout_ms, url)

        if auto_scroll:
            try:
                for _ in range(6):
                    page.evaluate("window.scrollBy(0, document.body.scrollHeight/6)")
                    page.wait_for_timeout(400)
            except Exception:
                pass

        # Execute custom JS scripts
        if js_code:
            for script in js_code:
                try:
                    page.evaluate(script)
                    page.wait_for_timeout(500)
                except Exception as e:
                    logger.warning("JS execution failed on %s: %s", url, e)

        html = page.content()
        browser.close()

    return BrowserFetchResult(
        url=url,
        status_code=status,
        html=html,
        content_type="text/html",
    )


def fetch_browser_paginated(
    url: str,
    *,
    wait_selector: str | None = None,
    wait_timeout_ms: int = 30_000,
    next_button_selector: str | None = None,
    max_pages: int = 10,
    user_agent: str | None = None,
) -> BrowserFetchResult:
    """Render a page and optionally click through pagination, concatenating HTML.

    Handles both postback-based paging (ASP.NET GridView) and URL-based
    paging (regular <a href> links like dbqh.quochoi.vn).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_kwargs: dict = {}
        if user_agent:
            ctx_kwargs["user_agent"] = user_agent
        ctx = browser.new_context(**ctx_kwargs)
        page = ctx.new_page()

        resp = page.goto(url, wait_until="networkidle", timeout=wait_timeout_ms)
        status = resp.status if resp else 0

        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=wait_timeout_ms)
            except Exception:
                logger.warning("Selector '%s' not found on %s", wait_selector, url)

        pages_html: list[str] = [page.content()]

        if next_button_selector:
            for i in range(max_pages - 1):
                # Find next page link — try clicking or navigating
                btn = page.query_selector(next_button_selector)
                if not btn or not btn.is_visible():
                    break
                href = btn.get_attribute("href")
                if href and href != "#" and not href.startswith("javascript:void"):
                    # URL-based pagination — navigate directly
                    page.goto(href, wait_until="networkidle", timeout=wait_timeout_ms)
                else:
                    # Postback/JS-based — click the element
                    btn.click()
                    page.wait_for_load_state("networkidle", timeout=wait_timeout_ms)

                if wait_selector:
                    try:
                        page.wait_for_selector(wait_selector, timeout=wait_timeout_ms)
                    except Exception:
                        break
                pages_html.append(page.content())
                logger.info("Paginated page %d/%d captured", i + 2, max_pages)

        browser.close()

    combined = "\n<!-- PAGE_BREAK -->\n".join(pages_html)
    return BrowserFetchResult(
        url=url,
        status_code=status,
        html=combined,
        content_type="text/html",
    )
