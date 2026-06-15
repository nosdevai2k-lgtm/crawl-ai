"""Main crawl form and two-step preview workflow."""

from __future__ import annotations

import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from src.config_loader import source_config_as_dict, source_config_from_dict
from src.field_catalog import build_field_catalog
from src.pipeline import collect_payload, run_source

from ui.constants import CRAWL_MODES, DISPLAY_PREVIEW_CHARS
from ui.context import UIContext
from ui.helpers import blob_to_payload, build_src_quick, payload_to_blob, widget_key_fragment


def _render_storage_banner(ctx: UIContext) -> None:
    settings = ctx.settings
    if ctx.storage_error:
        st.error(ctx.storage_error)
        st.info(
            "Sửa MongoDB rồi bấm **R** để reload. Trong lúc này bạn vẫn có thể preview/đọc nội dung, "
            "nhưng không thể lưu DB."
        )
    _back = (
        f"MongoDB `{settings.mongodb_database}.{settings.mongodb_collection}`"
        if settings.mongodb_uri
        else f"SQLite `{settings.database_path}`"
    )
    st.caption(
        f"Lưu trữ hiện tại: {_back} · LLM: **{'tắt' if settings.skip_llm else 'bật'}**."
    )
    if settings.mongodb_uri:
        st.success(
            f"**MongoDB đang bật** — collection `{settings.mongodb_collection}` "
            f"trong database `{settings.mongodb_database}`. Sau khi crawl, kiểm tra document "
            f'với `source_id` dạng `url_<hash>` (hoặc ID tuỳ chọn trong Options).'
        )
    else:
        st.info(
            "**Đang dùng SQLite** — nhập **MongoDB URI** ở sidebar (vd. `mongodb://localhost:27017`) "
            "rồi **Run crawl** lại để ghi vào Mongo."
        )


def _render_scope_guide() -> None:
    with st.expander("What can be crawled? (selection guide)", expanded=False):
        st.markdown(
            """
**Supported inputs (pick one in the list below)**

| Selection | What gets stored |
|-----------|------------------|
| **One web page / PDF** | HTML: article / raw text. **PDF:** text layer (không OCR scan). |
| **RSS / Atom** | Text built from the **feed file** (titles, links, summaries of listed items). |
| **Web search** | Top text **snippets** from DuckDuckGo for your query. |
| **Local file** | Reads a file from disk: PDF (text layer), HTML, CSV, or plain text. |

**Generally works well**  
Static or server-rendered pages, blogs, docs mirrors, RSS feeds, public pages that allow polite bots.

**Not guaranteed**  
Login-only pages, CAPTCHAs, aggressive anti-bot, infinite scroll SPAs, paywalls, **PDF chỉ ảnh scan** (không có lớp chữ), video, high-frequency bulk crawling (rate / legal risk).

You are responsible for **robots.txt**, site terms, and copyright.
            """
        )

    from ui.constants import HOW_TO_CRAWL_MD

    with st.expander("Hướng dẫn crawl (chi tiết)", expanded=False):
        st.markdown(HOW_TO_CRAWL_MD)


def _render_two_step_preview(
    ctx: UIContext,
    *,
    kind: str,
    raw: str,
    extract: str,
    rss_n: int,
    dd_n: int,
    nick: str,
    llm_mode: str,
    yt_n: int,
    dc_depth: int,
    dc_pages: int,
    crawl_imgs: bool,
) -> None:
    settings = ctx.settings
    storage = ctx.storage

    st.info(
        "**Luồng gợi ý:** ① **Preview** (chưa ghi DB) → ② xem từng trường / **chọn multiselect** "
        "→ ③ **Crawl & lưu**."
    )
    prev_btn = st.button("1 · Preview — chưa lưu DB", use_container_width=True)
    if prev_btn:
        if not raw:
            st.warning("Dán URL, feed hoặc câu query.")
        else:
            try:
                with st.spinner("Đang tải preview…"):
                    src = build_src_quick(
                        kind=kind,
                        raw=raw,
                        extract=extract,
                        rss_n=int(rss_n),
                        dd_n=int(dd_n),
                        nick=(nick or "").strip(),
                        llm_mode=llm_mode,
                        max_videos=int(yt_n),
                        max_depth=int(dc_depth),
                        max_crawl_pages=int(dc_pages),
                        crawl_images=bool(crawl_imgs),
                    )
                    payload = collect_payload(src, settings)
                if payload is None:
                    st.warning(
                        "Không lấy được nội dung (ví dụ 304 Not Modified). "
                        "Thử URL khác hoặc xóa bản ghi cũ cùng source nếu đang test cache."
                    )
                else:
                    cat = build_field_catalog(payload)
                    st.session_state.pop("wf_chosen_fields", None)
                    for _kdel in list(st.session_state.keys()):
                        if isinstance(_kdel, str) and _kdel.startswith("wf_chosen_fields_"):
                            st.session_state.pop(_kdel, None)
                    st.session_state["wf_two"] = {
                        "src_dict": source_config_as_dict(src),
                        "payload_blob": payload_to_blob(payload),
                        "catalog": cat,
                        "ui_kind": kind,
                    }
                    st.success(
                        f"Preview xong — **{len(cat)}** trường. Xem bên dưới, chọn trường rồi bấm bước 2."
                    )
                    st.rerun()
            except ValueError as ve:
                st.error(str(ve))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    wf = st.session_state.get("wf_two")
    if wf and isinstance(wf, dict) and wf.get("catalog"):
        if wf.get("ui_kind") != kind:
            st.warning("Chế độ crawl đã đổi kể từ lần preview — hãy bấm Preview lại cho khớp.")
        st.markdown("#### Dữ liệu đầy đủ từng trường")
        st.caption(
            f"Mỗi ô tối đa hiển thị ~{DISPLAY_PREVIEW_CHARS // 1000}k ký tự để giao diện mượt; "
            "bản đầy đủ vẫn dùng khi bạn bấm bước 2 (và có thể bị cắt theo giới hạn lưu BSON)."
        )
        cat: dict[str, str] = wf["catalog"]
        if st.button("Xóa preview", type="secondary"):
            st.session_state.pop("wf_two", None)
            st.session_state.pop("wf_chosen_fields", None)
            for _kdel in list(st.session_state.keys()):
                if isinstance(_kdel, str) and _kdel.startswith("wf_chosen_fields_"):
                    st.session_state.pop(_kdel, None)
            st.rerun()
        for fk, fv in sorted(cat.items()):
            n_chars = len(fv)
            disp = (
                fv
                if n_chars <= DISPLAY_PREVIEW_CHARS
                else (
                    fv[:DISPLAY_PREVIEW_CHARS]
                    + "\n\n… [UI chỉ hiển thị một phần; toàn bộ vẫn được dùng khi lưu nếu bạn giữ chọn trường này] …"
                )
            )
            wk = widget_key_fragment(fk)
            with st.expander(f"{fk} — {n_chars:,} ký tự", expanded=False):
                st.text_area(
                    fk,
                    value=disp,
                    height=min(560, max(140, min(n_chars // 8 + 100, 900))),
                    key=f"wf_prev_area_{wk}",
                    disabled=True,
                    label_visibility="collapsed",
                )
        keys = sorted(cat.keys())
        _cat_sig = hashlib.sha256(repr(tuple(keys)).encode("utf-8")).hexdigest()[:12]
        chosen = st.multiselect(
            "2 · Chọn trường cần giữ bản đầy đủ trong `meta.extract_full_by_field` "
            "(đồng thời ghi `user_extract_fields`)",
            options=keys,
            default=keys,
            key=f"wf_chosen_fields_{_cat_sig}",
            help="Có thể bỏ chọn cột/meta không cần; `raw_text` vẫn được pipeline lưu theo giới hạn store.",
        )
        st.caption(
            "Bước 2 chạy LLM trên `raw_text` (nếu không tắt LLM), ghi document và merge meta bạn chọn."
        )
        save2 = st.button(
            "2 · Crawl & lưu vào store",
            type="primary",
            use_container_width=True,
            disabled=storage is None,
        )
        if save2:
            if storage is None:
                st.error("MongoDB chưa kết nối, không thể lưu.")
                st.stop()
            try:
                src = source_config_from_dict(wf["src_dict"])
                pay = blob_to_payload(wf["payload_blob"])
                subset = {k: cat[k] for k in chosen if k in cat}
                extra_meta: dict[str, object] = {
                    "user_extract_fields": chosen,
                    "user_extract_confirmed_at": datetime.now(timezone.utc).isoformat(),
                    "preview_two_step": True,
                }
                if subset:
                    extra_meta["extract_full_by_field"] = subset
                with st.spinner("Đang crawl & lưu…"):
                    res = run_source(
                        src,
                        storage,
                        settings,
                        None,
                        cached_payload=pay,
                        extra_meta=extra_meta,
                    )
                if res.changed:
                    st.success(
                        f"Đã lưu **source_id** `{src.id}` · id bản ghi: `{res.document_id}` "
                        f"({'MongoDB' if settings.mongodb_uri else 'SQLite'})."
                    )
                else:
                    st.warning(
                        f"**Không ghi bản ghi mới** — `{res.skipped_reason or 'unknown'}`. "
                        "Có thể nội dung trùng hash với bản đã có, hoặc lỗi upstream."
                    )
                st.session_state.pop("wf_two", None)
                st.session_state.pop("wf_chosen_fields", None)
                for _kdel in list(st.session_state.keys()):
                    if isinstance(_kdel, str) and _kdel.startswith("wf_chosen_fields_"):
                        st.session_state.pop(_kdel, None)
            except ValueError as ve:
                st.error(str(ve))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def _render_one_step_run(
    ctx: UIContext,
    *,
    kind: str,
    raw: str,
    extract: str,
    rss_n: int,
    dd_n: int,
    nick: str,
    llm_mode: str,
    yt_n: int,
    dc_depth: int,
    dc_pages: int,
    crawl_imgs: bool,
) -> None:
    settings = ctx.settings
    storage = ctx.storage

    run_btn = st.button(
        "▶  Run crawl — lưu vào store",
        type="primary",
        use_container_width=True,
        disabled=storage is None,
    )
    if run_btn:
        if storage is None:
            st.error("MongoDB chưa kết nối, không thể lưu.")
            st.stop()
        if not raw:
            st.warning("Dán URL, feed hoặc câu query.")
        else:
            try:
                with st.spinner("Working…"):
                    src = build_src_quick(
                        kind=kind,
                        raw=raw,
                        extract=extract,
                        rss_n=int(rss_n),
                        dd_n=int(dd_n),
                        nick=(nick or "").strip(),
                        llm_mode=llm_mode,
                        max_videos=int(yt_n),
                        max_depth=int(dc_depth),
                        max_crawl_pages=int(dc_pages),
                        crawl_images=bool(crawl_imgs),
                    )
                    res = run_source(src, storage, settings, None)
                if res.changed:
                    st.success(
                        f"Đã lưu **source_id** `{src.id}` · id bản ghi: `{res.document_id}` "
                        f"({'MongoDB' if settings.mongodb_uri else 'SQLite'})."
                    )
                else:
                    st.warning(
                        f"**Không ghi bản ghi mới** — `{res.skipped_reason or 'unknown'}`. "
                        "Thử đổi URL, tắt cache 304 (xóa bản ghi cũ cùng source), hoặc kiểm tra PDF có lớp chữ."
                    )
            except ValueError as ve:
                st.error(str(ve))
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))


def render_crawl_section(ctx: UIContext) -> None:
    """Render crawl form, preview workflow, and run buttons."""
    _render_storage_banner(ctx)
    _render_scope_guide()

    st.subheader("Crawl")
    labels = [m[0] for m in CRAWL_MODES]
    _pick = st.session_state.get("crawl_mode_pick")
    if _pick not in labels:
        st.session_state["crawl_mode_pick"] = labels[0]
    st.markdown("##### Quick start")
    _qc = st.columns(4)
    _quick_rows = [
        ("Trang Python", 0, CRAWL_MODES[0][2]),
        ("RSS BBC", 1, CRAWL_MODES[1][2]),
        ("Query mẫu", 2, CRAWL_MODES[2][2]),
        ("python.org", 0, "https://www.python.org/"),
    ]
    for j, (btn_label, mode_idx, fill_val) in enumerate(_quick_rows):
        with _qc[j]:
            if st.button(btn_label, key=f"quick_fill_{j}", use_container_width=True):
                st.session_state["crawl_mode_pick"] = labels[mode_idx]
                st.session_state["main_paste_url"] = fill_val
                st.rerun()

    picked = st.selectbox(
        "What do you want to crawl?",
        labels,
        key="crawl_mode_pick",
    )
    try:
        _ki = labels.index(picked)
    except ValueError:
        _ki = 0
        st.session_state["crawl_mode_pick"] = labels[0]
        picked = labels[0]
    _, kind, placeholder, blurb = CRAWL_MODES[_ki]
    st.caption(blurb)

    text_in = st.text_area(
        "Paste URL or query" if kind not in ("File",) else "File path (full path on disk)",
        height=110,
        placeholder=placeholder,
        label_visibility="collapsed",
        key="main_paste_url",
    )

    if kind == "File":
        uploaded = st.file_uploader(
            "Or upload a file",
            type=["pdf", "html", "htm", "csv", "txt", "md", "json", "xml", "docx"],
            key="file_upload_widget",
        )
        if uploaded is not None:
            _upload_dir = Path(tempfile.gettempdir()) / "crawl_ai_uploads"
            _upload_dir.mkdir(exist_ok=True)
            _dest = _upload_dir / uploaded.name
            _dest.write_bytes(uploaded.getvalue())
            text_in = str(_dest)
            st.caption(f"Saved upload → `{_dest}`")

    with st.expander("Options (optional)", expanded=False):
        nick = st.text_input("Source ID (optional)", placeholder="auto if empty")
        if kind in ("URL", "RSS", "File"):
            extract = st.selectbox("Extraction", ("article", "raw"))
        else:
            extract = "raw"
        llm_mode = st.selectbox(
            "LLM mode",
            ("general", "persons"),
            help="**general**: tóm tắt nội dung. **persons**: trích xuất thông tin cá nhân (tên, ngày sinh, địa chỉ, SĐT, email…).",
        )
        rss_n = 20
        dd_n = 8
        yt_n = 10
        dc_depth = 2
        dc_pages = 20
        crawl_imgs = False
        if kind == "RSS":
            rss_n = st.number_input("Max feed entries", 1, 100, 20)
        elif kind == "Search":
            dd_n = st.number_input("Max search results", 1, 25, 8)
        elif kind == "YouTube":
            yt_n = st.number_input("Max videos", 1, 2000, 2000)
        elif kind == "DeepCrawl":
            dc_depth = st.number_input("Max depth", 1, 5, 2)
            dc_pages = st.number_input("Max pages", 1, 100, 20)
        if kind in ("URL", "DeepCrawl"):
            crawl_imgs = st.checkbox(
                "Tải ảnh trên trang (lưu vào data/images/<source_id>)",
                value=False,
                help="Trích <img>, og:image, twitter:image rồi tải file ảnh về đĩa; đường dẫn lưu trong meta['images'].",
            )

    raw = (text_in or "").strip()
    two_step = st.checkbox(
        "Hai bước: xem đủ dữ liệu từng trường → chọn trường → mới crawl & lưu DB",
        value=True,
        key="two_step_crawl",
        help="Bật: Preview chỉ tải và hiển thị; sau khi bạn chọn trường mới ghi store và chạy LLM (nếu bật). "
        "Tắt: một nút Run crawl lưu ngay.",
    )

    common = dict(
        kind=kind,
        raw=raw,
        extract=extract,
        rss_n=rss_n,
        dd_n=dd_n,
        nick=nick,
        llm_mode=llm_mode,
        yt_n=yt_n,
        dc_depth=dc_depth,
        dc_pages=dc_pages,
        crawl_imgs=crawl_imgs,
    )

    if two_step:
        _render_two_step_preview(ctx, **common)
    else:
        _render_one_step_run(ctx, **common)
