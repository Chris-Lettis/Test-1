"""Unit tests for quote verification and duplicate-evidence merging."""

import pytest

from cvreview.schemas.evidence import (
    ClaimType,
    Evidence,
    EvidenceCategory,
    EvidenceLocation,
    EvidenceState,
)
from cvreview.schemas.ingestion import SourceText, WordBox
from cvreview.verification.merge import (
    is_duplicate_pair,
    merge_duplicate_evidence,
)
from cvreview.verification.quote_check import verify_quote


def _source_text(text: str, conf: float | None = 95.0) -> SourceText:
    words = []
    pos = 0
    for w in text.split(" "):
        start = pos
        pos += len(w)
        words.append(WordBox(
            text=w, bbox=(0, 0, 10, 10), char_start=start, char_end=pos,
            confidence=conf, source="ocr",
        ))
        pos += 1
    return SourceText(page_number=2, text=text, words=words, source="ocr")


PAGE_TEXT = (
    "Personally organised and assembled all composite moulds for the front "
    "wing, rear wing, and nosecose; organised and led team trips to the "
    "carbon fibre sponsor to complete layup work."
)


class TestVerifyQuote:
    def test_exact_quote_passes(self):
        st = _source_text(PAGE_TEXT)
        check = verify_quote("assembled all composite moulds", st)
        assert check.passed
        assert not check.confidence_downgrade

    def test_hallucinated_quote_fails(self):
        st = _source_text(PAGE_TEXT)
        check = verify_quote("won the Formula Student world championship", st)
        assert not check.passed
        assert check.check == "QUOTE_MATCH"

    def test_low_ocr_confidence_downgrades(self):
        st = _source_text(PAGE_TEXT, conf=55.0)
        check = verify_quote("assembled all composite moulds", st)
        assert check.passed
        assert check.confidence_downgrade


def _evidence(eid: str, quote: str, pages: list[int]) -> Evidence:
    return Evidence(
        evidence_id=eid,
        packet_id="808_0000",
        claim_type=ClaimType.STATED_METRIC,
        category=EvidenceCategory.ACHIEVEMENT,
        raw_quote=quote,
        locations=[
            EvidenceLocation(packet_id="808_0000", page_number=p,
                             char_start=0, char_end=10, quote=quote)
            for p in pages
        ],
    )


class TestMerge:
    def test_near_identical_quotes_merge(self):
        a = _evidence("EV-1", "reducing required fasteners from 16 to 7 while achieving a 30% mass reduction", [2])
        b = _evidence("EV-2", "reducing required fasteners from 16 to 7 while achieving a 30% mass saving", [4])
        assert is_duplicate_pair(a, b)
        merged = merge_duplicate_evidence(a, b)
        assert {l.page_number for l in merged.locations} == {2, 4}
        assert "merged duplicate evidence EV-2" in merged.ambiguity_notes[0]

    def test_different_facts_do_not_merge(self):
        a = _evidence("EV-1", "led a team of eight aerodynamicists across two seasons", [2])
        b = _evidence("EV-2", "achieved 12th place overall at Formula Student UK", [3])
        assert not is_duplicate_pair(a, b)
        with pytest.raises(ValueError):
            merge_duplicate_evidence(a, b)

    def test_identical_quote_without_normalisation_still_merges(self):
        a = _evidence("EV-1", "founded and operated an AM consultancy managing customer requirements", [2])
        b = _evidence("EV-2", "founded and operated an AM consultancy managing customer requirements", [5])
        assert is_duplicate_pair(a, b)
