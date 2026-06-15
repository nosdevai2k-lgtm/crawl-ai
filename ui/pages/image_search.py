"""Preset-based image search UI."""

from __future__ import annotations

import json

import streamlit as st

from src.search import PRESETS, build_index, search_images

from ui.context import UIContext


def render_image_search_section(ctx: UIContext) -> None:
    storage = ctx.storage

    st.subheader("🔀 Tìm ảnh theo preset (Scene-style pipelines)")
    st.caption("Chọn preset → nhập từ khoá + công cụ (địa điểm/ngày) → xem request body → lưới ảnh kết quả.")

    _pcols = st.columns(len(PRESETS))
    if "img_preset" not in st.session_state:
        st.session_state["img_preset"] = "tong_hop"
    for col, (pk, pv) in zip(_pcols, PRESETS.items()):
        with col:
            if st.button(
                pv["label"],
                key=f"preset_{pk}",
                use_container_width=True,
                type="primary" if st.session_state["img_preset"] == pk else "secondary",
            ):
                st.session_state["img_preset"] = pk
            st.caption(pv["hint"])

    _preset = st.session_state["img_preset"]
    sc1, sc2, sc3 = st.columns([3, 2, 1])
    with sc1:
        s_query = st.text_input("Từ khoá", placeholder="VD: biển, chùa, hạ long, đảo", key="img_q")
    with sc2:
        s_loc = st.text_input("Địa điểm (location)", placeholder="VD: đà nẵng, huế", key="img_loc")
    with sc3:
        s_topk = st.number_input("top_k", min_value=4, max_value=120, value=24, step=4, key="img_topk")
    if _preset == "tin_tuc":
        dc1, dc2 = st.columns(2)
        with dc1:
            s_dfrom = st.text_input("Date từ (YYYY-MM-DD)", key="img_dfrom")
        with dc2:
            s_dto = st.text_input("Date đến (YYYY-MM-DD)", key="img_dto")
    else:
        s_dfrom = s_dto = ""

    s_group = st.selectbox(
        "Nhóm (group)",
        ["(tất cả)", "festival", "holidays", "events", "human", "architecture"],
        key="img_group",
    )
    _tools = {
        "location": s_loc,
        "date_from": s_dfrom,
        "date_to": s_dto,
        "group": "" if s_group == "(tất cả)" else s_group,
    }
    _req_preview = {
        "query": s_query,
        "preset": _preset,
        "top_k": int(s_topk),
        "tools": {k: v for k, v in _tools.items() if v},
    }
    st.caption("Request body (verify luồng):")
    st.code(json.dumps(_req_preview, ensure_ascii=False, indent=2), language="json")

    bcol1, bcol2 = st.columns([1, 4])
    with bcol1:
        s_go = st.button("🔎 Tìm ảnh", type="primary", use_container_width=True, key="img_go")
    with bcol2:
        if st.button("♻ Rebuild index", key="img_reindex"):
            n = len(build_index())
            st.success(f"Đã build index: {n} thư mục.")

    if s_go:
        res = search_images(s_query, _preset, tools=_tools, top_k=int(s_topk), storage=storage)
        items = res["results"]
        st.markdown(f"**{len(items)}** kết quả · preset `{_preset}`")
        if _preset == "tin_tuc":
            for it in items:
                st.markdown(
                    f"**{it.get('title') or it['source_id']}** · `{it.get('date', '')}` · score {it['score']}"
                )
                if it.get("snippet"):
                    st.caption(it["snippet"])
        elif not items:
            st.info("Không có ảnh khớp. Thử từ khoá khác hoặc bỏ bớt bộ lọc.")
        else:
            ncol = 4
            rows = [items[i : i + ncol] for i in range(0, len(items), ncol)]
            for row in rows:
                cols = st.columns(ncol)
                for col, it in zip(cols, row):
                    with col:
                        try:
                            st.image(it["path"], use_container_width=True)
                        except Exception:
                            st.caption("(lỗi ảnh)")
                        st.caption(
                            f"{it['slug']} · {it['w']}×{it['h']} · {it['why']} · {it['score']}"
                        )
