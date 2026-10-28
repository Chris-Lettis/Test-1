"""Deterministic page classification (Stage 1a; plan §7).

Rules are ordered and pure: given a page's verbatim text, ink ratio and a
little document context, return a PageType plus the reason it was chosen.
No LLM is involved at this stage; genuinely ambiguous substantive pages are
typed UNKNOWN_SUBSTANTIVE and flagged for review / later stages.

Corpus-informed design notes (plan §3):
- CV section keywords are matched as STANDALONE HEADING LINES, never as
  substrings of the page blob — cover-letter prose naturally contains words
  like "experience", which substring matching turns into false CV structure.
- The clean-divider rule precedes the blank rule: divider banners add so
  little ink that some divider pages sit at the blank-ink boundary
  (observed: 808_7533 p4, ink 0.00098).
"""

from __future__ import annotations

import re

from cvreview.schemas.ingestion import PageType
from cvreview.settings import (
    BLANK_INK_RATIO,
    BLANK_MAX_WORDS,
    CV_SECTION_KEYWORDS,
    DIVIDER_HEADINGS,
    DIVIDER_MAX_WORDS,
    FOOTER_RE,
    LETTER_SALUTATION_RE,
    LETTER_SIGNOFF_RE,
    MIXED_FRAGMENT_MAX_WORDS,
    NO_DATA_MAX_WORDS,
    YEAR_RANGE_RE,
)

_FORM_LABELS = [
    "applicant summary",
    "candidate status",
    "how did you learn about this job",
    "country of residence",
    "notice period",
    "application information",
]

# A standalone heading line is short; anything longer is prose that happens
# to start with a keyword (e.g. "Experience using CAD taught me ...").
HEADING_LINE_MAX_CHARS = 45


def strip_footer(text: str) -> str:
    """Remove ATS page footers like 'Page 3 of 7'."""
    return re.sub(FOOTER_RE, " ", text, flags=re.IGNORECASE)


def normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace — the form used by all rules."""
    return re.sub(r"\s+", " ", text).strip().lower()


def _word_count(text_norm: str) -> int:
    return len(text_norm.split()) if text_norm else 0


def _form_score(text_norm: str) -> int:
    return sum(1 for label in _FORM_LABELS if label in text_norm)


def _heading_line_count(raw_text: str) -> int:
    """Count lines that look like standalone CV section headings."""
    count = 0
    for line in raw_text.splitlines():
        ln = normalize_text(strip_footer(line)).rstrip(":").strip()
        if not ln or len(ln) > HEADING_LINE_MAX_CHARS:
            continue
        if ln in CV_SECTION_KEYWORDS or any(ln.startswith(kw) for kw in CV_SECTION_KEYWORDS):
            count += 1
    return count


def _letter_signal_count(text_norm: str) -> int:
    signals = 0
    if re.search(LETTER_SALUTATION_RE, text_norm):
        signals += 1
    if re.search(LETTER_SIGNOFF_RE, text_norm):
        signals += 1
    return signals


def _year_range_count(text_norm: str) -> int:
    return len(re.findall(YEAR_RANGE_RE, text_norm))


def _is_divider_heading(text_norm_stripped: str) -> bool:
    return text_norm_stripped in DIVIDER_HEADINGS


def classify_page(
    raw_text: str,
    ink_ratio: float,
    *,
    previous_substantive_type: str | None = None,
) -> tuple[PageType, str, list[str]]:
    """Classify one page deterministically.

    Returns (page_type, reason, flags). Rules are evaluated in a fixed order;
    the first match wins. Order matters: the divider rule must precede the
    blank rule (banners add negligible ink), and both precede content
    classification because some CV pages carry a trailing section banner
    (corpus: 808_5422 p2, 808_7949 p4, 808_9754 p3).
    """
    flags: list[str] = []
    text_norm = normalize_text(raw_text)
    content_norm = normalize_text(strip_footer(raw_text))
    n_words = _word_count(content_norm)

    # 1. ATS applicant-summary form (rich text layer, known labels)
    if "applicant summary" in text_norm or _form_score(text_norm) >= 3:
        return PageType.FORM, "ATS form labels detected in text layer", flags

    # 2. ATS placeholder page
    if "no data available" in text_norm and _word_count(text_norm) <= NO_DATA_MAX_WORDS:
        return PageType.NO_DATA, "ATS 'No data available' placeholder", flags

    # 3. Clean divider: only a known section heading remains after footer strip
    if n_words <= DIVIDER_MAX_WORDS and _is_divider_heading(content_norm):
        return PageType.DIVIDER, "only a section heading present", flags

    # 4. Blank (nothing beyond, at most, a footer)
    if ink_ratio < BLANK_INK_RATIO or (
        ink_ratio < BLANK_INK_RATIO * 10 and n_words <= BLANK_MAX_WORDS
    ):
        return PageType.BLANK, f"ink_ratio={ink_ratio:.4f}, words={n_words}", flags

    # 5. Substantive page — classify content.
    divider_heading_present = any(
        h in text_norm for h in DIVIDER_HEADINGS
    ) and not _is_divider_heading(content_norm)
    if divider_heading_present:
        flags.append("divider_text_present")

    headings = _heading_line_count(raw_text)
    letter_sig = _letter_signal_count(content_norm)
    year_ranges = _year_range_count(content_norm)

    if headings >= 2:
        if divider_heading_present:
            flags.append("divider_fragment")  # banner at foot of a CV page
        return PageType.CV, f"cv_heading_lines={headings}", flags

    # Heading detection can fail on visually difficult layouts (small-caps,
    # two-column, coloured backgrounds). Year-range density is the structural
    # fallback: CVs are organised around multi-year spans, letters are not.
    if headings >= 1 and year_ranges >= 2 and letter_sig < 2:
        if divider_heading_present:
            flags.append("divider_fragment")
        flags.append("low_heading_confidence")
        return PageType.CV, (
            f"headings={headings} + year_ranges={year_ranges}"
        ), flags

    if letter_sig >= 2 and headings < 2:
        return PageType.COVER_LETTER, f"letter_signals={letter_sig}", flags

    # 6. Tiny fragment continuing the previous CV page (corpus: 808_9754 p3,
    #    808_7949 p4) — context-sensitive, hence the previous-type argument.
    if (
        previous_substantive_type == PageType.CV.value
        and n_words <= MIXED_FRAGMENT_MAX_WORDS
        and letter_sig == 0
    ):
        flags.append("fragment_continuation")
        flags.append("needs_review")
        return PageType.CV, (
            f"tiny fragment ({n_words} words) continuing previous CV page"
        ), flags

    if letter_sig >= 1 and headings < 2:
        return PageType.COVER_LETTER, f"single letter signal ({letter_sig})", flags

    return PageType.UNKNOWN_SUBSTANTIVE, (
        f"content not typed (headings={headings}, letter_sig={letter_sig}, words={n_words})"
    ), flags
