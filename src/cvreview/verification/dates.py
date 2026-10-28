"""Stated date-range parsing (Stage 3) — deterministic, corpus-informed.

Handles the formats actually present in the corpus (plan §3.2 #11):
  "Feb 2025 - Present"          "September 2024 - February 2026"
  "2024-Present"                "2023 - 2025"          "2024 - 2029"
  "Sept 2022 - May 2024"        "Jun 2023" (single point)
  "8th September 2026"          (letter dates, day precision)
En-dashes, em-dashes and abbreviations ("Sept") included.

Matching is strict whole-phrase: leftover characters (the corpus oddity
"July 2025,2026", stray words) cause failure rather than a silently partial
parse — callers keep the raw string and flag DATE_UNPARSED (plan §18).
"""

from __future__ import annotations

import re

from cvreview.schemas.evidence import NormalisedDateRange

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_YEAR = r"(?P<year>(?:19|20)\d{2})"
_MONTH = r"(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY = r"(?P<day>\d{1,2})(?:st|nd|rd|th)?"
# right-side variants (Python re forbids duplicate group names in a pattern)
_YEAR_R = r"(?P<year2>(?:19|20)\d{2})"
_MONTH_R = r"(?P<mon2>jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DAY_R = r"(?P<day2>\d{1,2})(?:st|nd|rd|th)?"
_SEP = r"\s*(?:-|–|—|\bto\b)\s*"

_P_RANGE_MONTH = re.compile(
    rf"^(?:{_DAY}\s+)?{_MONTH}\s+{_YEAR}"
    rf"{_SEP}"
    rf"(?:(?:{_DAY_R}\s+)?{_MONTH_R}\s+{_YEAR_R}|(?P<present>present))$",
    re.I,
)
_P_RANGE_YEAR = re.compile(rf"^{_YEAR}{_SEP}(?:{_YEAR_R}|(?P<present>present))$", re.I)
_P_SINGLE_DAY = re.compile(rf"^{_DAY}\s+{_MONTH}\s+{_YEAR}$", re.I)
_P_SINGLE_MONTH = re.compile(rf"^{_MONTH}\s+{_YEAR}$", re.I)
_P_SINGLE_YEAR = re.compile(rf"^{_YEAR}$")
_P_RIGHT_DAY = re.compile(rf"^{_DAY_R}\s+{_MONTH_R}\s+{_YEAR_R}$", re.I)
_P_RIGHT_MONTH = re.compile(rf"^{_MONTH_R}\s+{_YEAR_R}$", re.I)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _month_num(m: re.Match, key: str = "mon") -> int:
    token = m.group(key)
    return 9 if token[:4] == "sept" else _MONTHS[token[:3]]


def _iso(year: str, month: int, day: str | None = None) -> str:
    if day is None:
        return f"{year}-{month:02d}"
    return f"{year}-{month:02d}-{int(day):02d}"


def parse_date_range(raw: str) -> NormalisedDateRange | None:
    """Parse a stated date phrase into a NormalisedDateRange, or None."""
    if not raw or not raw.strip():
        return None
    text = _norm(raw)

    m = _P_RANGE_MONTH.match(text)
    if m:
        earliest = _iso(m.group("year"), _month_num(m),
                        m.group("day"))  # left side (day optional)
        if m.group("present"):
            return NormalisedDateRange(
                raw=raw, earliest=earliest, latest=None,
                precision="month" if m.group("day") is None else "day",
                open_ended=True,
            )
        return _parse_range_month_right(raw, text, m, earliest)

    m = _P_RANGE_YEAR.match(text)
    if m:
        if m.group("present"):
            return NormalisedDateRange(raw=raw, earliest=m.group("year"),
                                       latest=None, precision="year",
                                       open_ended=True)
        return NormalisedDateRange(raw=raw, earliest=m.group("year"),
                                   latest=m.group("year2"), precision="year")

    m = _P_SINGLE_DAY.match(text)
    if m:
        iso = _iso(m.group("year"), _month_num(m), m.group("day"))
        return NormalisedDateRange(raw=raw, earliest=iso, latest=iso,
                                   precision="day")

    m = _P_SINGLE_MONTH.match(text)
    if m:
        iso = _iso(m.group("year"), _month_num(m))
        return NormalisedDateRange(raw=raw, earliest=iso, latest=iso,
                                   precision="month")

    m = _P_SINGLE_YEAR.match(text)
    if m:
        return NormalisedDateRange(raw=raw, earliest=m.group("year"),
                                   latest=m.group("year"), precision="year")
    return None


def _parse_range_month_right(
    raw: str, text: str, m: re.Match, earliest: str
) -> NormalisedDateRange | None:
    """Parse the right side of a month-name range (right-side groups)."""
    tail = text[m.start(0):]
    sep = re.search(r"\s*(?:-|–|—|\bto\b)\s*", tail)
    right_text = tail[sep.end():]
    right = _P_RIGHT_DAY.match(right_text) or _P_RIGHT_MONTH.match(right_text)
    if right is None:
        return None
    latest = _iso(right.group("year2"), _month_num(right, "mon2"),
                  right.groupdict().get("day2"))
    return NormalisedDateRange(
        raw=raw, earliest=earliest, latest=latest, precision="month",
    )


def ranges_overlap(
    a: NormalisedDateRange, b: NormalisedDateRange
) -> bool | None:
    """Do two stated ranges overlap? None = undecidable (one-sided open)."""
    if a.open_ended and b.open_ended:
        return True
    if a.open_ended != b.open_ended:
        open_r, closed = (a, b) if a.open_ended else (b, a)
        if closed.latest is None:
            return None
        return open_r.sort_key() <= closed.sort_key(end=True)
    return (a.sort_key() <= b.sort_key(end=True)
            and b.sort_key() <= a.sort_key(end=True))
