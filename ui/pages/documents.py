"""Browse crawled documents in the store."""

from __future__ import annotations

import json

import streamlit as st

from ui.context import UIContext


def render_documents_section(ctx: UIContext) -> None:
    storage = ctx.storage

    st.subheader("Documents")
    st.caption("Xem bản ghi gần đây trong SQLite hoặc MongoDB (theo cấu hình sidebar).")

    if storage is None:
        st.warning("Storage chưa sẵn sàng — kiểm tra MongoDB URI hoặc đường dẫn SQLite.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        limit = st.number_input("Số bản ghi", 1, 500, 50, key="doc_limit")
    with c2:
        source_filter = st.text_input(
            "Lọc source_id (tuỳ chọn)",
            placeholder="url_abc…",
            key="doc_source_filter",
        )
    with c3:
        refresh = st.button("↻ Làm mới", use_container_width=True, key="doc_refresh")

    if refresh:
        st.rerun()

    rows = storage.list_recent(limit=int(limit))
    if source_filter.strip():
        needle = source_filter.strip().lower()
        rows = [r for r in rows if needle in str(r.source_id).lower()]

    if not rows:
        st.info("Chưa có document nào — hãy crawl trước ở tab **Crawl**.")
        return

    table_rows = []
    for r in rows:
        meta = r.meta or {}
        title = ""
        summary = ""
        primary_topic = ""
        try:
            if r.structured_json:
                obj = json.loads(r.structured_json)
                if isinstance(obj, dict):
                    title = str(obj.get("title") or "")
                    summary = str(obj.get("summary") or "")[:200]
                    primary_topic = str(obj.get("primary_topic") or "")
        except json.JSONDecodeError:
            pass
        url = (
            meta.get("fetched_url")
            or meta.get("youtube_url")
            or meta.get("feed_url")
            or meta.get("start_url")
            or meta.get("query")
            or ""
        )
        table_rows.append(
            {
                "id": r.id,
                "source_id": r.source_id,
                "fetched_at": r.fetched_at,
                "title": title[:120],
                "primary_topic": primary_topic,
                "format": meta.get("format", ""),
                "url_or_query": str(url)[:120],
                "chars": len(r.raw_text or ""),
            }
        )

    st.dataframe(table_rows, use_container_width=True, hide_index=True)
    st.caption(f"Hiển thị **{len(rows)}** bản ghi · bấm expander bên dưới để xem chi tiết.")

    for r in rows[: min(len(rows), 25)]:
        meta = r.meta or {}
        title = r.source_id
        try:
            if r.structured_json:
                obj = json.loads(r.structured_json)
                if isinstance(obj, dict) and obj.get("title"):
                    title = str(obj["title"])
        except json.JSONDecodeError:
            pass
        with st.expander(f"`{r.id}` · {title}", expanded=False):
            st.markdown(f"**source_id:** `{r.source_id}` · **fetched_at:** {r.fetched_at}")
            st.markdown(f"**hash:** `{r.content_hash[:16]}…`")
            if meta:
                st.json({k: meta[k] for k in list(meta.keys())[:20]})
            if r.structured_json:
                st.markdown("**Structured (LLM)**")
                try:
                    st.json(json.loads(r.structured_json))
                except json.JSONDecodeError:
                    st.code(r.structured_json[:8000])
            preview = (r.raw_text or "")[:6000]
            if len(r.raw_text or "") > 6000:
                preview += "\n\n… [cắt bớt cho UI] …"
            st.text_area("raw_text", value=preview, height=220, disabled=True, label_visibility="collapsed")
