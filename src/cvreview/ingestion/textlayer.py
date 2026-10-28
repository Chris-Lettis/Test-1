"""Text-layer capture (Stage 1b) — the deterministic cheap path.

Used when a PDF page carries a real text layer (corpus: the ATS form pages).
Word boxes come from PyMuPDF in PDF points and are converted to the rendered
PNG pixel space so coordinates are consistent with OCR output.
"""

from __future__ import annotations

import pymupdf

from cvreview.schemas.ingestion import SourceText
from cvreview.settings import RENDER_DPI


def extract_text_layer(page_number: int, page: pymupdf.Page) -> SourceText:
    scale = RENDER_DPI / 72.0
    words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word_no)
    tuples: list[tuple[int, int, int, str, tuple[float, float, float, float], float | None]] = []
    for x0, y0, x1, y1, word, block, line, word_no in words:
        word = word.strip()
        if not word:
            continue
        bbox = (x0 * scale, y0 * scale, x1 * scale, y1 * scale)
        tuples.append(((block, line), word_no, 0, word, bbox, None))

    tuples.sort(key=lambda t: (t[0], t[1]))
    from cvreview.ingestion.wordbox import build_source_text
    return build_source_text(page_number, tuples, source="text_layer")
