"""UI copy and crawl mode definitions."""

from __future__ import annotations

# (UI label, pipeline kind, placeholder, scope blurb)
CRAWL_MODES: list[tuple[str, str, str, str]] = [
    (
        "One public web page or PDF (paste URL)",
        "URL",
        "https://docs.python.org/3/library/json.html",
        "Fetches **one** URL: HTML pages **or** `application/pdf` (text layer via built-in PDF reader). "
        "News, docs, Wikipedia, static pages. Not a headless browser (weak on heavy SPAs). "
        "Scanned PDFs without a text layer only get a short notice — use OCR elsewhere if needed.",
    ),
    (
        "RSS / Atom feed (paste a feed URL)",
        "RSS",
        "https://feeds.bbci.co.uk/news/rss.xml",
        "Downloads the **feed document** and rolls recent `<item>` entries into one text blob. "
        "It does **not** crawl each article URL by default.",
    ),
    (
        "Web search (type a query)",
        "Search",
        "renewable energy Europe",
        "Uses **DuckDuckGo** text results (titles, links, snippets). Rate limits and provider "
        "terms apply; not a substitute for a licensed search API.",
    ),
    (
        "Local file (PDF, HTML, CSV, TXT…)",
        "File",
        "D:\\path\\to\\document.pdf",
        "Reads a **local file** from disk. Supports PDF (text layer), HTML, CSV, and plain text. "
        "Enter the full path or upload via the file uploader below.",
    ),
    (
        "YouTube (video or channel URL)",
        "YouTube",
        "https://www.youtube.com/@ChannelName",
        "Extracts video **metadata** (title, description, duration, views, upload date) from a "
        "YouTube video URL, channel, or playlist via **yt-dlp**. Does **not** download video files.",
    ),
    (
        "Deep Crawl (multi-page BFS)",
        "DeepCrawl",
        "https://docs.example.com/",
        "Crawls a starting URL and follows **internal links** using BFS (breadth-first). "
        "Extracts text from each page up to max depth/pages. Great for documentation sites.",
    ),
]

HOW_TO_CRAWL_MD = """
### Hướng dẫn crawl (tóm tắt)

1. **Chọn loại nguồn**  
   - **Một URL / PDF**: một trang công khai.  
   - **RSS / Atom**: URL file feed (không tự mở từng bài trừ khi bạn thêm nguồn khác).  
   - **Tìm kiếm**: câu query → snippet DuckDuckGo.

2. **Hai bước (khuyến nghị)**  
   Bật checkbox → **Preview** (chưa ghi DB) → xem từng trường → **chọn trường** → **Crawl & lưu**.  
   Tắt checkbox → **Run crawl** một lần lưu ngay.

3. **Gợi ý nguồn (AI)** (tab **Auto-crawl**)  
   Nhập mục tiêu → **Tạo gợi ý** → xem URL / feed / query đề xuất → **Áp dụng** (điền lên tab Crawl) hoặc **Crawl mục đã chọn**. Cần **Ollama** và **tắt Skip LLM**. Kết quả chỉ là gợi ý — luôn kiểm tra URL/query.

4. **Tự cập nhật khi nội dung đổi**  
   Mỗi lần chạy `run_source`, app so **ETag / Last-Modified** (URL) và **hash nội dung** so với bản mới nhất cùng `source_id`.  
   - Trùng hash hoặc **304** → không ghi bản mới.  
   - Khác → thêm document mới (append).  
   Để chạy định kỳ: cấu hình `schedule_cron` trong `config.yaml` và chạy:  
   `python -m src.cli daemon` (từ thư mục dự án, có `config.yaml`).

5. **Pháp lý & lịch sự**  
   Tuân **robots.txt**, điều khoản site, không crawl hàng loạt / dữ liệu nhạy cảm trái phép.

6. **Gom tin / nghiên cứu chạy nền**  
   Tab **Export & Batch** hoặc `python -m src.cli daemon`; file mẫu `config.research_digest.example.yaml`; script `scripts/research_auto_crawl.py`.

---
*English:* Pick source type → **two-step Preview** to confirm fields → use **AI source suggestions** (section above) then **Apply** to the form; you still **Preview/Run** manually → **re-runs** or `python -m src.cli daemon` / **`scripts/research_auto_crawl.py`** pick up changes via **304 / content hash**.
"""

DISPLAY_PREVIEW_CHARS = 450_000
