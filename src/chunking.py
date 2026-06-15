"""Content chunking strategies for large documents before LLM processing.

Inspired by crawl4ai's chunking (topic-based, regex, sentence-level).
Splits large text into manageable chunks for LLM context windows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    index: int
    start_char: int
    end_char: int


def chunk_by_heading(text: str, *, max_chars: int = 12000) -> list[Chunk]:
    """Split text at markdown headings, merging small sections.

    Keeps heading context with its content. Merges consecutive
    small sections until max_chars is reached.
    """
    parts = re.split(r"(?=^#{1,4}\s)", text, flags=re.MULTILINE)
    if not parts or (len(parts) == 1 and not parts[0].strip()):
        parts = [text]

    chunks: list[Chunk] = []
    current = ""
    current_start = 0
    pos = 0

    for part in parts:
        if not part.strip():
            pos += len(part)
            continue
        if len(current) + len(part) <= max_chars:
            if not current:
                current_start = pos
            current += part
        else:
            if current.strip():
                chunks.append(Chunk(
                    text=current.strip(),
                    index=len(chunks),
                    start_char=current_start,
                    end_char=current_start + len(current),
                ))
            current_start = pos
            current = part
        pos += len(part)

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            index=len(chunks),
            start_char=current_start,
            end_char=current_start + len(current),
        ))

    return chunks or [Chunk(text=text, index=0, start_char=0, end_char=len(text))]


def chunk_by_tokens(text: str, *, max_chars: int = 12000, overlap: int = 200) -> list[Chunk]:
    """Split text into fixed-size chunks with overlap.

    Simple character-based splitting with overlap for context continuity.
    Tries to break at paragraph or sentence boundaries.
    """
    if len(text) <= max_chars:
        return [Chunk(text=text, index=0, start_char=0, end_char=len(text))]

    chunks: list[Chunk] = []
    start = 0

    while start < len(text):
        end = start + max_chars

        if end < len(text):
            # Try to break at paragraph
            para_break = text.rfind("\n\n", start + max_chars // 2, end)
            if para_break > start:
                end = para_break
            else:
                # Try sentence boundary
                sent_break = text.rfind(". ", start + max_chars // 2, end)
                if sent_break > start:
                    end = sent_break + 1

        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(Chunk(
                text=chunk_text,
                index=len(chunks),
                start_char=start,
                end_char=end,
            ))

        start = max(start + 1, end - overlap)

    return chunks or [Chunk(text=text, index=0, start_char=0, end_char=len(text))]


def chunk_by_separator(text: str, *, separator: str = "\n\n", max_chars: int = 12000) -> list[Chunk]:
    """Split text at a separator pattern, merging small parts."""
    parts = text.split(separator)
    chunks: list[Chunk] = []
    current = ""
    pos = 0

    for part in parts:
        if len(current) + len(part) + len(separator) <= max_chars:
            current += (separator if current else "") + part
        else:
            if current.strip():
                chunks.append(Chunk(
                    text=current.strip(),
                    index=len(chunks),
                    start_char=pos - len(current),
                    end_char=pos,
                ))
            current = part
        pos += len(part) + len(separator)

    if current.strip():
        chunks.append(Chunk(
            text=current.strip(),
            index=len(chunks),
            start_char=pos - len(current),
            end_char=pos,
        ))

    return chunks or [Chunk(text=text, index=0, start_char=0, end_char=len(text))]
