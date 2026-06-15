#!/usr/bin/env python3
"""
End-to-end test: crawl dbqh.quochoi.vn → LLM structuring → MongoDB.

Requires one of:
  - Ollama running locally (default)
  - Groq API key:  set LLM_BASE_URL=https://api.groq.com/openai/v1
                        LLM_MODEL=llama-3.1-8b-instant
                        LLM_API_KEY=gsk_...
  - Any OpenAI-compatible endpoint

Usage:
  # With Groq (free):
  set LLM_BASE_URL=https://api.groq.com/openai/v1
  set LLM_MODEL=llama-3.1-8b-instant
  set LLM_API_KEY=gsk_your_key_here
  set MONGODB_URI=mongodb://localhost:27017
  python scripts/test_llm_crawl.py

  # With Ollama:
  set MONGODB_URI=mongodb://localhost:27017
  python scripts/test_llm_crawl.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(override=False)

from src.settings import load_settings
from src.llm import make_llm_client, structure_content
from src.fetch_browser import fetch_browser
from src.extract import extract_from_html


def main() -> int:
    settings = load_settings()
    print(f"LLM endpoint: {settings.ollama_base_url}")
    print(f"LLM model:    {settings.ollama_model}")
    print()

    # Step 1: Crawl
    print("=" * 60)
    print("STEP 1: Crawling dbqh.quochoi.vn/VI/Daibieu.aspx ...")
    t0 = time.perf_counter()
    result = fetch_browser(
        "https://dbqh.quochoi.vn/VI/Daibieu.aspx",
        wait_selector="#list",
        user_agent=settings.user_agent,
    )
    text = extract_from_html(result.html, mode="raw")
    elapsed = time.perf_counter() - t0
    print(f"  Crawled: {len(text)} chars in {elapsed:.1f}s")
    print(f"  First 200 chars: {text[:200]}")
    print()

    # Step 2: LLM structuring
    print("=" * 60)
    print("STEP 2: Sending to LLM for structuring ...")
    # Clip to reasonable size for the model
    clipped = text[:min(len(text), settings.max_text_chars)]
    client = make_llm_client(settings)

    fetch_context = {
        "source_id": "test_dbqh_daibieu",
        "source_config_type": "browser",
        "config_url": "https://dbqh.quochoi.vn/VI/Daibieu.aspx",
        "fetched_url": result.url,
        "status": result.status_code,
        "format": "browser_rendered",
    }

    t0 = time.perf_counter()
    try:
        structured = structure_content(
            client,
            settings.ollama_model,
            clipped,
            max_retries=settings.llm_max_retries,
            backoff_sec=settings.llm_retry_backoff_sec,
            fetch_context=fetch_context,
        )
        elapsed = time.perf_counter() - t0
        print(f"  LLM responded in {elapsed:.1f}s")
        print()
        print("=" * 60)
        print("STEP 3: Structured output from LLM:")
        print(json.dumps(structured, ensure_ascii=False, indent=2)[:3000])
        print()

        # Step 3: Save to MongoDB if configured
        if settings.mongodb_uri:
            print("=" * 60)
            print("STEP 4: Saving to MongoDB ...")
            from src.document_store import get_document_store
            storage = get_document_store(settings)
            doc_id = storage.insert_document(
                source_id="test_llm_dbqh",
                content_hash="test_" + str(int(time.time())),
                raw_text=clipped,
                structured_json=json.dumps(structured, ensure_ascii=False),
                meta=fetch_context,
            )
            print(f"  Saved doc_id: {doc_id}")
            print()
            # Verify
            doc = storage.get_document_by_id(doc_id)
            if doc and doc.structured_json:
                saved = json.loads(doc.structured_json)
                print(f"  Verified: title = {saved.get('title', '?')}")
                print(f"  Verified: {len(saved.get('key_entities', []))} entities extracted")
        print()
        print("SUCCESS - End-to-end test passed!")
        return 0

    except Exception as e:
        elapsed = time.perf_counter() - t0
        print(f"  FAILED after {elapsed:.1f}s: {e}")
        print()
        print("Troubleshooting:")
        print(f"  - Is LLM endpoint reachable? {settings.ollama_base_url}")
        print("  - For Groq (free): set LLM_BASE_URL=https://api.groq.com/openai/v1")
        print("  - For Groq: set LLM_MODEL=llama-3.1-8b-instant")
        print("  - For Groq: set LLM_API_KEY=gsk_... (get from console.groq.com)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
