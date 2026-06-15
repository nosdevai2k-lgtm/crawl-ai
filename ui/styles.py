"""Streamlit custom CSS."""

MIN_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* === Base === */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }
    .stApp {
        background: #1A1A1A !important;
        color: #ECECEC !important;
    }

    /* === Sidebar — Claude style muted panel === */
    section[data-testid="stSidebar"] {
        background: #212121 !important;
        border-right: 1px solid rgba(255,255,255,0.06) !important;
    }
    div[data-testid="stSidebar"] label,
    div[data-testid="stSidebar"] p,
    div[data-testid="stSidebar"] .stMarkdown p {
        color: #B8B8B8 !important;
        font-size: 0.875rem !important;
    }

    /* === Main content — generous spacing === */
    section.main .block-container {
        max-width: 52rem !important;
        padding-top: 2rem !important;
        padding-bottom: 4rem !important;
    }

    /* === Typography === */
    h1.t {
        font-size: 1.6rem;
        font-weight: 600;
        color: #F5F5F5 !important;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.03em;
    }
    h2, .stSubheader {
        font-weight: 600 !important;
        letter-spacing: -0.02em !important;
        color: #E8E8E8 !important;
    }
    h3 {
        font-weight: 500 !important;
        color: #D4A574 !important;
    }

    /* === Inputs — soft rounded === */
    [data-testid="stTextArea"] textarea,
    [data-testid="stTextInput"] input,
    .stSelectbox > div > div {
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        background: #2A2A2A !important;
        color: #ECECEC !important;
        font-size: 0.9rem !important;
        transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
    }
    [data-testid="stTextArea"] textarea:focus,
    [data-testid="stTextInput"] input:focus {
        border-color: #D4A574 !important;
        box-shadow: 0 0 0 3px rgba(212, 165, 116, 0.12) !important;
    }

    /* === Primary button — warm accent like Claude === */
    div.stButton > button[kind="primary"] {
        border-radius: 12px !important;
        min-height: 2.75rem !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
        letter-spacing: 0.01em !important;
        border: none !important;
        background: #D4A574 !important;
        color: #1A1A1A !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.3), 0 4px 12px rgba(212, 165, 116, 0.15) !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="primary"]:hover {
        background: #E0B68A !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3), 0 6px 20px rgba(212, 165, 116, 0.25) !important;
        transform: translateY(-1px) !important;
    }

    /* === Secondary button === */
    div.stButton > button[kind="secondary"],
    div.stButton > button:not([kind="primary"]) {
        border-radius: 12px !important;
        min-height: 2.5rem !important;
        font-weight: 500 !important;
        font-size: 0.875rem !important;
        border: 1px solid rgba(255,255,255,0.12) !important;
        background: transparent !important;
        color: #CCCCCC !important;
        transition: all 0.2s ease !important;
    }
    div.stButton > button[kind="secondary"]:hover,
    div.stButton > button:not([kind="primary"]):hover {
        border-color: #D4A574 !important;
        color: #D4A574 !important;
        background: rgba(212, 165, 116, 0.06) !important;
    }

    /* === Expanders — card-like === */
    .streamlit-expanderHeader {
        font-weight: 500 !important;
        font-size: 0.9rem !important;
        color: #D0D0D0 !important;
        border-radius: 12px !important;
    }
    details[data-testid="stExpander"] {
        border: 1px solid rgba(255,255,255,0.06) !important;
        border-radius: 14px !important;
        background: #222222 !important;
        margin-bottom: 0.75rem !important;
    }

    /* === Alerts / info boxes === */
    .stAlert > div {
        border-radius: 12px !important;
        border: none !important;
        font-size: 0.875rem !important;
    }
    div[data-testid="stNotification"] {
        border-radius: 12px !important;
    }

    /* === Dataframe === */
    .stDataFrame {
        border-radius: 12px !important;
        overflow: hidden !important;
    }

    /* === Code blocks === */
    .stCodeBlock, pre, code {
        font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
        font-size: 0.82rem !important;
        border-radius: 10px !important;
    }

    /* === Selectbox / multiselect pills === */
    span[data-baseweb="tag"] {
        border-radius: 8px !important;
        background: rgba(212, 165, 116, 0.15) !important;
        color: #D4A574 !important;
        border: 1px solid rgba(212, 165, 116, 0.3) !important;
    }

    /* === Checkbox / toggle === */
    .stCheckbox label span {
        color: #CCCCCC !important;
    }

    /* === Dividers === */
    hr {
        border-color: rgba(255,255,255,0.06) !important;
        margin: 1.5rem 0 !important;
    }

    /* === Captions === */
    .stCaption, small {
        color: #888888 !important;
        font-size: 0.8rem !important;
    }

    /* === Success/warning/error — softer === */
    .element-container .stSuccess {
        background: rgba(76, 175, 80, 0.08) !important;
        border-left: 3px solid #4CAF50 !important;
    }
    .element-container .stWarning {
        background: rgba(255, 152, 0, 0.08) !important;
        border-left: 3px solid #FF9800 !important;
    }

    /* === File uploader === */
    [data-testid="stFileUploader"] {
        border-radius: 12px !important;
    }
    [data-testid="stFileUploader"] section {
        border-radius: 12px !important;
        border: 1px dashed rgba(255,255,255,0.15) !important;
    }

    /* === Tabs === */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px !important;
        font-weight: 500 !important;
    }

    /* === Hide Streamlit branding === */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent !important; }

    /* === Scrollbar === */
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: transparent; }
    ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.2); }

    /* === Number input === */
    [data-testid="stNumberInput"] input {
        border-radius: 10px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        background: #2A2A2A !important;
    }

    /* === Spinner === */
    .stSpinner > div {
        border-top-color: #D4A574 !important;
    }

    /* === Entrance animation for native widgets (GSAP can't reach the parent frame) === */
    @keyframes craiFadeUp {
        from { opacity: 0; transform: translateY(10px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    section.main .block-container > div {
        animation: craiFadeUp 0.5s ease both;
    }
    div.stButton > button[kind="primary"] {
        animation: craiFadeUp 0.5s ease both;
    }
</style>
"""
