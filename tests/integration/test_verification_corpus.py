"""Integration: verification core against the real corpus.

Self-consistency quote checks on every page, a date-parse sweep over every
year-range pattern found, and alias resolution on a known CV page.
"""

import re

import pytest

from cvreview.ingestion.packet import ingest_packet
from cvreview.ingestion.provenance import resolve_quote
from cvreview.settings import RAW_DIR
from cvreview.verification.aliases import default_registry
from cvreview.verification.dates import parse_date_range

pytestmark = pytest.mark.skipif(
    not any(RAW_DIR.glob("*.pdf")), reason="corpus PDFs not present"
)

YEAR_RANGE_RE = re.compile(
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(?:19|20)\d{2}"
    r"\s*(?:-|–|—|to)\s*(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+"
    r"(?:19|20)\d{2}|present|(?:19|20)\d{2})"
    r"|(?:19|20)\d{2}\s*(?:-|–|—|to)\s*(?:(?:19|20)\d{2}|present)",
    re.I,
)


@pytest.fixture(scope="module")
def packets():
    return [ingest_packet(pdf, write_pngs=False) for pdf in sorted(RAW_DIR.glob("*.pdf"))]


def test_quote_self_consistency_all_pages(packets):
    """Any sentence-length span of a page's captured text must resolve back
    to that page (provenance round-trip, invariant I1)."""
    checked = 0
    for packet in packets:
        for page in packet.pages:
            text = page.source_text.text
            sentences = [
                s.strip() for s in re.split(r"[.\n]", text)
                if 25 <= len(s.strip()) <= 200
            ]
            if not sentences:
                continue
            probe = max(sentences, key=len)
            res = resolve_quote(page.source_text, probe)
            assert res is not None, (
                f"{packet.packet_id} p{page.page_number}: self-quote failed: {probe!r}"
            )
            checked += 1
    assert checked > 25  # sanity: the sweep actually exercised the corpus
    # (not every page qualifies: dividers, blanks and form label lists have
    # no sentence-length span — 27/39 in the current corpus)


def test_date_sweep_all_year_ranges_parse(packets):
    """Every year-range pattern visible in captured text must normalise."""
    total = 0
    for packet in packets:
        for page in packet.pages:
            for m in YEAR_RANGE_RE.finditer(page.source_text.text):
                phrase = m.group(0)
                parsed = parse_date_range(phrase)
                assert parsed is not None, (
                    f"{packet.packet_id} p{page.page_number}: "
                    f"unparsed date {phrase!r}"
                )
                total += 1
    assert total > 20


def test_known_alias_surface_forms_resolve(packets):
    registry = default_registry()
    thomson_cv = next(
        p for pkt in packets if pkt.packet_id == "808_5422"
        for p in pkt.pages if p.page_number == 2
    )
    ids = {m.skill_id for m in registry.find_in_text(thomson_cv.source_text.text)}
    assert {"SKILL-SOLIDWORKS", "SKILL-PYTHON", "SKILL-MATLAB",
            "SKILL-STAR-CCM-PLUS"} <= ids, ids


def test_registry_version_stable():
    assert default_registry().version == "0.1.0"
