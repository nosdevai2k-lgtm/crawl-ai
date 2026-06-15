"""Domain trust / authority ranking for crawl sources and search results.

The crawler is transport-agnostic and trusts every URL equally. For news /
research monitoring we usually want OFFICIAL and reputable sources first
(government portals, the national press) and spam/low-trust sites filtered out.

This module provides a small, curated registry of Vietnamese + international
authoritative domains and helpers to score / rank / filter by trust. It is pure
Python (no network) so it is cheap to call on every search result.

Tiers (higher = more authoritative):
  official   1.00  government & state bodies (.gov.vn, chinhphu.vn, quochoi.vn…)
  press      0.80  established national news outlets
  reference  0.70  encyclopaedic / academic references (wikipedia, .edu…)
  neutral    0.40  unknown but not flagged
  low        0.15  user-generated / aggregators (reddit, medium, blogspot…)
  blocked    0.00  spam / content farms — should be dropped
"""

from __future__ import annotations

from urllib.parse import urlparse

TIER_SCORE: dict[str, float] = {
    "official": 1.00,
    "press": 0.80,
    "reference": 0.70,
    "neutral": 0.40,
    "low": 0.15,
    "blocked": 0.0,
}

# Exact domains (matched against the registrable host and its parent domains).
_OFFICIAL = {
    "chinhphu.vn", "baochinhphu.vn", "quochoi.vn", "mod.gov.vn", "mofa.gov.vn",
    "moh.gov.vn", "moet.gov.vn", "mof.gov.vn", "sbv.gov.vn", "gso.gov.vn",
    "most.gov.vn", "mic.gov.vn", "molisa.gov.vn", "monre.gov.vn", "mt.gov.vn",
    "dangcongsan.vn", "nhandan.vn", "tapchicongsan.org.vn", "moit.gov.vn",
}
_PRESS = {
    "vnexpress.net", "tuoitre.vn", "thanhnien.vn", "dantri.com.vn",
    "vietnamnet.vn", "vtv.vn", "vov.vn", "laodong.vn", "tienphong.vn",
    "vneconomy.vn", "cafef.vn", "zingnews.vn", "baotintuc.vn", "sggp.org.vn",
    "nguoilaodong.com.vn", "vietnamplus.vn", "baophapluat.vn", "plo.vn",
    # international press
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "nytimes.com",
    "theguardian.com", "bloomberg.com", "ft.com", "afp.com",
}
_REFERENCE = {
    "wikipedia.org", "britannica.com", "who.int", "un.org", "worldbank.org",
    "imf.org", "oecd.org", "nature.com", "sciencedirect.com", "arxiv.org",
}
_LOW = {
    "reddit.com", "medium.com", "blogspot.com", "wordpress.com", "quora.com",
    "facebook.com", "x.com", "twitter.com", "pinterest.com", "tiktok.com",
    "tumblr.com", "wattpad.com",
}
# Obvious spam / scraped-content farms — extend as needed.
_BLOCKED = {
    "ebay.com", "aliexpress.com", "amazon.com",
}

# TLD-level fallbacks when the exact domain is unknown.
_TLD_TIER = {
    ".gov.vn": "official",
    ".gov": "official",
    ".edu.vn": "reference",
    ".edu": "reference",
    ".ac.vn": "reference",
    ".org.vn": "press",
}


def domain_of(url: str) -> str:
    """Registrable host of a URL, lower-cased, without a leading 'www.'."""
    if not url:
        return ""
    u = url if "://" in url else "http://" + url
    host = (urlparse(u).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _parent_domains(host: str):
    """Yield host and each parent domain: a.b.c.vn -> a.b.c.vn, b.c.vn, c.vn."""
    parts = host.split(".")
    for i in range(len(parts) - 1):
        yield ".".join(parts[i:])


def trust_tier(url: str) -> str:
    """Classify a URL/domain into a trust tier."""
    host = domain_of(url)
    if not host:
        return "neutral"
    for d in _parent_domains(host):
        if d in _BLOCKED:
            return "blocked"
        if d in _OFFICIAL:
            return "official"
        if d in _PRESS:
            return "press"
        if d in _REFERENCE:
            return "reference"
        if d in _LOW:
            return "low"
    for suffix, tier in _TLD_TIER.items():
        if host.endswith(suffix):
            return tier
    return "neutral"


def trust_score(url: str) -> float:
    """Trust score in [0, 1] for a URL/domain."""
    return TIER_SCORE.get(trust_tier(url), 0.4)


def effective_priority(source) -> int:
    """Sort priority for a configured source: higher runs first.

    Uses an explicit `priority` if set, otherwise derives one from the trust of
    the source URL (official > press > reference > neutral). Search-type sources
    (no fixed URL) get a neutral default."""
    explicit = getattr(source, "priority", None)
    if explicit is not None:
        return int(explicit)
    url = getattr(source, "url", None) or ""
    if not url:
        return 50  # search/query sources: neutral
    return int(round(trust_score(url) * 100))


def sort_sources(sources: list) -> list:
    """Sources ordered by effective priority (desc), preserving input order on ties."""
    return [s for _, s in sorted(
        enumerate(sources), key=lambda iv: (-effective_priority(iv[1]), iv[0])
    )]


def rank_search_results(
    results: list[dict],
    *,
    url_key: str = "href",
    drop_blocked: bool = True,
    min_score: float = 0.0,
) -> list[dict]:
    """Stable-sort search results by trust (desc), preserving relevance order
    within the same tier. Annotates each result with `_trust`/`_tier` and
    optionally drops blocked / below-threshold domains."""
    annotated: list[dict] = []
    for i, r in enumerate(results):
        url = r.get(url_key) or r.get("url") or r.get("link") or ""
        tier = trust_tier(url)
        score = TIER_SCORE.get(tier, 0.4)
        if drop_blocked and tier == "blocked":
            continue
        if score < min_score:
            continue
        item = dict(r)
        item["_trust"] = score
        item["_tier"] = tier
        item["_rank"] = i  # original relevance order
        annotated.append(item)
    annotated.sort(key=lambda x: (-x["_trust"], x["_rank"]))
    return annotated
