# crawl-ai

Crawl URL / RSS / tìm kiếm (DuckDuckGo) / **file cục bộ** (PDF, HTML, CSV, TXT…), trích nội dung, so khớp thay đổi (hash + ETag), và tóm tắt có cấu trúc qua **Ollama** (API tương thích OpenAI).

## Model mặc định

- Biến môi trường **`OLLAMA_MODEL`**, mặc định trong code: **`qwen2.5:7b`** (Ollama).
- Bạn có thể đổi sang bất kỳ model đã `ollama pull` (ví dụ `qwen2.5:9b`, `qwen2.5:14b`, `llama3.2`, …) trong `.env` hoặc trên giao diện web.

## Yêu cầu

- Python 3.10+
- [Ollama](https://ollama.com) chạy local (trừ khi bật `SKIP_LLM=1`)

## Cài đặt

```powershell
cd D:\crawl-ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Chỉnh `config.yaml` (danh sách `sources`) và `.env` nếu cần. Trang **hướng dẫn crawl / lỗi 403 / Wikipedia**: [docs/CRAWL.md](docs/CRAWL.md). Mẫu nguồn: [examples/sample_sources.yaml](examples/sample_sources.yaml).

Để chạy thử crawl + SQLite **không cần** Ollama: đặt `SKIP_LLM=1` trong `.env`, hoặc bật tùy chọn tương ứng trên UI.

### MongoDB (tuỳ chọn)

Nếu bạn đã cài MongoDB trên máy, đặt trong `.env`:

- `MONGODB_URI` — ví dụ `mongodb://localhost:27017` (khi có giá trị, app dùng Mongo thay cho SQLite cho bảng documents).
- `MONGODB_DATABASE` — mặc định `crawl_ai`.
- `MONGODB_COLLECTION` — mặc định `documents`.

Cần gói `pymongo` (đã có trong `requirements.txt`). Trên UI Streamlit có thể ghi tạm URI/database/collection vào biến môi trường trong phiên làm việc.

## Giao diện web (Streamlit)

Bố cục gọn, **dark mode** (Streamlit theme + CSS), nút chính nổi bật. Nhãn giao diện tiếng Anh; sidebar có nhóm **Lưu trữ** (Mongo URI / SQLite). Theme: [`.streamlit/config.toml`](.streamlit/config.toml).

```powershell
cd D:\crawl-ai
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app_ui.py
```

Trình duyệt: sidebar (DB / Mongo, User-Agent, model). Thanh tab: **Crawl** · **Documents** · **Auto-crawl** · **Images** · **Export & Batch**.

- **Crawl**: chọn loại nguồn → dán URL/query/file → Preview hai bước hoặc Run crawl.
- **Documents**: bảng + chi tiết bản ghi gần đây (SQLite/Mongo).
- **Auto-crawl**: gợi ý nguồn bằng LLM → **Áp dụng** lên tab Crawl hoặc crawl hàng loạt.
- **Export & Batch**: CSV / JSON / Excel / Parquet + chạy một lần mọi nguồn trong `config.yaml`.

## Kiểm thử (pytest)

```powershell
cd D:\crawl-ai
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -v
```

175 test — không cần mạng/Ollama cho phần lớn; `test_export_parquet` cần `pyarrow`.

Kết quả có thể ghi log UTF-8: `logs\pytest_latest.log` (chạy lệnh dưới đây sẽ ghi đè file log mỗi lần).

```powershell
cd D:\crawl-ai
$log = "logs\pytest_latest.log"
"=== crawl-ai pytest $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File $log -Encoding utf8
.\.venv\Scripts\python.exe -m pytest tests\test_crawl.py -v --tb=short 2>&1 | Out-File $log -Append -Encoding utf8
```

## CLI

```powershell
python -m src.cli list-sources
python -m src.cli import-opml .\feeds.opml --config .\config.yaml
python -m src.cli import-opml .\feeds.opml --dry-run
python -m src.cli export-parquet --out .\data\export.parquet --limit 5000
python -m src.cli run-once --source example_static
python -m src.cli run-once --all
python -m src.cli daemon
```

- **import-opml**: đọc mọi `<outline xmlUrl="...">`, thêm nguồn `type: rss` vào `config.yaml` (bỏ trùng URL/id). `--dry-run` in YAML mẫu.
- **export-parquet**: đọc `list_recent` từ store hiện tại (SQLite/Mongo theo `.env`), cột gồm `title`, `summary`, `topics`, `primary_topic`, `content_kind`, …

JSON từ LLM (khi không `SKIP_LLM`) có thêm **`topics`** (mảng 1–5 nhãn) và **`primary_topic`** (một nhãn chính); pipeline luôn `setdefault` nếu model thiếu key.

- **File cục bộ**: chọn **Local file** trên UI (hoặc `type: file` trong YAML) → nhập đường dẫn hoặc upload. Hỗ trợ `.pdf` (lớp chữ), `.html/.htm`, `.csv`, `.txt`, `.md`, `.json`. Ví dụ YAML:

```yaml
sources:
  - id: local_report
    type: file
    file_path: D:\docs\report.pdf
    schedule_cron: "0 8 * * *"
    extract: raw
```

- **Google Sheets**: URL dạng `docs.google.com/spreadsheets/d/<id>/edit...` được tự đổi sang **CSV export** công khai (`/export?format=csv&gid=...`) để lấy **toàn bộ ô** (sheet phải public / “Anyone with the link can view”). Ví dụ chạy một lần lên Mongo: [`examples/ingest_google_sheet_to_mongo.py`](examples/ingest_google_sheet_to_mongo.py).

Lưu trữ documents: **SQLite** mặc định (`data/crawl.db`, tạo thư mục `data` tự động), hoặc **MongoDB** khi đặt `MONGODB_URI`.

### Crawl tự động (tin / nghiên cứu nền)

- **Daemon theo cron từng nguồn** (khuyến nghị): `python -m src.cli daemon --config config.yaml` — mỗi `source` có `schedule_cron` riêng trong YAML.
- **Script vòng lặp** (mỗi *X* giây gọi lại tất cả nguồn):  
  `python scripts/research_auto_crawl.py --config config.research_digest.example.yaml --interval-sec 1800`  
  Một vòng rồi thoát: thêm `--once` (tiện gắn Task Scheduler / cron hệ điều hành).
- **File mẫu** RSS + URL + search: [`config.research_digest.example.yaml`](config.research_digest.example.yaml).

Khi nội dung **không đổi**, pipeline **bỏ qua** ghi (hash / 304) — đó là dấu hiệu cơ chế cập nhật đang hoạt động.

## Nhận diện khuôn mặt & match sự kiện

Nhận diện khuôn mặt dùng **OpenCV** (YuNet detect + SFace embedding) — không cần biên dịch.

```powershell
pip install opencv-python-headless
python scripts/download_face_models.py   # tải model vào data/models/ (~37MB)
```

- **Thu thập + kiểm tra mặt**: `python -m src.cli harvest-faces "Tô Lâm" --en "To Lam" --verify`
  (`--verify` bỏ ảnh không có mặt / sai người theo embedding).
- **Dọn thư mục mặt đã có**: `python -m src.cli clean-faces` (thêm `--apply` để chuyển ảnh sai vào `_rejected/`).
- **Nối mặt với KG**: `python -m src.cli link-faces` → cạnh `Person --HAS_FACE--> FaceSet`.
- **Nhận diện → sự kiện**: `python -m src.cli identify-face ảnh.jpg` hoặc tab **🔍 Nhận diện mặt → sự kiện** trên UI.
  Cạnh `Person --ATTENDED--> Event` được tạo khi index tài liệu; bấm **Rebuild KG** để cập nhật dữ liệu cũ.

Nếu thiếu opencv/model, các tính năng mặt **tự tắt** (degrade gracefully), phần còn lại vẫn chạy.

## Ưu tiên nguồn chuẩn

`src/source_trust.py` xếp hạng domain theo độ tin cậy (official `.gov.vn`/chinhphu.vn → press báo lớn →
reference → neutral → low → blocked). Kết quả tìm kiếm DuckDuckGo được **xếp lại theo trust** và bỏ
domain spam; `run-once --all` / batch chạy **nguồn ưu tiên cao trước**. Đặt `priority: <int>` cho từng
source trong `config.yaml` để ghi đè.

## Giới hạn

- Trang cần JavaScript nặng: dùng `type: browser` (Playwright headless Chromium) — đã hỗ trợ.
- File cục bộ: hỗ trợ PDF (lớp chữ), HTML, CSV, TXT. PDF scan (chỉ ảnh) cần OCR bên ngoài.
- Tìm kiếm DuckDuckGo tuân thủ TOS, nên giữ tần suất cron hợp lý.
