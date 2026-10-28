"""Unit tests for date parsing (corpus-informed formats, plan §3.2 #11)."""

import pytest

from cvreview.verification.dates import parse_date_range, ranges_overlap


class TestRanges:
    def test_month_year_to_present(self):
        r = parse_date_range("Feb 2025 - Present")
        assert r is not None
        assert r.earliest == "2025-02"
        assert r.open_ended and r.latest is None
        assert r.precision == "month"

    def test_month_year_both_sides(self):
        r = parse_date_range("September 2024 - February 2026")
        assert r is not None
        assert r.earliest == "2024-09"
        assert r.latest == "2026-02"
        assert not r.open_ended

    def test_year_to_present(self):
        r = parse_date_range("2024-Present")
        assert r is not None
        assert r.earliest == "2024"
        assert r.open_ended
        assert r.precision == "year"

    def test_year_pair(self):
        r = parse_date_range("2024 - 2029")
        assert r is not None
        assert r.earliest == "2024" and r.latest == "2029"

    def test_sept_abbreviation(self):
        r = parse_date_range("Sept 2022 - May 2024")
        assert r is not None
        assert r.earliest == "2022-09"

    def test_en_dash(self):
        r = parse_date_range("2024–Present")
        assert r is not None and r.open_ended

    def test_single_month_point(self):
        r = parse_date_range("Jun 2023")
        assert r is not None
        assert r.earliest == r.latest == "2023-06"

    def test_day_precision_letter_date(self):
        r = parse_date_range("8th September 2026")
        assert r is not None
        assert r.earliest == "2026-09-08"
        assert r.precision == "day"

    def test_unparseable_returns_none(self):
        # corpus oddity: "July 2025,2026" (808_7533) must NOT be guessed
        assert parse_date_range("July 2025,2026") is None

    def test_present_on_left_is_malformed(self):
        assert parse_date_range("Present - 2024") is None

    def test_empty(self):
        assert parse_date_range("") is None
        assert parse_date_range("   ") is None


class TestOverlap:
    def test_overlapping(self):
        a = parse_date_range("Sept 2024 - February 2026")
        b = parse_date_range("November 2024 - July 2026")
        assert ranges_overlap(a, b) is True

    def test_disjoint(self):
        a = parse_date_range("Jan 2023 - May 2024")
        b = parse_date_range("Jan 2025 - May 2026")
        assert ranges_overlap(a, b) is False

    def test_open_ended_overlaps(self):
        a = parse_date_range("2024-Present")
        b = parse_date_range("2025 - 2026")
        assert ranges_overlap(a, b) is True

    def test_open_ended_undecidable(self):
        a = parse_date_range("2024-Present")
        b = parse_date_range("2020 - 2021")
        assert ranges_overlap(a, b) is False
        c = parse_date_range("Feb 2025 - Present")
        assert ranges_overlap(a, c) is True
