"""Quote resolution — the traceability workhorse (plan invariant I1).

Given a verbatim quote and a page's SourceText, resolve the character span
and the word boxes to highlight on the rendered page. Whitespace-tolerant:
OCR line breaks and spacing differences do not break resolution.
"""

from __future__ import annotations

import re

from cvreview.schemas.ingestion import SourceText, WordBox


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace; return normalized text + index map to original."""
    norm_chars: list[str] = []
    index_map: list[int] = []
    prev_ws = True  # collapse leading whitespace
    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_ws:
                norm_chars.append(" ")
                index_map.append(i)
                prev_ws = True
            continue
        norm_chars.append(ch.lower())
        index_map.append(i)
        prev_ws = False
    while norm_chars and norm_chars[-1] == " ":
        norm_chars.pop()
        index_map.pop()
    return "".join(norm_chars), index_map


def resolve_quote(
    source_text: SourceText, quote: str
) -> tuple[int, int, list[WordBox]] | None:
    """Find a quote in the page text.

    Returns (char_start, char_end, word_boxes) or None if not found.
    Matching is case-insensitive and whitespace-collapsing.
    """
    if not quote.strip():
        return None
    norm_text, index_map = _normalize_with_map(source_text.text)
    norm_quote, _ = _normalize_with_map(quote)
    if not norm_quote:
        return None

    pos = norm_text.find(norm_quote)
    if pos < 0:
        return None
    char_start = index_map[pos]
    char_end = index_map[pos + len(norm_quote) - 1] + 1

    boxes = [
        w for w in source_text.words
        if w.char_start < char_end and w.char_end > char_start
    ]
    return char_start, char_end, boxes
