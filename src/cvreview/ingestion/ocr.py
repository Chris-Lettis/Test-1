"""OCR capture (Stage 1b).

Uses Tesseract via pytesseract on the rendered page PNG. Tesseract's TSV
output gives word-level boxes and confidence — exactly the provenance the
pipeline requires. We never "correct" OCR text generatively: the verbatim
capture IS the provenance anchor (plan §15).
"""

from __future__ import annotations

import io

import pytesseract
from PIL import Image
from pytesseract import Output

from cvreview.schemas.ingestion import SourceText
from cvreview.settings import OCR_LANGUAGE, TESSERACT_CMD

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def ocr_page(page_number: int, png_bytes: bytes) -> SourceText:
    """OCR a rendered page into a SourceText with word-level provenance."""
    image = Image.open(io.BytesIO(png_bytes))
    data = pytesseract.image_to_data(
        image, lang=OCR_LANGUAGE, output_type=Output.DICT,
        config="--psm 3",  # automatic page segmentation (handles columns)
    )

    tuples: list[tuple[int, int, int, str, tuple[float, float, float, float], float | None]] = []
    n = len(data["text"])
    for i in range(n):
        word = (data["text"][i] or "").strip()
        conf_raw = int(float(data["conf"][i]))
        if not word or conf_raw < 0:
            continue
        conf = float(conf_raw)
        line_key = (
            data["block_num"][i], data["par_num"][i], data["line_num"][i]
        )
        x, y = data["left"][i], data["top"][i]
        w, h = data["width"][i], data["height"][i]
        tuples.append((line_key, i, 0, word, (x, y, x + w, y + h), conf))

    from cvreview.ingestion.wordbox import build_source_text
    return build_source_text(page_number, tuples, source="ocr")
