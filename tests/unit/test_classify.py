"""Unit tests for deterministic page classification (Stage 1a rules)."""

import pytest

from cvreview.ingestion.classify import classify_page, normalize_text, strip_footer
from cvreview.schemas.ingestion import PageType

FOOTER = "Page 3 of 7"


def _cls(text, ink=0.05, prev=None):
    return classify_page(text, ink, previous_substantive_type=prev)


class TestHelpers:
    def test_strip_footer(self):
        assert "Page 3 of 7" not in strip_footer(f"Cover Letter\n{FOOTER}")
        assert "Cover Letter" in strip_footer(f"Cover Letter\n{FOOTER}")

    def test_normalize(self):
        assert normalize_text("  Cover\n\tLETTER  ") == "cover letter"


class TestForm:
    def test_ats_form_detected(self):
        text = ("Applicant Summary\nName\nJane Doe\nEmail\njane@example.com\n"
                "Candidate Status\nCountry of Residence\nNotice period\n" + FOOTER)
        ptype, reason, _ = _cls(text, ink=0.036)
        assert ptype == PageType.FORM
        assert "form labels" in reason


class TestNoData:
    def test_no_data_placeholder(self):
        text = f"No data available\n{FOOTER}"
        ptype, _, _ = _cls(text, ink=0.004)
        assert ptype == PageType.NO_DATA


class TestBlank:
    def test_truly_blank(self):
        ptype, _, _ = _cls("", ink=0.0005)
        assert ptype == PageType.BLANK

    def test_footer_only_counts_as_blank(self):
        # corpus: 808_9411 p5 — a footer line and a rule, nothing else
        ptype, _, _ = _cls(FOOTER, ink=0.0016)
        assert ptype == PageType.BLANK

    def test_substantive_page_is_not_blank(self):
        text = "Engineering Experience\nDesigned wings\nEducation\n" + FOOTER
        ptype, _, _ = _cls(text, ink=0.10)
        assert ptype != PageType.BLANK


class TestDivider:
    def test_clean_divider(self):
        text = f"Cover Letter\n{FOOTER}"
        ptype, reason, _ = _cls(text, ink=0.006)
        assert ptype == PageType.DIVIDER
        assert "section heading" in reason

    def test_divider_with_fragment_is_not_clean(self):
        # corpus: 808_9754 p3 — one orphaned CV line + divider banner
        text = f"Overall Team Winners\nCover Letter\n{FOOTER}"
        ptype, _, flags = _cls(text, ink=0.008, prev=PageType.CV.value)
        assert ptype == PageType.CV
        assert "fragment_continuation" in flags
        assert "divider_text_present" in flags
        assert "needs_review" in flags


class TestContent:
    CV_TEXT = (
        "Personal Profile\nEngineering student with Formula Student experience.\n"
        "Technical Skills\nCAD, CFD, Python\n"
        "Engineering Experience\nDesigned the front wing\n"
        "Education\nMEng Mechanical Engineering\n" + FOOTER
    )

    LETTER_TEXT = (
        "Dear Sir/Madam,\n\n"
        "I am writing to apply for the placement. I have experience in design.\n"
        "Thank you for considering my application.\n\n"
        "Yours faithfully,\nSam\n" + FOOTER
    )

    def test_cv_by_keywords(self):
        ptype, reason, _ = _cls(self.CV_TEXT, ink=0.10)
        assert ptype == PageType.CV
        assert "cv_heading_lines" in reason

    def test_letter_by_signals(self):
        ptype, _, _ = _cls(self.LETTER_TEXT, ink=0.08)
        assert ptype == PageType.COVER_LETTER

    def test_cv_page_with_trailing_divider_banner(self):
        # corpus: 808_5422 p2 — full CV plus 'Cover Letter' banner at the foot
        text = self.CV_TEXT + "\nCover Letter\n"
        ptype, _, flags = _cls(text, ink=0.12)
        assert ptype == PageType.CV
        assert "divider_fragment" in flags

    def test_unknown_substantive(self):
        text = "Some ambiguous content that matches nothing we know.\n" + FOOTER
        ptype, reason, flags = _cls(text, ink=0.02)
        assert ptype == PageType.UNKNOWN_SUBSTANTIVE
        # needs_review is derived by the orchestrator from UNKNOWN_SUBSTANTIVE;
        # the pure classifier only reports the type and its reason.
        assert flags == []

    def test_fragment_continuation_after_cv(self):
        # corpus: 808_7949 p4 — a truncated interests line continuing p3
        text = ("climbing, including multi-day treks across the mountain "
                "range and Alps.\n" + FOOTER)
        ptype, _, flags = _cls(text, ink=0.004, prev=PageType.CV.value)
        assert ptype == PageType.CV
        assert "fragment_continuation" in flags

    def test_fragment_not_continuing_letter(self):
        text = "some stray words here\n" + FOOTER
        ptype, _, _ = _cls(text, ink=0.004, prev=PageType.COVER_LETTER.value)
        assert ptype == PageType.UNKNOWN_SUBSTANTIVE

    def test_year_range_fallback_for_poor_ocr_layouts(self):
        # corpus: 808_9754 p2 — small-caps two-column CV whose headings OCR
        # poorly (exactly one heading line survived); year-range density is
        # the structural fallback
        text = ("Contact Details\n"
                "Proficiencies\n"
                "Head Engineer 2026-Present Managing the design\n"
                "Head of Aerodynamics 2025-2026 Led a team of nine\n"
                "UGRacing Aerodynamics Member 2024-2025\n"
                "Designed aero package\n" + FOOTER)
        ptype, reason, flags = _cls(text, ink=0.24)
        assert ptype == PageType.CV
        assert "year_ranges" in reason
        assert "low_heading_confidence" in flags


class TestRuleOrder:
    def test_form_beats_blank_rule(self):
        # A form page has modest ink but must classify as FORM (rule order).
        text = ("Applicant Summary\nName\nX\nCandidate Status\n"
                "Country of Residence\n" + FOOTER)
        ptype, _, _ = _cls(text, ink=0.0005)
        assert ptype == PageType.FORM
