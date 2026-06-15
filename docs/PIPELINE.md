# crawl-ai Pipeline — Data Types & Flow

## Overview

```
INPUT (URL/RSS/Search/File/YouTube)
  │
  ▼
┌─────────────┐
│  FETCH      │  Retrieve raw data based on source type
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  EXTRACT    │  Parse content → text + metadata
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  HASH/DEDUP │  SHA256 compare → skip if unchanged
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  LLM (opt)  │  Structure/summarize via Ollama (skip for YouTube)
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  STORE (DB) │  SQLite or MongoDB → documents table
└─────────────┘
```

---

## Data Types

### 1. URL (Web Page / PDF)

| Step | Detail |
|------|--------|
| Fetch | HTTP GET with ETag/Last-Modified caching |
| Extract | HTML → trafilatura/BeautifulSoup article extraction; PDF → pypdf text layer |
| Fields stored | `raw_text`, `fetched_url`, `content_type`, `markdown`, `links_discovered` |
| LLM | Summarize, extract entities, dates, locations |
| DB record | `source_id`, `content_hash`, `raw_text`, `structured_json`, `meta` |

### 2. RSS / Atom Feed

| Step | Detail |
|------|--------|
| Fetch | HTTP GET feed XML |
| Extract | feedparser → roll N entries into text blob (title + link + summary per entry) |
| Fields stored | `raw_text`, `feed_url`, `format=rss` |
| LLM | Summarize all entries |
| DB record | Same schema, `meta.format = "rss"` |

### 3. Web Search (DuckDuckGo)

| Step | Detail |
|------|--------|
| Fetch | DuckDuckGo text search API |
| Extract | Titles + URLs + snippets → plain text |
| Fields stored | `raw_text`, `query`, `max_results` |
| LLM | Summarize search results |
| DB record | Same schema, `meta.format = "search"` |

### 4. Local File (PDF/HTML/CSV/TXT/DOCX)

| Step | Detail |
|------|--------|
| Fetch | Read from disk path |
| Extract | PDF → pypdf; DOCX → python-docx; HTML → article extract; CSV/TXT → raw |
| Fields stored | `raw_text`, `file_path`, `format`, `file_size`; CSV also gets `col::ColumnName` fields |
| LLM | Summarize content |
| DB record | Same schema, `meta.format = "pdf"/"docx"/"csv"/"text"` |

### 5. YouTube (Video / Channel / Playlist)

| Step | Detail |
|------|--------|
| Fetch | yt-dlp: detect URL type (single video / playlist / playlists page) |
| Download | Save `.mp4` to `\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl\{playlist_name}\` |
| Extract | Per-video metadata: title, description, duration, views, upload_date, tags, channel |
| Fields stored | `raw_text` (summary), `meta.videos[]` (full per-video data with file_path) |
| LLM | **Skipped** (auto) |
| DB record | `meta.format = "youtube"`, `meta.video_count`, `meta.videos[].{all fields}` |

---

## DB Schema (SQLite)

```sql
CREATE TABLE documents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id       TEXT NOT NULL,        -- unique ID per source config
    fetched_at      TEXT NOT NULL,        -- ISO-8601 UTC timestamp
    content_hash    TEXT NOT NULL,        -- SHA256 of normalized text (dedup)
    raw_text        TEXT NOT NULL,        -- full extracted text (capped ~1.5M chars)
    structured_json TEXT,                 -- LLM output (JSON) or null
    meta            TEXT NOT NULL,        -- JSON: format, urls, fields, videos, etc.
    etag            TEXT,                 -- HTTP ETag for caching
    last_modified   TEXT                  -- HTTP Last-Modified for caching
);
```

## DB Schema (MongoDB)

Same fields as above, stored as BSON documents in configured collection.

---

## Two-Step Preview Flow

```
User pastes input
       │
       ▼
[Preview button] → collect_payload() → build_field_catalog()
       │
       ▼
UI shows all fields (raw_text, meta::url, col::X, video_N::title, etc.)
       │
       ▼
User selects which fields to keep
       │
       ▼
[Crawl & Save button] → run_source() with extra_meta:
   • user_extract_fields: [list of chosen field keys]
   • extract_full_by_field: {field_key: full_content}
   • Writes to DB
```

---

## Config (config.yaml)

```yaml
sources:
  - id: my_youtube
    type: youtube
    url: https://www.youtube.com/@vtv24/playlists
    max_videos: 2000
    schedule_cron: "0 6 * * *"

  - id: my_page
    type: url
    url: https://example.com/article
    extract: article
    schedule_cron: "0 * * * *"

  - id: my_feed
    type: rss
    url: https://feeds.bbci.co.uk/news/rss.xml
    rss_max_entries: 20
    schedule_cron: "*/30 * * * *"

  - id: my_search
    type: search
    query: "AI news 2026"
    max_results: 10
    schedule_cron: "0 9 * * *"

  - id: my_file
    type: file
    file_path: D:\docs\report.pdf
    extract: raw
    schedule_cron: "0 * * * *"
```

---

## Environment (.env)

```env
SKIP_LLM=1                          # 1=skip Ollama, 0=enable LLM structuring
YOUTUBE_DOWNLOAD_DIR=\\172.16.201.171\Demo\INGEST\video_test\Service_AI\Crawl
DATABASE_PATH=data/crawl.db
MONGODB_URI=                         # set for MongoDB storage
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
```
