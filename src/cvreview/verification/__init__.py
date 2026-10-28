"""Deterministic verification core — Stage 3 (plan §7, Increment 3)."""

from cvreview.verification.aliases import SkillRegistry, normalise_skill_text
from cvreview.verification.dates import parse_date_range, ranges_overlap
from cvreview.verification.merge import merge_duplicate_evidence
from cvreview.verification.quote_check import verify_quote

__all__ = [
    "SkillRegistry",
    "normalise_skill_text",
    "parse_date_range",
    "ranges_overlap",
    "merge_duplicate_evidence",
    "verify_quote",
]
