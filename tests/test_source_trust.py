"""Domain trust ranking + source prioritization."""

from __future__ import annotations

from dataclasses import dataclass

from src.source_trust import (
    domain_of,
    effective_priority,
    rank_search_results,
    sort_sources,
    trust_score,
    trust_tier,
)


def test_domain_of_strips_www_and_scheme() -> None:
    assert domain_of("https://www.vnexpress.net/abc") == "vnexpress.net"
    assert domain_of("chinhphu.vn/x") == "chinhphu.vn"
    assert domain_of("") == ""


def test_trust_tiers() -> None:
    assert trust_tier("https://chinhphu.vn/x") == "official"
    assert trust_tier("https://so-y-te.hanoi.gov.vn/x") == "official"  # .gov.vn fallback
    assert trust_tier("https://vnexpress.net/x") == "press"
    assert trust_tier("https://en.wikipedia.org/wiki/X") == "reference"
    assert trust_tier("https://reddit.com/r/x") == "low"
    assert trust_tier("https://ebay.com/itm") == "blocked"
    assert trust_tier("https://some-random-blog.xyz/p") == "neutral"


def test_trust_score_monotonic() -> None:
    assert trust_score("https://chinhphu.vn") > trust_score("https://vnexpress.net")
    assert trust_score("https://vnexpress.net") > trust_score("https://reddit.com")
    assert trust_score("https://ebay.com") == 0.0


def test_rank_search_results_orders_and_drops_blocked() -> None:
    results = [
        {"href": "https://random.xyz/a", "title": "a"},
        {"href": "https://chinhphu.vn/b", "title": "b"},
        {"href": "https://ebay.com/c", "title": "c"},      # blocked -> dropped
        {"href": "https://vnexpress.net/d", "title": "d"},
    ]
    out = rank_search_results(results)
    titles = [r["title"] for r in out]
    assert "c" not in titles                 # blocked domain removed
    assert titles[0] == "b"                  # official first
    assert titles.index("d") < titles.index("a")  # press before neutral
    assert out[0]["_tier"] == "official"


def test_rank_preserves_relevance_within_tier() -> None:
    results = [
        {"href": "https://vnexpress.net/1", "title": "1"},
        {"href": "https://tuoitre.vn/2", "title": "2"},
    ]
    out = rank_search_results(results)
    assert [r["title"] for r in out] == ["1", "2"]  # same tier -> original order


@dataclass
class _Src:
    id: str
    url: str | None = None
    priority: int | None = None


def test_effective_priority_explicit_and_derived() -> None:
    assert effective_priority(_Src("a", priority=99)) == 99
    assert effective_priority(_Src("gov", url="https://chinhphu.vn/x")) == 100
    assert effective_priority(_Src("press", url="https://vnexpress.net")) == 80
    assert effective_priority(_Src("search", url=None)) == 50


def test_sort_sources_official_first_stable() -> None:
    srcs = [
        _Src("blog", url="https://blog.xyz"),
        _Src("gov", url="https://chinhphu.vn"),
        _Src("press1", url="https://vnexpress.net"),
        _Src("press2", url="https://tuoitre.vn"),
    ]
    ordered = [s.id for s in sort_sources(srcs)]
    assert ordered[0] == "gov"
    assert ordered.index("press1") < ordered.index("press2")  # stable on tie
    assert ordered[-1] == "blog"
