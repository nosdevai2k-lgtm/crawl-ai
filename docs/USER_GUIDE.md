# crawl-ai Documentation

## Overview

crawl-ai is a multi-source data crawling tool with a Streamlit web UI. It fetches, extracts, and stores structured data from web pages, RSS feeds, search engines, local files, YouTube videos, and multi-page deep crawls.

---

## Installation

```bash
cd D:\crawl-ai
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
crawl4ai-setup  # (optional) for Playwright browser
```

### Requirements
- Python 3.12+
- Dependencies: httpx, trafilatura, beautifulsoup4, feedparser, openai, yt-dlp, playwright, streamlit, pyyaml, pymongo (optional)

---

## Running the Tool

### Streamlit UI (recommended)
```bash
streamlit run app_ui.py --server.headless true
```
Open http://localhost:8501

### CLI
```bash
python -m src.cli daemon          # Run scheduled crawls from config.yaml
python -m src.cli run <source_id> # Run a single source
```

---

## Source Types

### 1. URL (Web Page / PDF)
Fetches a single URL, extracts article text, generates markdown, discovers links.

**Usage:**
- Paste any public URL
- Supports HTML pages, PDFs (text layer), JSON endpoints
- Uses ETag/Last-Modified caching to avoid redundant fetches

**Options:**
- Extract mode: `article` (clean text) or `raw` (full content)

**Example:**
```
https://docs.python.org/3/library/json.html
```

---

### 2. RSS / Atom Feed
Downloads a feed and rolls entries into a text blob.

**Usage:**
- Paste a feed URL (RSS or Atom)
- Each entry: title + link + summary

**Options:**
- Max feed entries: 1–100 (default 20)

**Example:**
```
https://feeds.bbci.co.uk/news/rss.xml
```

---

### 3. Web Search (DuckDuckGo)
Searches DuckDuckGo and returns titles, links, snippets.

**Usage:**
- Type a search query

**Options:**
- Max results: 1–25 (default 8)

**Example:**
```
Python programming news 2026
```

---

### 4. Local File
Reads a file from disk. Supports PDF, DOCX, HTML, CSV, TXT.

**Usage:**
- Enter full file path or upload via the file uploader

**Options:**
- Extract mode: `article` or `raw`

**Example:**
```
D:\documents\report.pdf
```

---

### 5. YouTube (Video / Channel / Playlist)
Downloads videos and extracts metadata using yt-dlp.

**Usage:**
- Single video: `https://www.youtube.com/watch?v=xxxxx`
- Channel playlists: `https://www.youtube.com/@ChannelName/playlists`
- Single playlist: `https://www.youtube.com/playlist?list=PLxxxxx`

**Behavior:**
- Detects if URL is a playlists page → creates subfolder per playlist
- Downloads video files (max 720p) to network storage
- Extracts: title, description, duration, views, upload date, tags, channel

**Options:**
- Max videos: 1–2000 (default 2000)

**Download location:**
```
\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl\{playlist_name}\{title} [{id}].mp4
```

**Config via .env:**
```
YOUTUBE_DOWNLOAD_DIR=\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl
```

---

### 6. Browser (JS-Rendered Pages)
Uses headless Chromium (Playwright) for pages requiring JavaScript.

**Usage:**
- For SPAs, ASP.NET pages, or sites with dynamic content
- Set `wait_selector` to wait for specific elements

**Options:**
- Wait selector: CSS selector to wait for
- Next button selector: for pagination
- Max pages: for multi-page crawls
- JS code: custom JavaScript to execute before extraction

**Config example:**
```yaml
sources:
  - id: dynamic_page
    type: browser
    url: https://example.com/spa
    wait_selector: ".content-loaded"
    js_code:
      - "document.querySelector('.load-more').click()"
      - "await new Promise(r => setTimeout(r, 2000))"
```

---

### 7. Deep Crawl (Multi-page BFS)
Crawls a start URL, follows internal links breadth-first, extracts text from each page.

**Usage:**
- Paste a starting URL (e.g., documentation site root)
- Tool discovers and crawls internal links

**Options:**
- Max depth: 1–5 (default 2)
- Max pages: 1–100 (default 20)

**Features:**
- State export/resume for crash recovery
- URL filtering (include/exclude patterns)
- Async parallel fetching

**Example:**
```
https://docs.crawl4ai.com/
```

---

## Two-Step Preview Workflow

1. **Select source type** and paste URL/query
2. **Enable "Hai bước"** checkbox (enabled by default)
3. Click **"Preview"** — fetches data without saving
4. **Review fields** — each field shown in expandable sections
5. **Select fields** to keep (multiselect)
6. Click **"Crawl & lưu"** — saves to database with selected fields

---

## Data Storage

### SQLite (default)
- Location: `data/crawl.db`
- Table: `documents`

### MongoDB (optional)
- Set `MONGODB_URI` in `.env`
- Same document structure as SQLite

### Document Schema
| Field | Description |
|-------|-------------|
| source_id | Unique identifier per source |
| fetched_at | ISO-8601 UTC timestamp |
| content_hash | SHA256 for deduplication |
| raw_text | Full extracted text |
| structured_json | LLM output (JSON) or null |
| meta | JSON with format-specific data |
| etag | HTTP ETag for caching |
| last_modified | HTTP Last-Modified |

---

## Configuration

### .env File
```env
SKIP_LLM=1                          # 1=skip LLM, 0=enable Ollama
YOUTUBE_DOWNLOAD_DIR=\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl
DATABASE_PATH=data/crawl.db
MONGODB_URI=                         # mongodb://localhost:27017
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
LLM_API_KEY=ollama
HTTP_TIMEOUT=60.0
USER_AGENT=crawl-ai/1.0 (+https://example.org) httpx
MAX_TEXT_CHARS=40000
LLM_MAX_RETRIES=3
```

### config.yaml (for scheduled crawls)
```yaml
sources:
  - id: bbc_news
    type: rss
    url: https://feeds.bbci.co.uk/news/rss.xml
    schedule_cron: "*/30 * * * *"
    rss_max_entries: 20

  - id: youtube_vtv24
    type: youtube
    url: https://www.youtube.com/@vtv24/playlists
    max_videos: 100
    schedule_cron: "0 6 * * *"

  - id: docs_site
    type: deep_crawl
    url: https://docs.example.com/
    max_depth: 3
    max_crawl_pages: 50
    schedule_cron: "0 0 * * 1"
```

---

## Advanced Features

### LLM Schema Extraction
Extract structured data from any page using a JSON schema.

```python
from src.schema_extract import extract_by_schema, SCHEMA_PRODUCT
from src.llm import make_llm_client
from src.settings import load_settings

settings = load_settings()
client = make_llm_client(settings)

items = extract_by_schema(
    client, settings.ollama_model,
    text="Product: iPhone 15 Pro - $999...",
    schema=SCHEMA_PRODUCT,
)
# Returns: [{"title": "iPhone 15 Pro", "price": "$999", ...}]
```

**Built-in schemas:** `SCHEMA_PRODUCT`, `SCHEMA_ARTICLE`, `SCHEMA_CONTACT`

---

### CSS/XPath Extraction
Extract structured data without LLM using CSS selectors.

```python
from src.css_extract import css_extract

schema = {
    "baseSelector": "div.product",
    "fields": [
        {"name": "title", "selector": "h2", "type": "text"},
        {"name": "price", "selector": ".price", "type": "text"},
        {"name": "image", "selector": "img", "type": "attribute", "attribute": "src"},
    ],
}
results = css_extract(html_content, schema)
```

---

### Fetch Cache
Avoid re-downloading the same URL within a TTL period.

```python
from src.fetch_cache import FetchCache

cache = FetchCache(ttl_sec=3600)  # 1 hour cache

# Check cache before fetching
cached = cache.get("https://example.com")
if cached:
    body = cached.body
else:
    # fetch and store
    cache.put("https://example.com", body, "text/html", 200)

# Maintenance
cache.cleanup_expired()
cache.clear()
```

---

### Deep Crawl with Resume
```python
from src.deep_crawl import deep_crawl_bfs, export_state_to_file, load_state_from_file

# Start crawl
result = deep_crawl_bfs(
    "https://docs.example.com/",
    max_depth=3,
    max_pages=50,
    on_state_change=lambda state: export_state_to_file(state, "crawl_state.json"),
)

# Resume after crash
saved = load_state_from_file("crawl_state.json")
result = deep_crawl_bfs("https://docs.example.com/", resume_state=saved)
```

---

### Async Parallel Fetch
Fetch multiple URLs concurrently.

```python
from src.async_fetch import fetch_many_sync

results = fetch_many_sync(
    ["https://a.com", "https://b.com", "https://c.com"],
    max_concurrent=10,
    timeout=30.0,
)
for r in results:
    if r.ok:
        print(f"{r.url}: {len(r.body)} bytes")
```

---

### Markdown Generation
Convert HTML to clean, LLM-ready markdown with BM25 noise filtering.

```python
from src.markdown_gen import html_to_markdown

result = html_to_markdown(html_content)
print(result.raw_markdown)   # Full markdown
print(result.fit_markdown)   # Filtered for LLM
print(result.links)          # Extracted links
```

---

### Chunking Strategies
Split large text for LLM processing.

```python
from src.chunking import chunk_by_heading, chunk_by_tokens, chunk_by_separator

# By headings (# / ## / ###)
chunks = chunk_by_heading(text, max_chars=8000)

# By token count with overlap
chunks = chunk_by_tokens(text, max_chars=4000, overlap=200)

# By custom separator
chunks = chunk_by_separator(text, separator="\n\n", max_chars=3000)
```

---

## Module Reference

| Module | Purpose |
|--------|---------|
| `src/pipeline.py` | Main orchestrator: fetch → extract → hash → LLM → store |
| `src/config_loader.py` | Load config.yaml, SourceConfig dataclass |
| `src/fetch.py` | HTTP fetching with httpx (sync) |
| `src/async_fetch.py` | Parallel async fetching |
| `src/fetch_browser.py` | Playwright headless browser + JS execution |
| `src/fetch_cache.py` | URL-based fetch cache with TTL |
| `src/extract.py` | HTML/PDF/RSS/search text extraction |
| `src/css_extract.py` | CSS selector-based structured extraction |
| `src/schema_extract.py` | LLM-based schema extraction |
| `src/markdown_gen.py` | HTML → Markdown with BM25 filtering |
| `src/chunking.py` | Text chunking strategies |
| `src/deep_crawl.py` | BFS multi-page crawling with state resume |
| `src/youtube_fetch.py` | YouTube video download via yt-dlp |
| `src/url_filters.py` | URL filter chains for deep crawl |
| `src/llm.py` | OpenAI-compatible LLM client |
| `src/storage.py` | SQLite document store |
| `src/mongo_storage.py` | MongoDB document store |
| `src/document_store.py` | Abstract store interface + factory |
| `src/field_catalog.py` | Build field catalog for preview |
| `src/settings.py` | Environment settings loader |
| `src/quick_sources.py` | Quick source config builders |
| `src/scheduler.py` | Cron-based scheduling |
| `app_ui.py` | Streamlit web interface |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| 403 Forbidden | Set proper `USER_AGENT` in `.env` |
| LLM failed after N attempts | Set `SKIP_LLM=1` or start Ollama |
| YouTube download stuck | Check network path is accessible |
| DuckDuckGo empty results | Rate limited; use RSS/URL instead |
| Playwright not found | Run `python -m playwright install chromium` |
| MongoDB connection error | Check `MONGODB_URI` in `.env` |

---

## Running Tests

```bash
python -m pytest tests/ -v
```

Current test coverage: 39 tests across all modules.
