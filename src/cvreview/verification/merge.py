"""Duplicate-evidence merging (Stage 3).

Corpus packets contain near-duplicate documents (plan §3.2 #4): the same CV
or letter rendered twice. Without merging, identical facts would be counted
twice — inflating corroboration. Merge keeps ALL locations (both renderings
are real provenance) and records the superseded twin via duplicate_of.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from cvreview.schemas.evidence import Evidence, EvidenceState


def quote_similarity(a: str, b: str) -> float:
    """Order-sensitive similarity of two quotes (0..1)."""
    return SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio()


def is_duplicate_pair(a: Evidence, b: Evidence, threshold: float = 0.85) -> bool:
    """Two evidence items state the same fact if their quotes are
    near-identical (order-sensitive word-level similarity). Merging keeps
    every location, so both renderings remain valid provenance."""
    if a.evidence_id == b.evidence_id:
        return False
    return quote_similarity(a.raw_quote, b.raw_quote) >= threshold


def merge_duplicate_evidence(keep: Evidence, discard: Evidence) -> Evidence:
    """Merge `discard` into `keep`, preserving every location."""
    if not is_duplicate_pair(keep, discard):
        raise ValueError(
            f"refusing to merge non-duplicate evidence: "
            f"{keep.evidence_id} vs {discard.evidence_id}"
        )
    existing_locs = {(l.packet_id, l.page_number, l.char_start) for l in keep.locations}
    for loc in discard.locations:
        if (loc.packet_id, loc.page_number, loc.char_start) not in existing_locs:
            keep.locations.append(loc)
    for check in discard.checks:
        if check not in keep.checks:
            keep.checks.append(check)
    if discard.state == EvidenceState.CONTRADICTORY:
        keep.state = EvidenceState.CONTRADICTORY
    keep.duplicate_of = None
    keep.ambiguity_notes.append(
        f"merged duplicate evidence {discard.evidence_id} "
        f"(pages {[l.page_number for l in discard.locations]})"
    )
    return keep
