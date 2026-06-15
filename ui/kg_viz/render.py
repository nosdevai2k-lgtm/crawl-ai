"""Render Video KG-style panel (results + vis-network graph)."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

_CSS = (Path(__file__).parent / "vkg.css").read_text(encoding="utf-8")

_COLORS = {
    "Person": "#4f9dff", "Title": "#f4c542", "Topic": "#c98bff", "Organization": "#ff7a59",
    "Location": "#36c275", "Video": "#ff5d8f", "Scene": "#5bd1d7", "TextMention": "#9aa4b2",
    "Event": "#f4c542", "Festival": "#e879f9", "Document": "#94a3b8", "Image": "#22d3ee", "Node": "#888",
}


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_KIND_ICON = {
    "document": "📄",
    "doc": "📰",
    "image": "🖼️",
    "scene": "🎬",
    "video": "📹",
}


def _render_cards(results: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, r in enumerate(results):
        src = r.get("_source", "local")
        src_b = {"video_kg": "VKG", "local": "KG", "image_index": "IMG", "document_index": "DOC"}.get(src, src)
        kind = r.get("display_kind") or r.get("kind") or "document"
        icon = _KIND_ICON.get(kind, "📄")
        title = r.get("video_name") or r.get("title") or "?"
        time_s = r.get("time")
        play = ""
        if kind in ("scene", "video") and (r.get("video") or r.get("media_ref")):
            play = ' <span class="rel">▶</span>'
        why = r.get("why") or ""
        if len(why) > 120:
            why = why[:117] + "…"
        meta_bits = [x for x in [r.get("date"), r.get("programme"), why] if x]
        if time_s:
            meta_bits.insert(0, f"@{time_s}")
        meta = " · ".join(meta_bits)
        ev = r.get("evidence") or r.get("snippet") or ""
        img = ""
        if kind == "image" and r.get("path"):
            p = Path(str(r["path"]))
            if p.is_file() and p.stat().st_size < 800_000:
                try:
                    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
                    suf = p.suffix.lower().lstrip(".")
                    mime = "jpeg" if suf in ("jpg", "jpeg") else suf or "jpeg"
                    img = f'<img class="imgthumb" src="data:image/{mime};base64,{b64}"/>'
                except Exception:
                    img = ""
        parts.append(
            f'<div class="card"><div class="h"><span class="srcbadge">{_esc(src_b)}</span>{icon} {_esc(title)}{play}</div>'
            f'<div class="meta">{_esc(meta)}</div>'
            + (f'<div class="ev">{_esc(ev)}</div>' if ev else "")
            + img
            + "</div>"
        )
    return "".join(parts)


def _understood_html(notes: dict[str, Any]) -> str:
    det = notes.get("resolved_detail") or {}
    parts = []
    for d in det.values():
        approx = "≈ " if d.get("approx") else ""
        parts.append(f'{approx}{_esc(d.get("name",""))} <span class="lbltag">{_esc(d.get("label",""))}</span>')
    html = ""
    if parts:
        html += f'<div class="understood">Đã hiểu: {" · ".join(parts)}</div>'
    unr = notes.get("unresolved") or []
    if unr:
        html += f'<div class="notrecog">Không nhận ra: {_esc(", ".join(unr))}</div>'
    return html


def render_vkg_panel(
    payload: dict[str, Any],
    *,
    entities: str = "",
    topics: str = "",
    stats_line: str = "",
    height: int = 640,
) -> str:
    """Full HTML for st.components.v1.html."""
    results = payload.get("results") or []
    notes = payload.get("notes") or {}
    graph = payload.get("graph") or {"nodes": [], "edges": []}
    neighbors = payload.get("neighbors") or {}
    legend = (payload.get("stats") or {}).get("legend") or []

    ent_tags = "".join(
        f'<span class="tag">người/địa: <b>{_esc(e.strip())}</b></span>'
        for e in entities.split(";") if e.strip()
    )
    top_tags = "".join(
        f'<span class="tag">chủ đề: <b>{_esc(t.strip())}</b></span>'
        for t in topics.split(";") if t.strip()
    )
    legend_html = "".join(
        f'<span><span class="dot" style="background:{it.get("color","#888")}"></span>{_esc(it.get("label",""))} {it.get("count",0)}</span>'
        for it in legend
    )

    side_html = ""
    if results:
        side_html = (
            f'<div class="intent"><div><b>Tìm:</b> {ent_tags}{top_tags or "<i>—</i>"}</div>'
            f'<div style="margin-top:5px"><b>Kết quả:</b> <span class="rel">{len(results)}</span></div></div>'
            + _understood_html(notes)
            + f'<div class="meta" style="margin:6px 0">{len(results)} kết quả</div>'
            + _render_cards(results)
        )
    else:
        side_html = (
            '<div class="empty">Nhập câu hỏi hoặc bấm một mẫu phía trên.<br><br>'
            'Đồ thị bên phải tương tác được: <b>bấm vào một node</b> để mở rộng quan hệ.</div>'
        )

    data_json = json.dumps({
        "graph": graph,
        "neighbors": neighbors,
        "colors": _COLORS,
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_CSS}</style>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
</head><body>
<div class="vkg-root" style="height:{height}px">
<header>
 <div class="top">
  <h1>🔎 crawl-ai KG</h1>
  <span id="stats">{_esc(stats_line)}</span>
 </div>
 <div class="legend">{legend_html}</div>
</header>
<div class="wrap">
 <div class="side" id="side">{side_html}</div>
 <div id="net"></div>
</div>
</div>
<script>
const DATA = {data_json};
const COLORS = DATA.colors;
const nodes = new vis.DataSet(), edges = new vis.DataSet();
const net = new vis.Network(document.getElementById('net'), {{nodes, edges}}, {{
  nodes: {{shape:'dot', size:15, font:{{color:'#e6e6e6', size:13}}}},
  edges: {{color:{{color:'#3a4252', highlight:'#7c8696'}}, font:{{color:'#8a93a3', size:10, strokeWidth:0}}, arrows:'to', smooth:{{type:'dynamic'}}}},
  physics: {{barnesHut:{{gravitationalConstant:-9000, springLength:130}}, stabilization:{{iterations:120}}}},
  interaction: {{hover:true}}
}});
function addGraph(g) {{
  (g.nodes||[]).forEach(n => {{
    if (!nodes.get(n.id)) {{
      const grp = n.group || n.label || 'Node';
      const disp = n.name || n.label || n.id;
      nodes.add({{
        id: n.id,
        label: disp.length>30 ? disp.slice(0,28)+'…' : disp,
        title: grp+': '+disp,
        color: COLORS[grp]||COLORS.Node
      }});
    }}
  }});
  (g.edges||[]).forEach(e => {{
    const id = e.from+'|'+e.to+'|'+(e.label||'');
    if (!edges.get(id)) edges.add({{id, from:e.from, to:e.to, label:(e.label||'').toLowerCase()}});
  }});
}}
function drawGraph(g) {{ nodes.clear(); edges.clear(); addGraph(g); }}
if (typeof vis === 'undefined') {{
  document.getElementById('net').innerHTML = '<div class="empty">Không tải được vis-network. Kiểm tra mạng.</div>';
}} else {{
drawGraph(DATA.graph||{{nodes:[],edges:[]}});
net.on('click', p => {{
  if (!p.nodes || !p.nodes.length) return;
  const id = p.nodes[0];
  const nb = DATA.neighbors && DATA.neighbors[id];
  if (nb) addGraph(nb);
}});
}}
</script>
</body></html>"""
