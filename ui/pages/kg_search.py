"""Unified Search — KG + ảnh + tin tức, giao diện giống Video KG."""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

from src.kg.indexer import rebuild_kg_from_store
from src.kg.overview import build_overview_graph, neighbors_vis
from src.kg.search import SAMPLE_QUERIES
from src.kg.storage import KGStorage
from src.kg.unified_search import unified_search
from src.kg.video_kg_client import video_kg_available, video_kg_stats
from src.search import PRESETS

from ui.context import UIContext
from ui.kg_viz.render import render_vkg_panel


_VKG_CSS = """
<style>
.kg-bar label, .kg-bar .stMarkdown p { color:#cdd6e4 !important; font-size:13px; }
</style>
"""


def _apply_sample(entities: str = "", topics: str = "") -> None:
    st.session_state["kg_entities"] = entities
    st.session_state["kg_topics"] = topics
    st.session_state["kg_do_search"] = True


def _run_unified_search(ctx: UIContext, *, vkg_ok: bool) -> None:
    storage = ctx.storage
    db_path = ctx.settings.database_path
    video_kg_url = ctx.settings.video_kg_base_url
    res = unified_search(
        db_path,
        entities=st.session_state.get("kg_entities", ""),
        topics=st.session_state.get("kg_topics", ""),
        image_query=st.session_state.get("kg_img_q", ""),
        image_preset=st.session_state.get("kg_img_preset", "tong_hop"),
        has_people=st.session_state.get("kg_has_people", "any"),
        media=st.session_state.get("kg_media", "both"),
        top_k=int(st.session_state.get("kg_topk", 30)),
        source=st.session_state.get("kg_source", "both"),
        video_kg_url=video_kg_url if vkg_ok else "",
        storage=storage,
        image_tools={"location": st.session_state.get("kg_img_loc", "")},
        include_images=bool(st.session_state.get("kg_include_images", True)),
    )
    st.session_state["kg_unified_result"] = res


def render_kg_search_section(ctx: UIContext) -> None:
    storage = ctx.storage
    db_path = ctx.settings.database_path
    video_kg_url = ctx.settings.video_kg_base_url

    st.markdown(_VKG_CSS, unsafe_allow_html=True)
    st.subheader("🔎 Search — KG · ảnh · tin tức · video")
    st.caption("Gộp KG Search + tìm ảnh preset + Video KG. Bố cục minh hoạ giống Video KG.")

    vkg_ok = video_kg_available(video_kg_url) if video_kg_url else False

    for key, default in [
        ("kg_entities", ""),
        ("kg_topics", ""),
        ("kg_img_q", ""),
        ("kg_has_people", "any"),
        ("kg_media", "both"),
        ("kg_source", "both" if vkg_ok else "local"),
        ("kg_img_preset", "tong_hop"),
        ("kg_topk", 30),
        ("kg_img_loc", ""),
        ("kg_include_images", True),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Mẫu truy vấn TRƯỚC widget (tránh lỗi session_state)
    st.markdown("**Mẫu truy vấn**")
    scols = st.columns(len(SAMPLE_QUERIES))
    for col, sample in zip(scols, SAMPLE_QUERIES):
        with col:
            st.button(
                sample["label"],
                key=f"kg_s_{sample['label'][:8]}",
                use_container_width=True,
                on_click=_apply_sample,
                kwargs={"entities": sample.get("entities", ""), "topics": sample.get("topics", "")},
            )

    hc1, hc2, hc3 = st.columns([3, 3, 2])
    with hc1:
        st.text_input(
            "Người / địa điểm (cách nhau ;)",
            placeholder="Tô Lâm; Hạ Long; Hà Nội",
            key="kg_entities",
        )
    with hc2:
        st.text_input(
            "Chủ đề / sự kiện / lễ hội (cách nhau ;)",
            placeholder="nhà ở xã hội; lễ hội",
            key="kg_topics",
        )
    with hc3:
        st.text_input(
            "Từ khoá ảnh (tuỳ chọn)",
            placeholder="biển, chùa, hạ long",
            key="kg_img_q",
        )

    rc1, rc2, rc3, rc4, rc5 = st.columns([2, 2, 2, 2, 1])
    with rc1:
        st.selectbox("Có người", ["any", "yes", "no"], key="kg_has_people")
    with rc2:
        st.selectbox("Media", ["both", "document", "image", "video", "scene"], key="kg_media")
    with rc3:
        source_opts = ["both", "local", "video_kg"] if vkg_ok else ["local"]
        st.selectbox("Nguồn KG", source_opts, key="kg_source")
    with rc4:
        st.selectbox(
            "Preset ảnh",
            list(PRESETS.keys()),
            format_func=lambda k: PRESETS[k]["label"],
            key="kg_img_preset",
        )
    with rc5:
        st.number_input("top_k", 5, 100, 30, 5, key="kg_topk")

    st.text_input("Địa điểm lọc ảnh", placeholder="đà nẵng, huế", key="kg_img_loc")
    st.checkbox("Gộp tìm ảnh theo preset (phong cảnh/địa điểm/sự kiện/nhân vật)", key="kg_include_images")

    bc1, bc2, bc3 = st.columns([1, 1, 2])
    with bc1:
        go = st.button("🔎 Tìm", type="primary", use_container_width=True, key="kg_go")
    with bc2:
        if st.button("♻ Rebuild KG", use_container_width=True, key="kg_rebuild"):
            if storage:
                with st.spinner("Rebuild…"):
                    r = rebuild_kg_from_store(db_path, storage)
                st.success(f"{r['docs']} docs · {r['entities']} entities · {r['media']} media")
    with bc3:
        st.caption("Preset ảnh tự chọn theo entity: 👤 nhân vật · 📍 địa điểm · 🎌 sự kiện · 🏞️ phong cảnh")

    auto = st.session_state.pop("kg_do_search", False)
    if go or auto:
        with st.spinner("Đang truy vấn…"):
            _run_unified_search(ctx, vkg_ok=vkg_ok)

    res = st.session_state.get("kg_unified_result")
    kg = KGStorage(db_path)
    st_stats = kg.stats()
    vline = f"{st_stats.get('nodes',0)} nodes · {st_stats.get('edges',0)} rels · {st_stats.get('media',0)} media"
    if vkg_ok:
        vs = video_kg_stats(video_kg_url)
        vline += f" · VKG {vs.get('total_nodes', '?')} nodes"

    if not res:
        overview = build_overview_graph(kg, limit_nodes=40)
        nb: dict = {}
        for n in (overview.get("nodes") or [])[:12]:
            nid = n.get("id")
            if nid:
                nb[nid] = neighbors_vis(kg, nid, limit=20)
        empty_payload = {
            "results": [],
            "notes": {},
            "graph": overview,
            "neighbors": nb,
            "stats": {"legend": []},
        }
        from src.kg.graph_format import legend_from_stats
        empty_payload["stats"]["legend"] = legend_from_stats(st_stats.get("by_label") or {})
        components.html(
            render_vkg_panel(empty_payload, stats_line=vline, height=680),
            height=700,
            scrolling=False,
        )
        return

    stats = res.get("stats") or {}
    local = stats.get("local") or st_stats
    vline = f"{local.get('nodes',0)} nodes · {local.get('edges',0)} rels · {local.get('media',0)} media"
    if vkg_ok:
        vs = video_kg_stats(video_kg_url)
        vline += f" · VKG {vs.get('total_nodes', '?')} nodes"

    with st.expander("Request JSON", expanded=False):
        st.code(json.dumps({
            "entities": st.session_state.get("kg_entities"),
            "topics": st.session_state.get("kg_topics"),
            "image_query": st.session_state.get("kg_img_q"),
            "preset": st.session_state.get("kg_img_preset"),
            "source": st.session_state.get("kg_source"),
            "count": res.get("count"),
        }, ensure_ascii=False, indent=2), language="json")

    components.html(
        render_vkg_panel(
            res,
            entities=st.session_state.get("kg_entities", ""),
            topics=st.session_state.get("kg_topics", ""),
            stats_line=vline,
            height=680,
        ),
        height=700,
        scrolling=False,
    )
