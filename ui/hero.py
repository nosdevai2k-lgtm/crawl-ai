"""GSAP hero banner."""

from __future__ import annotations

import streamlit.components.v1 as components


def render_gsap_hero() -> None:
    """Hero động bằng GSAP (chạy trong iframe component)."""
    html = """
<div id="hero">
  <div class="orb o1"></div><div class="orb o2"></div><div class="orb o3"></div>
  <h1 id="title">crawl-ai</h1>
  <p id="tagline">Crawl • Extract • Images + Names • LLM</p>
  <div id="bar"></div>
</div>
<style>
  html,body{margin:0;background:#1A1A1A;overflow:hidden;font-family:Inter,system-ui,sans-serif;}
  #hero{position:relative;height:160px;display:flex;flex-direction:column;
        align-items:center;justify-content:center;}
  #title{margin:0;font-size:2.6rem;font-weight:700;letter-spacing:-.04em;
         background:linear-gradient(90deg,#D4A574,#E8C9A0,#D4A574);
         -webkit-background-clip:text;background-clip:text;color:transparent;
         background-size:200% auto;}
  #tagline{margin:.4rem 0 0;color:#9a9a9a;font-size:.95rem;letter-spacing:.02em;}
  #bar{margin-top:.9rem;height:3px;width:0;border-radius:3px;
       background:linear-gradient(90deg,#D4A574,transparent);}
  .orb{position:absolute;border-radius:50%;filter:blur(40px);opacity:.5;}
  .o1{width:140px;height:140px;background:#D4A574;left:8%;top:0;}
  .o2{width:90px;height:90px;background:#6b8caf;right:12%;top:30%;}
  .o3{width:110px;height:110px;background:#a5746b;right:30%;bottom:-20px;}
</style>
<script src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>
<script>
  const tl = gsap.timeline();
  tl.from("#title",{y:30,opacity:0,duration:.8,ease:"power3.out"})
    .from("#tagline",{y:14,opacity:0,duration:.6,ease:"power2.out"},"-=.4")
    .to("#bar",{width:220,duration:.7,ease:"power2.inOut"},"-=.3");
  gsap.to("#title",{backgroundPosition:"200% center",duration:4,
          repeat:-1,ease:"none"});
  gsap.to(".orb",{y:"+=20",duration:3,repeat:-1,yoyo:true,
          ease:"sine.inOut",stagger:.4});
</script>
"""
    components.html(html, height=170)
