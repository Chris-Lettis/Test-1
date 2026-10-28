"""Quote verification (Stage 3).

Deterministic check that an evidence item's verbatim quote actually occurs in
the captured source text of the page it cites. This is the primary defence
against extraction hallucination (plan §7 Stage 3): any quote that does not
resolve fails QUOTE_MATCH and the evidence cannot reach
VERIFIED_FROM_DOCUMENT.
"""

from __future__ import annotations

from cvreview.ingestion.provenance import resolve_quote
from cvreview.schemas.evidence import VerificationCheck
from cvreview.schemas.ingestion import SourceText

LOW_OCR_CONFIDENCE = 80.0  # mean word confidence below this downgrades


def verify_quote(quote: str, source_text: SourceText) -> VerificationCheck:
    """Verify a quote against one page's captured text.

    Passing requires an exact (whitespace/case-tolerant) match. Low OCR
    confidence on the matched span still passes the check but downgrades
    confidence (plan §14) — presence is verified, legibility is separate.
    """
    res = resolve_quote(source_text, quote)
    if res is None:
        return VerificationCheck(
            check="QUOTE_MATCH",
            passed=False,
            detail=f"quote not found in page {source_text.page_number} "
                   f"({source_text.source})",
        )

    _, _, boxes = res
    confs = [b.confidence for b in boxes if b.confidence is not None]
    if confs and (sum(confs) / len(confs)) < LOW_OCR_CONFIDENCE:
        return VerificationCheck(
            check="QUOTE_MATCH",
            passed=True,
            detail=f"quote found on page {source_text.page_number} "
                   f"but OCR confidence is low",
            confidence_downgrade=True,
        )
    return VerificationCheck(
        check="QUOTE_MATCH",
        passed=True,
        detail=f"quote verified on page {source_text.page_number} "
               f"({len(boxes)} words)",
    )
