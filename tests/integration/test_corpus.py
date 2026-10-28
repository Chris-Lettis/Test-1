"""Integration test: ingest the 7 corpus packets and check the full 39-page
ground truth established during document analysis (plan §3.1) plus the
duplicate groups the architecture must catch.

Skipped automatically when data/raw is absent (e.g. fresh clone — candidate
data never enters source control).
"""

from pathlib import Path

import pytest

from cvreview.ingestion.packet import ingest_packet
from cvreview.settings import PACKETS_DIR, RAW_DIR
from cvreview.schemas.ingestion import DocType

pytestmark = pytest.mark.skipif(
    not any(RAW_DIR.glob("*.pdf")), reason="corpus PDFs not present"
)

# Ground truth per packet id -> list of expected page types (1-based order)
GROUND_TRUTH: dict[str, list[str]] = {
    "808_5422": ["FORM", "CV", "NO_DATA"],
    "808_6934": ["FORM", "CV", "CV", "DIVIDER", "CV", "COVER_LETTER", "BLANK"],
    "808_7533": ["FORM", "CV", "CV", "DIVIDER", "COVER_LETTER", "BLANK"],
    "808_7949": ["FORM", "CV", "CV", "CV", "COVER_LETTER", "BLANK"],
    "808_9158": ["FORM", "CV", "DIVIDER", "COVER_LETTER", "BLANK"],
    "808_9411": ["FORM", "CV", "CV", "COVER_LETTER", "DIVIDER", "COVER_LETTER", "BLANK"],
    "808_9754": ["FORM", "CV", "CV", "COVER_LETTER", "BLANK"],
}

EXPECTED_DUP_GROUPS: dict[str, set[frozenset[str]]] = {
    # doc ids are DOC-<first page>; both corpus duplicates must be found
    "808_6934": {frozenset({"DOC-02", "DOC-05"})},   # CV twice
    "808_9411": {frozenset({"DOC-04", "DOC-06"})},   # letter twice
}


@pytest.fixture(scope="module")
def ingested():
    out = {}
    for pdf in sorted(RAW_DIR.glob("*.pdf")):
        packet = ingest_packet(pdf, write_pngs=True)
        out[packet.packet_id] = packet
    return out


def test_all_corpus_packets_present(ingested):
    assert set(ingested) == set(GROUND_TRUTH)


@pytest.mark.parametrize("packet_id", sorted(GROUND_TRUTH))
def test_page_types_match_ground_truth(ingested, packet_id):
    packet = ingested[packet_id]
    expected = GROUND_TRUTH[packet_id]
    actual = [p.page_type.value for p in packet.pages]
    assert actual == expected, (
        f"\n{packet_id}: page-type mismatch"
        f"\n  expected: {expected}"
        f"\n  actual:   {actual}"
        f"\n  reasons:  {[p.classification_reason for p in packet.pages]}"
    )


@pytest.mark.parametrize("packet_id", sorted(EXPECTED_DUP_GROUPS))
def test_duplicate_groups_found(ingested, packet_id):
    packet = ingested[packet_id]
    found = {frozenset(g.doc_ids) for g in packet.duplicate_groups}
    assert EXPECTED_DUP_GROUPS[packet_id] <= found, (
        f"{packet_id}: expected duplicate groups "
        f"{EXPECTED_DUP_GROUPS[packet_id]}, found {found}"
    )


def test_every_page_has_provenance(ingested):
    for packet in ingested.values():
        for page in packet.pages:
            assert page.render_path, f"{packet.packet_id} p{page.page_number}"
            assert Path(PACKETS_DIR / packet.packet_id / page.render_path).exists()
            assert page.source_text.text is not None


def test_no_cv_free_packet_marked_incomplete(ingested):
    for packet in ingested.values():
        assert not any("INCOMPLETE_PACKET" in w for w in packet.warnings), (
            f"{packet.packet_id} unexpectedly marked incomplete: {packet.warnings}"
        )


def test_provenance_resolution_end_to_end(ingested):
    """A quote from a rendered page must resolve to boxes (traceability I1)."""
    from cvreview.ingestion.provenance import resolve_quote

    packet = ingested["808_5422"]
    form_page = packet.pages[0]
    quote = "Applicant Summary"
    res = resolve_quote(form_page.source_text, quote)
    assert res is not None, "quote from text-layer page must resolve"
    _, _, boxes = res
    assert boxes, "quote must resolve to at least one word box"
