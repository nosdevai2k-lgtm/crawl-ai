"""Streamlit sidebar: storage, LLM, assistant."""

from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from src.document_store import get_document_store
from src.settings import DEFAULT_USER_AGENT, Settings, load_settings
from src.ui_agent import chat_ui_assistant

from ui.context import UIContext
from ui.env import reload_env


def _render_sidebar_agent(settings: Settings) -> None:
    if "ui_agent_msgs" not in st.session_state:
        st.session_state.ui_agent_msgs = [
            {
                "role": "assistant",
                "content": (
                    "Chào bạn! Mình giúp bạn dùng crawl-ai: Preview hai bước, chọn trường, Mongo/SQLite, "
                    "lỗi 304… Gõ câu hỏi dưới đây rồi bấm **Gửi**, hoặc bấm gợi ý."
                ),
            }
        ]
    max_keep = 36
    msgs = st.session_state.ui_agent_msgs
    if len(msgs) > max_keep:
        st.session_state.ui_agent_msgs = [msgs[0]] + msgs[-(max_keep - 1) :]

    st.caption("Cần Ollama + **tắt Skip LLM** để chat hoạt động.")

    hist = st.container()
    with hist:
        for m in st.session_state.ui_agent_msgs:
            who = "**Bạn:**" if m.get("role") == "user" else "**Trợ lý:**"
            st.markdown(f"{who} {m.get('content', '')}")

    presets = [
        ("Luồng 2 bước?", "Giải thích ngắn luồng Hai bước trong crawl-ai: Preview, chọn trường, Crawl & lưu."),
        ("304 / skip?", "304 Not Modified và skipped_reason unchanged_hash là gì, xử lý ra sao trong app này?"),
        ("Mongo vs SQLite?", "Khi nào nhập MongoDB URI, khi nào dùng file SQLite?"),
        ("Wikipedia 403?", "Vì sao Wikipedia chặn và cần chỉnh User-Agent thế nào?"),
    ]
    for i, (lab, user_txt) in enumerate(presets):
        if st.button(lab, key=f"ui_ag_pre_{i}", use_container_width=True):
            st.session_state.ui_agent_msgs.append({"role": "user", "content": user_txt})
            with st.spinner("Đang trả lời…"):
                reply = chat_ui_assistant(st.session_state.ui_agent_msgs, settings=settings)
            st.session_state.ui_agent_msgs.append({"role": "assistant", "content": reply})
            st.rerun()

    if st.button("Xóa hội thoại", key="ui_agent_clear", use_container_width=True):
        st.session_state.ui_agent_msgs = [
            {"role": "assistant", "content": "Đã xóa lịch sử. Bạn cần gì tiếp theo?"}
        ]
        if "ui_agent_draft" in st.session_state:
            st.session_state["ui_agent_draft"] = ""
        st.rerun()

    st.text_input(
        "Câu hỏi",
        key="ui_agent_draft",
        placeholder="Hỏi trợ lý…",
        label_visibility="collapsed",
    )
    send = st.button("Gửi", key="ui_agent_send", use_container_width=True)
    if send:
        user_q = (st.session_state.get("ui_agent_draft") or "").strip()
        if user_q:
            st.session_state.ui_agent_msgs.append({"role": "user", "content": user_q})
            with st.spinner("Đang trả lời…"):
                reply = chat_ui_assistant(st.session_state.ui_agent_msgs, settings=settings)
            st.session_state.ui_agent_msgs.append({"role": "assistant", "content": reply})
            st.session_state["ui_agent_draft"] = ""
            st.rerun()


def render_sidebar(root: Path, config_path: Path) -> UIContext:
    """Render sidebar widgets and return shared UI context."""
    with st.sidebar:
        st.markdown("##### ⚙️ Settings")
        st.markdown("### Lưu trữ")
        st.caption("Để trống URI = SQLite. Có URI = ghi document vào MongoDB.")
        mongo_uri = st.text_input(
            "MongoDB URI (tuỳ chọn)",
            value=os.environ.get("MONGODB_URI", ""),
            placeholder="mongodb://localhost:27017",
            help="Ví dụ: mongodb://localhost:27017 — collection mặc định bên dưới.",
        )
        c_m1, c_m2 = st.columns(2)
        with c_m1:
            mongo_db = st.text_input(
                "DB name",
                value=os.environ.get("MONGODB_DATABASE", "crawl_ai"),
                label_visibility="visible",
            )
        with c_m2:
            mongo_coll = st.text_input(
                "Collection",
                value=os.environ.get("MONGODB_COLLECTION", "documents"),
            )
        os.environ["MONGODB_URI"] = mongo_uri.strip()
        os.environ["MONGODB_DATABASE"] = (mongo_db or "").strip() or "crawl_ai"
        os.environ["MONGODB_COLLECTION"] = (mongo_coll or "").strip() or "documents"

        st.divider()
        st.markdown("**SQLite** (khi không dùng Mongo)")
        db_input = st.text_input(
            "Database path",
            value=os.environ.get("DATABASE_PATH", "data/crawl.db"),
        )
        db_path = Path(db_input)
        if not db_path.is_absolute():
            db_path = root / db_path
        os.environ["DATABASE_PATH"] = str(db_path)

        st.markdown("**User-Agent**")
        ua_http = st.text_area(
            "User-Agent",
            value=os.environ.get("USER_AGENT", DEFAULT_USER_AGENT),
            height=72,
            help="Wikipedia / một số CDN yêu cầu UA mô tả rõ ràng.",
        )
        os.environ["USER_AGENT"] = (ua_http or "").strip() or DEFAULT_USER_AGENT

        with st.expander("LLM & batch", expanded=False):
            ollama_url = st.text_input(
                "Ollama URL",
                value=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
            )
            os.environ["OLLAMA_BASE_URL"] = ollama_url.rstrip("/")
            model = st.text_input("Model", value=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"))
            os.environ["OLLAMA_MODEL"] = model
            skip = st.toggle(
                "Skip LLM",
                value=os.environ.get("SKIP_LLM", "").lower() in ("1", "true", "yes"),
            )
            os.environ["SKIP_LLM"] = "1" if skip else "0"
            config_path = Path(
                st.text_input("config.yaml path", value=str(config_path))
            )
            st.caption("`docs/CRAWL.md` — 403 / Wikipedia")
            if st.button("Reload .env", use_container_width=True):
                reload_env(root)
                st.rerun()

        storage_error: str | None = None
        settings = load_settings(root / ".env" if (root / ".env").is_file() else None)
        try:
            storage = get_document_store(settings)
        except Exception as exc:  # noqa: BLE001
            if settings.mongodb_uri:
                storage = None
                storage_error = (
                    "Không kết nối được MongoDB và app đang ở chế độ **Mongo bắt buộc** "
                    "(không fallback SQLite).\n\n"
                    f"Lỗi: `{type(exc).__name__}: {exc}`"
                )
            else:
                raise

        st.divider()
        with st.expander("Trợ lý AI — hỏi cách dùng app", expanded=False):
            st.caption("**Trợ lý** — giải thích mục A–E, lỗi 304, Mongo…")
            _render_sidebar_agent(settings)

    return UIContext(
        root=root,
        settings=settings,
        storage=storage,
        storage_error=storage_error,
        config_path=config_path,
    )
