"""Word-box construction shared by the text-layer and OCR paths.

Both sources produce WordBox items with character offsets into a single
per-page verbatim text, so downstream quote resolution is identical no
matter how the words were captured.
"""

from __future__ import annotations

from cvreview.schemas.ingestion import SourceText, TextSource, WordBox


def build_source_text(
    page_number: int,
    word_tuples: list[tuple[int, int, int, str, tuple[float, float, float, float], float | None]],
    source: TextSource,
) -> SourceText:
    """Assemble a SourceText from word tuples.

    Each tuple: (line_key, word_key, unused, word, bbox, confidence).
    Words are joined with spaces; a newline separates distinct line_keys.
    char_start/char_end are computed as words are placed into the text.
    """
    words: list[WordBox] = []
    parts: list[str] = []
    pos = 0
    confs: list[float] = []

    prev_line: int | None = None
    for line_key, _wk, _u, word, bbox, conf in word_tuples:
        if prev_line is not None:
            if line_key != prev_line:
                parts.append("\n")
                pos += 1
            else:
                parts.append(" ")
                pos += 1
        start = pos
        parts.append(word)
        pos += len(word)
        words.append(WordBox(
            text=word, bbox=bbox, char_start=start, char_end=pos,
            confidence=conf, source=source,
        ))
        if conf is not None:
            confs.append(conf)
        prev_line = line_key

    text = "".join(parts)
    mean_conf = round(sum(confs) / len(confs), 1) if confs else None
    return SourceText(
        page_number=page_number, text=text, words=words,
        source=source, mean_ocr_confidence=mean_conf,
    )
