"""Export crawled documents and batch tools."""

from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from ui.context import UIContext
from ui.pages.batch import render_batch_section


def render_export_section(ctx: UIContext) -> None:
    storage = ctx.storage

    st.subheader("Export dữ liệu")
    if storage is None:
        st.warning("Storage chưa sẵn sàng — không export được.")

    exp_col1, exp_col2, exp_col3 = st.columns(3)
    with exp_col1:
        exp_limit = st.number_input("Số bản ghi", 1, 5000, 50, key="exp_limit")
    with exp_col2:
        exp_fmt = st.selectbox(
            "Format",
            ["CSV", "JSON", "Excel", "Parquet"],
            key="exp_fmt",
        )
    with exp_col3:
        exp_btn = st.button(
            "📥 Export",
            use_container_width=True,
            key="exp_btn",
            disabled=storage is None,
        )

    if exp_btn and storage:
        from src.export import export_to_csv, export_to_excel, export_to_json
        from src.export_parquet import export_recent_to_parquet

        rows = storage.list_recent(limit=int(exp_limit))
        if not rows:
            st.warning("Chưa có dữ liệu. Hãy crawl trước.")
        elif exp_fmt == "Parquet":
            try:
                with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                    out = Path(tmp.name)
                n = export_recent_to_parquet(storage, out, limit=int(exp_limit))
                data = out.read_bytes()
                out.unlink(missing_ok=True)
                st.download_button(
                    "⬇ Download Parquet",
                    data,
                    file_name="crawl_export.parquet",
                    mime="application/octet-stream",
                )
                st.success(f"Sẵn sàng tải **{n}** bản ghi (Parquet).")
            except ModuleNotFoundError as exc:
                st.error(str(exc))
        else:
            if exp_fmt == "CSV":
                data = export_to_csv(rows)
                mime, fname = "text/csv", "crawl_export.csv"
            elif exp_fmt == "JSON":
                data = export_to_json(rows)
                mime, fname = "application/json", "crawl_export.json"
            else:
                data = export_to_excel(rows)
                mime = (
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    if data[:2] != b"\xef\xbb"
                    else "text/csv"
                )
                fname = "crawl_export.xlsx" if mime.endswith("sheet") else "crawl_export.csv"
            st.download_button(f"⬇ Download {exp_fmt}", data, file_name=fname, mime=mime)
            st.success(f"Sẵn sàng tải **{len(rows)}** bản ghi.")

    st.divider()
    render_batch_section(ctx)
