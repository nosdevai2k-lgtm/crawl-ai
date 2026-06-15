"""
crawl-ai — Streamlit UI entry point.
Run: streamlit run app_ui.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from ui.env import reload_env  # noqa: E402
from ui.hero import render_gsap_hero  # noqa: E402
from ui.pages.auto_crawl import render_auto_crawl_section  # noqa: E402
from ui.pages.crawl import render_crawl_section  # noqa: E402
from ui.pages.documents import render_documents_section  # noqa: E402
from ui.pages.export_data import render_export_section  # noqa: E402
from ui.pages.image_harvest import render_image_harvest_section  # noqa: E402
from ui.pages.kg_search import render_kg_search_section  # noqa: E402
from ui.sidebar import render_sidebar  # noqa: E402
from ui.styles import MIN_CSS  # noqa: E402

reload_env(ROOT)

st.set_page_config(
    page_title="crawl-ai",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"Get help": None, "Report a bug": None, "About": None},
)
st.markdown(MIN_CSS, unsafe_allow_html=True)

ctx = render_sidebar(ROOT, ROOT / "config.yaml")

render_gsap_hero()

_NAV = ["Crawl", "Documents", "Search", "Auto-crawl", "Images", "Export & Batch"]
if "ui_nav" not in st.session_state:
    st.session_state["ui_nav"] = _NAV[0]

st.radio(
    "Navigation",
    _NAV,
    horizontal=True,
    key="ui_nav",
    label_visibility="collapsed",
)

nav = st.session_state["ui_nav"]

if nav == "Crawl":
    render_crawl_section(ctx)
elif nav == "Documents":
    render_documents_section(ctx)
elif nav == "Search":
    render_kg_search_section(ctx)
elif nav == "Auto-crawl":
    render_auto_crawl_section(ctx)
elif nav == "Images":
    render_image_harvest_section(ctx)
    st.caption("Tìm ảnh theo preset đã gộp vào tab **Search**.")
else:
    render_export_section(ctx)
