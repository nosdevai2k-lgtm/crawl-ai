"""Markdown generation: clean + fit (noise-filtered) markdown from HTML.

Inspired by crawl4ai's DefaultMarkdownGenerator with BM25 content filtering.
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

import trafilatura
from bs4 import BeautifulSoup


@dataclass
class MarkdownResult:
    raw_markdown: str  # Full markdown from page
    fit_markdown: str  # Filtered/cleaned for LLM consumption
    links: list[str]   # Extracted links
    markdown_with_citations: str = ""  # Markdown with numbered citation refs
    references_markdown: str = ""      # References section


def _tokenize(text: str) -> List[str]:
    """Simple whitespace tokenizer with lowercasing."""
    return text.lower().split()


def _bm25_filter(
    chunks: List[str],
    query: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
    threshold_ratio: float = 0.25,
) -> List[str]:
    """Filter text chunks using BM25 scoring against a query.

    Keeps chunks scoring above threshold_ratio * max_score.
    """
    if not query or not chunks:
        return chunks

    query_terms = _tokenize(query)
    if not query_terms:
        return chunks

    # Build corpus
    corpus = [_tokenize(c) for c in chunks]
    avg_dl = sum(len(d) for d in corpus) / max(len(corpus), 1)

    # Document frequency
    df: defaultdict[str, int] = defaultdict(int)
    for doc in corpus:
        for term in set(doc):
            df[term] += 1

    n = len(corpus)
    scores: List[float] = []

    for doc in corpus:
        tf: defaultdict[str, int] = defaultdict(int)
        for t in doc:
            tf[t] += 1
        score = 0.0
        dl = len(doc)
        for term in query_terms:
            if df[term] == 0:
                continue
            idf = math.log((n - df[term] + 0.5) / (df[term] + 0.5) + 1)
            term_freq = tf[term]
            numerator = term_freq * (k1 + 1)
            denominator = term_freq + k1 * (1 - b + b * (dl / avg_dl))
            score += idf * (numerator / denominator)
        scores.append(score)

    if not scores or max(scores) == 0:
        return chunks

    threshold = max(scores) * threshold_ratio
    return [c for c, s in zip(chunks, scores) if s >= threshold]


_LINK_PATTERN = re.compile(
    r'!?\[((?:[^\[\]]|\[(?:[^\[\]]|\[[^\]]*\])*\])*)\]\(((?:[^()\s]|\([^()]*\))*)(?:\s+"([^"]*)")?\)'
)


def convert_links_to_citations(markdown: str) -> tuple[str, str]:
    """Convert markdown links to numbered citations with a References section.

    Returns (markdown_with_citations, references_markdown).
    """
    link_map: dict[str, tuple[int, str]] = {}
    parts: list[str] = []
    last_end = 0
    counter = 1

    for match in _LINK_PATTERN.finditer(markdown):
        parts.append(markdown[last_end:match.start()])
        text, url, title = match.groups()
        if url not in link_map:
            desc_parts = []
            if title:
                desc_parts.append(title)
            if text and text != title:
                desc_parts.append(text)
            link_map[url] = (counter, ": " + " - ".join(desc_parts) if desc_parts else "")
            counter += 1
        num = link_map[url][0]
        if match.group(0).startswith("!"):
            parts.append(f"![{text}⟨{num}⟩]")
        else:
            parts.append(f"{text}⟨{num}⟩")
        last_end = match.end()

    parts.append(markdown[last_end:])
    converted = "".join(parts)

    if not link_map:
        return markdown, ""

    refs = ["\n\n## References\n\n"]
    for url, (num, desc) in sorted(link_map.items(), key=lambda x: x[1][0]):
        refs.append(f"⟨{num}⟩ {url}{desc}\n")
    return converted, "".join(refs)


def html_to_markdown(
    html: str,
    *,
    include_links: bool = True,
    query: Optional[str] = None,
) -> MarkdownResult:
    """Convert HTML to clean markdown + fit markdown (noise removed).

    Args:
        html: Raw HTML string.
        include_links: Whether to include links in output.
        query: Optional relevance query for BM25 filtering of fit_markdown.
    """
    raw_md = trafilatura.extract(
        html,
        output_format="txt",
        include_tables=True,
        include_links=include_links,
        include_formatting=True,
        favor_recall=True,
        no_fallback=False,
    ) or ""

    # Extract links
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href and not href.startswith(("#", "javascript:")):
            links.append(href)

    # Fit markdown: remove noise, then optionally BM25 filter
    fit_md = _filter_noise(raw_md)

    if query and fit_md:
        # Split into paragraph chunks for BM25
        chunks = [p.strip() for p in re.split(r"\n{2,}", fit_md) if p.strip()]
        if chunks:
            relevant = _bm25_filter(chunks, query)
            fit_md = "\n\n".join(relevant)

    # Generate citations
    md_with_citations, refs_md = convert_links_to_citations(raw_md)

    return MarkdownResult(
        raw_markdown=raw_md,
        fit_markdown=fit_md,
        links=links,
        markdown_with_citations=md_with_citations,
        references_markdown=refs_md,
    )


def _filter_noise(text: str, *, min_line_words: int = 4) -> str:
    """Remove noisy lines: very short, repetitive nav items, boilerplate."""
    lines = text.split("\n")
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        # Keep blank lines for paragraph separation
        if not stripped:
            if kept and kept[-1] != "":
                kept.append("")
            continue
        # Keep headings
        if stripped.startswith("#"):
            kept.append(line)
            continue
        # Keep lines with enough words
        words = stripped.split()
        if len(words) >= min_line_words:
            kept.append(line)
        # Keep list items
        elif stripped.startswith(("-", "*", "•")) and len(words) >= 2:
            kept.append(line)
    # Remove trailing blanks
    while kept and kept[-1] == "":
        kept.pop()
    return "\n".join(kept)
