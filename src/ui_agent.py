"""Trợ lý chat cho UI Streamlit (Ollama API tương thích OpenAI)."""

from __future__ import annotations

from typing import Any

from openai import OpenAI

from .settings import Settings

UI_AGENT_SYSTEM = """Bạn là trợ lý giao diện ứng dụng **crawl-ai** (ưu tiên tiếng Việt; có thể dùng tiếng Anh ngắn).

Bạn **không** crawl hay gọi HTTP thay người dùng; chỉ hướng dẫn nút và luồng trong app.

Nội dung cần nắm:
- Ba chế độ: **một URL/PDF**, **RSS/Atom**, **tìm kiếm DuckDuckGo** (snippet).
- **Hai bước (mặc định)**: (1) Preview — chỉ tải, xem đủ từng trường; (2) chọn trường trong multiselect; (3) nút «Crawl & lưu» ghi MongoDB hoặc SQLite và có thể chạy LLM cấu trúc nội dung.
- Tắt «Hai bước» → một nút lưu ngay.
- **Lưu trữ**: để trống Mongo URI → SQLite file; có URI → ghi collection đã chọn.
- **User-Agent**: Wikipedia/CDN có thể chặn bot; xem gợi ý trong app/docs.
- **Skip LLM**: bật thì không gọi model khi crawl; trợ lý chat vẫn cần Ollama **tắt Skip** để trả lời.
- **Gợi ý nguồn (AI)** ở tab **Auto-crawl**: mục tiêu + tuỳ chọn URL gốc → **Tạo gợi ý** → **Áp dụng** (điền tab Crawl) hoặc **Crawl mục đã chọn**.
- Lỗi thường gặp: **304 / not_modified**, **unchanged_hash** (nội dung giống lần trước), PDF scan không có lớp chữ, SPA/login.

Quy tắc:
- Trả lời súc tích; dùng danh sách đánh số khi có nhiều bước.
- Không khuyến khích vi phạm robots.txt, điều khoản site, hay bản quyền.
- Nếu thiếu ngữ cảnh (URL cụ thể, thông báo lỗi), hỏi lại một câu ngắn.
"""


def _trim_chat_messages(
    messages: list[dict[str, Any]], *, max_user_assistant_chars: int
) -> list[dict[str, str]]:
    """Giữ các tin nhắn cuối để không vượt ngân sách token."""
    out: list[dict[str, str]] = []
    total = 0
    for m in reversed(messages):
        role = str(m.get("role") or "")
        if role not in ("user", "assistant"):
            continue
        c = str(m.get("content") or "")
        if len(c) > 12_000:
            c = c[:11_800] + "\n...[đã cắt để gọn]..."
        if total + len(c) > max_user_assistant_chars and out:
            break
        out.append({"role": role, "content": c})
        total += len(c)
    return list(reversed(out))


def chat_ui_assistant(
    messages: list[dict[str, Any]],
    *,
    settings: Settings,
    max_output_tokens: int = 900,
) -> str:
    if settings.skip_llm:
        return (
            "Đang bật **Skip LLM** trong sidebar → pipeline không gọi model. "
            "Để **trợ lý chat** hoạt động, hãy **tắt Skip LLM**, bật Ollama, chọn đúng **Model**, rồi gửi lại tin nhắn."
        )
    client = OpenAI(
        base_url=settings.ollama_base_url,
        api_key=settings.ollama_api_key,
    )
    trimmed = _trim_chat_messages(messages, max_user_assistant_chars=28_000)
    try:
        resp = client.chat.completions.create(
            model=settings.ollama_model,
            messages=[
                {"role": "system", "content": UI_AGENT_SYSTEM},
                *trimmed,
            ],
            temperature=0.35,
            max_tokens=max_output_tokens,
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or "(Model trả về nội dung trống.)"
    except Exception as exc:  # noqa: BLE001
        return (
            f"**Lỗi gọi LLM:** `{type(exc).__name__}: {exc}`\n\n"
            "Kiểm tra **Ollama URL**, model đã `ollama pull`, và không chặn firewall."
        )
