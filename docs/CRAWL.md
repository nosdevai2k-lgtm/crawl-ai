# Crawl: lỗi 403, Wikipedia, và cách dùng

## Vì sao gặp `403 Forbidden` (ví dụ vi.wikipedia.org)?

Nhiều site lớn (đặc biệt **Wikimedia / Wikipedia**) chặn client nếu:

- `User-Agent` quá chung (ví dụ chỉ `python-httpx`, `curl`, `crawl-ai/1.0` ngắn), hoặc  
- Thiếu header giống trình duyệt thông thường.

Đây **không phải lỗi code**, mà là chính sách chống bot. crawl-ai đã gửi thêm `Accept`, `Accept-Language`, v.v. nhưng **bạn vẫn nên đặt `USER_AGENT` rõ ràng** theo [User-Agent policy](https://meta.wikimedia.org/wiki/User-Agent_policy) (tên tool + phiên bản + URL hoặc email liên hệ).

### Cách sửa nhanh

1. Mở file `.env` trong thư mục dự án.  
2. Thêm hoặc sửa dòng (thay URL/email bằng của bạn):

```env
USER_AGENT=crawl-ai/1.0 (+https://trang-web-cua-ban.example; email@ban.com) httpx
```

3. Khởi động lại Streamlit / CLI.

**Trên Streamlit:** trong sidebar có ô **User-Agent (HTTP)** — chỉnh trực tiếp tại đó; nếu sửa tay file `.env` thì bấm **Reload .env**.

**Lưu ý:** Không nên giả mạo chuỗi User-Agent của Chrome/Googlebot; nên dùng chuỗi **trung thực, mô tả đúng** ứng dụng của bạn.

---

## Ví dụ URL dễ thử (ít chặn hơn Wikipedia)

| Mục đích | URL ví dụ |
|----------|-----------|
| Trang tĩnh đơn giản | `https://example.com/` |
| Tài liệu HTML công khai | `https://www.w3.org/TR/html401/` |
| Trang Python docs | `https://docs.python.org/3/library/json.html` |

Wikipedia vẫn dùng được **sau khi** `USER_AGENT` hợp lệ và tôn trọng robots / tần suất.

---

## Gộp vào `config.yaml`

Xem file mẫu: [`examples/sample_sources.yaml`](examples/sample_sources.yaml) (copy mục `sources` vào `config.yaml` của bạn).

---

## Crawl nhanh (Streamlit)

1. Bật **Skip LLM** nếu chưa chạy Ollama.  
2. Chọn **URL** → dán link → **Run crawl**.  
3. Nếu 403: chỉnh `USER_AGENT` như trên, tải lại `.env` trên UI (nút **Reload .env**).

---

## API Wikipedia chính thức (tuỳ chọn)

Nếu bạn cần dữ liệu Wikipedia **ổn định**, nên dùng [MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page) thay vì scrape HTML — ngoài phạm vi mặc định của crawl-ai nhưng phù hợp production.
