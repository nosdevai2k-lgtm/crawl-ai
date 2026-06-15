"""AI-assisted auto-crawl from natural language goals."""

from __future__ import annotations

import json

import streamlit as st

from ui.context import UIContext
from ui.helpers import apply_suggestion_to_crawl_form


def _show_crawled(ctx: UIContext, items) -> None:
    """Hiện nội dung vừa crawl: title + summary + ảnh."""
    storage = ctx.storage
    for it in items:
        if not (it.result and it.result.changed and storage):
            continue
        row = storage.get_document_by_id(it.result.document_id)
        if not row:
            continue
        d = json.loads(row.structured_json or "{}")
        with st.expander(f"📄 {d.get('title') or row.source_id}", expanded=False):
            st.caption(
                f"`{row.source_id}` · "
                f"{(row.meta or {}).get('fetched_url') or (row.meta or {}).get('query') or ''}"
            )
            if d.get("summary"):
                st.write(d["summary"])
            imgs = [
                im.get("path")
                for im in (row.meta or {}).get("images") or []
                if im.get("path")
            ]
            if imgs:
                st.image(imgs[:12], width=140)


def render_auto_crawl_section(ctx: UIContext) -> None:
    settings = ctx.settings
    storage = ctx.storage

    st.subheader("Auto-crawl bằng prompt (AI gợi ý nguồn → chọn → crawl)")
    st.caption(
        "Cần **Ollama** + **tắt Skip LLM**. Nhập mục tiêu → **Tạo gợi ý** → chọn nguồn muốn giữ → **Crawl mục đã chọn**."
    )

    ac_goal = st.text_area(
        "Mục tiêu crawl",
        height=90,
        placeholder="VD: theo dõi tin năng lượng tái tạo ở châu Âu",
        key="auto_crawl_goal",
    )
    ac_c1, ac_c2 = st.columns([2, 1])
    with ac_c1:
        ac_seed = st.text_input("Seed URL (tuỳ chọn)", placeholder="https://...", key="auto_crawl_seed")
    with ac_c2:
        ac_imgs = st.checkbox("Tải ảnh", value=False, key="auto_crawl_imgs")
        ac_expand = st.checkbox(
            "Mở rộng link (theo link cùng trang để lấy thêm text + ảnh)",
            value=False,
            key="auto_crawl_expand",
        )

    ac_b1, ac_b2 = st.columns(2)
    with ac_b1:
        ac_plan = st.button(
            "🔎 Tạo gợi ý",
            use_container_width=True,
            disabled=storage is None,
            key="auto_crawl_plan_btn",
        )
    with ac_b2:
        ac_run = st.button(
            "✨ Crawl thẳng (bỏ chọn)",
            use_container_width=True,
            disabled=storage is None,
            key="auto_crawl_btn",
        )

    if ac_plan:
        if settings.skip_llm:
            st.warning("Đang bật **Skip LLM** — tắt ở sidebar để dùng auto-crawl.")
        elif not (ac_goal or "").strip():
            st.warning("Nhập mục tiêu crawl.")
        else:
            from src.auto_crawl import plan_crawl

            try:
                with st.spinner("LLM gợi ý nguồn…"):
                    st.session_state["auto_crawl_suggestions"] = plan_crawl(
                        ac_goal, settings, seed_url=(ac_seed or "").strip() or None
                    )
            except Exception as exc:  # noqa: BLE001
                st.session_state.pop("auto_crawl_suggestions", None)
                st.error(str(exc))

    suggestions = st.session_state.get("auto_crawl_suggestions")
    if suggestions:
        st.markdown("**Gợi ý nguồn** — bỏ tick nguồn không muốn crawl, hoặc **Áp dụng** lên tab Crawl:")
        chosen = []
        for i, sug in enumerate(suggestions):
            row1, row2 = st.columns([5, 1])
            with row1:
                lab = f"**{sug.get('kind')}** · {sug.get('title') or sug.get('value')}"
                keep = st.checkbox(lab, value=True, key=f"auto_crawl_pick_{i}")
                st.caption(f"`{sug.get('value')}` — {sug.get('rationale', '')}")
            with row2:
                if st.button("Áp dụng", key=f"auto_crawl_apply_{i}", use_container_width=True):
                    if apply_suggestion_to_crawl_form(sug):
                        st.toast("Đã áp dụng lên tab Crawl", icon="✅")
                        st.rerun()
                    else:
                        st.warning("Chỉ áp dụng được URL / RSS / Search.")
            if keep:
                chosen.append(sug)
        if st.button(
            f"✅ Crawl {len(chosen)} mục đã chọn",
            type="primary",
            use_container_width=True,
            disabled=not chosen,
            key="auto_crawl_go_btn",
        ):
            from src.auto_crawl import crawl_suggestions

            try:
                with st.spinner("Đang crawl…"):
                    items = crawl_suggestions(
                        chosen,
                        storage,
                        settings,
                        crawl_images=bool(ac_imgs),
                        expand_links=bool(ac_expand),
                    )
                ok = sum(1 for it in items if it.result and it.result.changed)
                st.success(f"Xong: **{ok}/{len(items)}** nguồn lưu mới.")
                for it in items:
                    lab = f"{it.suggestion.get('kind')}: {it.suggestion.get('value')}"
                    if it.error:
                        st.caption(f"✗ {lab} — {it.error}")
                    elif it.result and it.result.changed:
                        st.caption(f"✓ {lab} — doc_id {it.result.document_id}")
                    else:
                        st.caption(f"– {lab} — {it.result.skipped_reason if it.result else 'no_result'}")
                _show_crawled(ctx, items)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    if ac_run:
        if storage is None:
            st.error("Storage chưa sẵn sàng.")
        elif settings.skip_llm:
            st.warning("Đang bật **Skip LLM** — tắt ở sidebar để dùng auto-crawl.")
        elif not (ac_goal or "").strip():
            st.warning("Nhập mục tiêu crawl.")
        else:
            from src.auto_crawl import auto_crawl

            try:
                with st.spinner("LLM gợi ý nguồn & crawl…"):
                    items = auto_crawl(
                        ac_goal,
                        storage,
                        settings,
                        seed_url=(ac_seed or "").strip() or None,
                        crawl_images=bool(ac_imgs),
                        expand_links=bool(ac_expand),
                    )
                ok = sum(1 for it in items if it.result and it.result.changed)
                st.success(f"Xong: **{ok}/{len(items)}** nguồn lưu mới.")
                for it in items:
                    lab = f"{it.suggestion.get('kind')}: {it.suggestion.get('value')}"
                    if it.error:
                        st.caption(f"✗ {lab} — {it.error}")
                    elif it.result and it.result.changed:
                        st.caption(f"✓ {lab} — doc_id {it.result.document_id}")
                    else:
                        st.caption(f"– {lab} — {it.result.skipped_reason if it.result else 'no_result'}")
                _show_crawled(ctx, items)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))
