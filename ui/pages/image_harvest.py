"""Landmark + face image harvest UI."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from ui.context import UIContext


def render_image_harvest_section(ctx: UIContext) -> None:
    settings = ctx.settings

    st.subheader("Thu thập ảnh")
    tab_landmark, tab_face, tab_id = st.tabs(
        ["📍 Địa danh / phong cảnh", "👤 Khuôn mặt / nhân vật", "🔍 Nhận diện mặt → sự kiện"]
    )

    with tab_landmark:
        st.caption("Image-search đa truy vấn → tải ảnh phong cảnh/địa danh → lọc trùng.")
        hv_c1, hv_c2, hv_c3 = st.columns([2, 2, 1])
        with hv_c1:
            hv_name = st.text_input("Tên địa danh", placeholder="VD: Vịnh Hạ Long", key="hv_name")
        with hv_c2:
            hv_en = st.text_input("Tên tiếng Anh (tuỳ chọn)", placeholder="VD: Ha Long Bay", key="hv_en")
        with hv_c3:
            hv_target = st.number_input("Số ảnh", min_value=50, max_value=800, value=400, step=50, key="hv_target")
        if st.button("🖼️ Thu thập địa danh", type="primary", key="hv_btn", disabled=not (hv_name or "").strip()):
            from src.image_harvest import harvest_landmark
            from src.quick_sources import _slug_id
            from src.search import build_index

            out = Path("data/images") / (_slug_id("", hv_name).strip("_") or "landmark")
            try:
                with st.spinner(f"Đang tải ảnh '{hv_name}'…"):
                    stats = harvest_landmark(
                        hv_name.strip(),
                        out,
                        user_agent=settings.user_agent,
                        timeout=settings.http_timeout,
                        en_name=(hv_en or "").strip() or None,
                        target=int(hv_target),
                    )
                    build_index()
                st.success(f"Lưu **{stats['saved']}** ảnh → `{out}` · index rebuilt")
                st.caption(
                    f"urls={stats['urls']} · lọc={stats.get('off_topic', 0)} · nhỏ={stats['too_small']} · "
                    f"trùng={stats['dup']} · hỏng={stats['failed']}"
                )
                imgs = [str(p) for p in sorted(out.glob("*")) if p.is_file()][:12]
                if imgs:
                    st.image(imgs, width=120)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    with tab_face:
        st.caption("Tải ảnh chân dung vào `data/images/human/<tên>/` để search preset **Nhân vật** khớp tên.")
        fc1, fc2, fc3 = st.columns([2, 2, 1])
        with fc1:
            face_name = st.text_input("Tên nhân vật", placeholder="VD: Tô Lâm", key="face_name")
        with fc2:
            face_en = st.text_input("Tên tiếng Anh", placeholder="VD: To Lam", key="face_en")
        with fc3:
            face_target = st.number_input("Số ảnh", min_value=20, max_value=300, value=120, step=20, key="face_target")
        from src import faces as _faces
        face_verify = st.checkbox(
            "Kiểm tra khuôn mặt sau khi tải (bỏ ảnh không có mặt / sai người)",
            value=_faces.available(), disabled=not _faces.available(),
            help=None if _faces.available() else "Cần opencv-python-headless + model trong data/models/",
            key="face_verify",
        )
        if st.button("👤 Thu thập khuôn mặt", type="primary", key="face_btn", disabled=not (face_name or "").strip()):
            from src.face_harvest import default_face_out_dir, harvest_faces
            from src.search import build_index

            out = default_face_out_dir(face_name.strip())
            try:
                with st.spinner(f"Đang tải mặt '{face_name}'…"):
                    stats = harvest_faces(
                        face_name.strip(),
                        out,
                        user_agent=settings.user_agent,
                        timeout=settings.http_timeout,
                        en_name=(face_en or "").strip() or None,
                        target=int(face_target),
                    )
                    vmsg = ""
                    if face_verify and _faces.available():
                        r = _faces.clean_folder(out, move_rejects=True)
                        vmsg = f" · verify: giữ {r['kept']}, bỏ {len(r['rejected'])}"
                    build_index()
                st.success(f"Lưu **{stats['saved']}** ảnh → `{out}` · index rebuilt{vmsg}")
                st.caption(
                    f"urls={stats['urls']} · lọc title={stats['off_topic']} · trùng={stats['dup']}"
                )
                imgs = [str(p) for p in sorted(out.glob("*")) if p.is_file()][:12]
                if imgs:
                    st.image(imgs, width=120)
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    with tab_id:
        st.caption("Tải lên một ảnh → nhận diện nhân vật (theo ảnh đã thu thập) → "
                   "sự kiện liên quan trong KG.")
        from src import faces as _faces2

        if not _faces2.available():
            st.info("Face recognition chưa sẵn sàng. Cài `opencv-python-headless` và đặt "
                    "model YuNet + SFace vào `data/models/`.")
        else:
            up = st.file_uploader("Ảnh khuôn mặt", type=["jpg", "jpeg", "png", "webp"], key="id_up")
            if up is not None:
                from src.kg.faces_link import match_face_to_events

                img_bytes = up.read()
                st.image(img_bytes, width=180)
                with st.spinner("Đang nhận diện…"):
                    res = match_face_to_events(settings.database_path, img_bytes, Path("data/images"))
                if not res["match"]:
                    st.warning("Không khớp nhân vật nào đã thu thập. Thử thu thập khuôn mặt người này trước.")
                else:
                    m = res["match"]
                    st.success(f"**{m['name']}** · độ khớp {m['score']}")
                    if res["events"]:
                        st.markdown("**Sự kiện liên quan:**")
                        for ev in res["events"]:
                            st.markdown(f"- {ev['name']} · _{ev['label']}_ ({ev['via']})")
                    else:
                        st.caption("Chưa có sự kiện liên kết trong KG. Bấm **Rebuild KG** ở tab Search "
                                   "để tạo cạnh Person→Event từ tài liệu đã crawl.")
