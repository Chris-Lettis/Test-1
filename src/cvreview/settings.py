"""Central settings for the cvreview pipeline.

All tunable thresholds live here and are recorded in audit events so any
artifact can be traced to the configuration that produced it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import cvreview

# ---------------------------------------------------------------------------
# Versions recorded into every artifact / audit event
# ---------------------------------------------------------------------------
VERSIONS = {
    "software": cvreview.__version__,
    "ingestion_stage": "1.0.0",  # stage contract version (plan §7)
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../Test-1
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PACKETS_DIR = DATA_DIR / "packets"


def _find_tesseract() -> str:
    """Locate the tesseract binary (PATH first, then common Windows installs)."""
    found = shutil.which("tesseract")
    if found:
        return found
    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        str(Path.home() / r"AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "tesseract"  # let pytesseract raise a clear error later


TESSERACT_CMD = _find_tesseract()
OCR_LANGUAGE = "eng"

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
RENDER_DPI = 200  # archive PNGs + OCR input (corpus text is large enough)

# --- Text-layer vs OCR routing (corpus-informed) ----------------------------
# ATS exports overlay sparse text (section banners, footers) on image-page
# bodies, and some pages carry image content NOT present in their text layer
# (observed: 808_5422 p2 = 6-word layer over a full CV image; 808_9754 p3 =
# banner-only layer over an orphaned CV fragment). A text layer is therefore
# trusted only when it is genuinely rich; every other page is OCR'd so the
# full visible content — banners included — is captured.
TEXT_LAYER_RICH_WORDS = 40       # ≥ this many words → trust the text layer

# ---------------------------------------------------------------------------
# Page classification thresholds (derived from corpus analysis, plan §3)
# ---------------------------------------------------------------------------
BLANK_INK_RATIO = 0.001        # below this the page is blank (corpus blanks ≈0.0005)
BLANK_MAX_WORDS = 1            # ...or only a page footer remains at low ink
NO_DATA_MAX_WORDS = 12         # "No data available" + footer at most
DIVIDER_MAX_WORDS = 6          # a clean divider page carries only its heading
MIXED_FRAGMENT_MAX_WORDS = 25  # tiny fragment after a CV page → continuation

# Section keywords that identify CV content (plan §3.3; corpus-informed)
CV_SECTION_KEYWORDS = [
    "personal profile", "profile", "technical skills", "key skills",
    "software proficiency", "proficiencies", "experience", "work experience",
    "engineering experience", "education", "university education",
    "projects", "selected projects", "achievements", "extracurricular",
    "interests", "hobbies", "relevant modules", "voluntary", "volunteering",
    "additional information", "courses", "certifications",
]

# Signals that identify cover-letter content
LETTER_SALUTATION_RE = r"\bdear\b"
LETTER_SIGNOFF_RE = (
    r"yours (faithfully|sincerely)|kind regards|best regards|"
    r"thank you for considering"
)

# Year-range density: CVs are structured around multi-year date ranges
# ("2024-Present", "Sep 2025 - Feb 2026"); letters carry at most a single
# letter date. Corpus-informed second signal for pages whose headings OCR
# poorly (observed: 808_9754's small-caps two-column CV).
YEAR_RANGE_RE = r"\b(19|20)\d{2}\s*[-–—]\s*((19|20)\d{2}|present)"

DIVIDER_HEADINGS = {"cover letter", "curriculum vitae", "cv", "references"}

FOOTER_RE = r"page \d+ of \d+"
