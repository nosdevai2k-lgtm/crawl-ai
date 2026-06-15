"""Batch crawl from config.yaml."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.config_loader import load_config
from src.llm import make_llm_client
from src.pipeline import run_source

from ui.context import UIContext


def render_batch_section(ctx: UIContext) -> None:
    storage = ctx.storage
    settings = ctx.settings
    config_path = Path(ctx.config_path)

    st.subheader("Batch từ config.yaml")
    st.caption(
        f"Chạy một lần mọi nguồn trong `{config_path.name}` (tương đương `python -m src.cli run-once --all`)."
    )

    if not config_path.is_file():
        st.error(f"Không tìm thấy `{config_path}`. Chỉnh đường dẫn ở sidebar → LLM & batch.")
        return

    try:
        sources = load_config(config_path)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return

    if not sources:
        st.info("File config không có nguồn nào.")
        return

    preview = [
        {"id": s.id, "type": s.type, "schedule": s.schedule_cron}
        for s in sources
    ]
    st.dataframe(preview, use_container_width=True, hide_index=True)

    run = st.button(
        "▶ Chạy tất cả nguồn",
        type="primary",
        use_container_width=True,
        disabled=storage is None,
        key="batch_run_all",
    )
    if run:
        if storage is None:
            st.error("Storage chưa sẵn sàng.")
            st.stop()
        client = None if settings.skip_llm else make_llm_client(settings)
        results = []
        prog = st.progress(0.0, text="Đang chạy batch…")
        for i, src in enumerate(sources):
            prog.progress((i + 1) / len(sources), text=f"{src.id} ({i + 1}/{len(sources)})")
            try:
                res = run_source(src, storage, settings, client)
                results.append((src.id, res.changed, res.document_id, res.skipped_reason))
            except Exception as exc:  # noqa: BLE001
                results.append((src.id, False, None, str(exc)))
        prog.empty()
        ok = sum(1 for _, changed, _, _ in results if changed)
        st.success(f"Xong: **{ok}/{len(sources)}** nguồn ghi bản ghi mới.")
        for sid, changed, doc_id, reason in results:
            if changed:
                st.caption(f"✓ `{sid}` → doc_id `{doc_id}`")
            else:
                st.caption(f"– `{sid}` — {reason or 'skip'}")
