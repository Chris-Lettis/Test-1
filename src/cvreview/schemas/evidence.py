"""Evidence and verification schemas (plan §8–§9).

Increment 3 scope: the canonical Evidence model plus verification records.
Extraction (Increment 4) will *produce* EvidenceItems; the verification core
operates on them deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ClaimType(str, Enum):
    """What kind of statement the evidence represents (plan §8).

    STATED_* types come straight from the documents; NORMALISED_VALUE is a
    deterministic transformation; INFERRED is discouraged and always flagged
    (plan §2 R4 — minimise category 3).
    """

    STATED_FACT = "STATED_FACT"
    STATED_CLAIM = "STATED_CLAIM"          # self-assessment ("Advanced, 6+ years")
    STATED_METRIC = "STATED_METRIC"        # quantified achievement ("18%")
    NORMALISED_VALUE = "NORMALISED_VALUE"
    INFERRED = "INFERRED"                  # always flagged; reviewer-visible


class EvidenceCategory(str, Enum):
    QUALIFICATION = "QUALIFICATION"
    EMPLOYMENT = "EMPLOYMENT"
    ROLE_TITLE = "ROLE_TITLE"
    RESPONSIBILITY = "RESPONSIBILITY"
    TECHNICAL_SKILL = "TECHNICAL_SKILL"
    TOOL_SOFTWARE = "TOOL_SOFTWARE"
    PROJECT = "PROJECT"
    ACHIEVEMENT = "ACHIEVEMENT"
    DOMAIN_EXPERIENCE = "DOMAIN_EXPERIENCE"
    LEADERSHIP = "LEADERSHIP"
    DATE_FACT = "DATE_FACT"
    OTHER = "OTHER"


class EvidenceState(str, Enum):
    """Verification states (plan §6)."""

    UNVERIFIED = "UNVERIFIED"
    VERIFIED_FROM_DOCUMENT = "VERIFIED_FROM_DOCUMENT"
    AMBIGUOUS = "AMBIGUOUS"
    CONTRADICTORY = "CONTRADICTORY"
    NOT_STATED = "NOT_STATED"
    UNREADABLE = "UNREADABLE"


class EvidenceLocation(BaseModel):
    """Where in the original packet an evidence item lives (invariant I1)."""

    packet_id: str
    page_number: int
    char_start: int
    char_end: int
    bbox: tuple[float, float, float, float] | None = None
    quote: str  # verbatim, resolvable via provenance.resolve_quote


class VerificationCheck(BaseModel):
    """Result of one deterministic check against an evidence item."""

    check: str                       # e.g. QUOTE_MATCH, DATE_PARSE, ALIAS_NORMALISE
    passed: bool
    detail: str = ""
    confidence_downgrade: bool = False  # True → evidence confidence lowered


class SkillMatch(BaseModel):
    skill_id: str
    canonical: str
    matched_alias: str
    registry_version: str


class NormalisedDateRange(BaseModel):
    """A stated date range resolved to comparable values.

    open_ended ranges ("2024-Present") carry latest=None — the pipeline never
    silently substitutes 'today' for Present, because chronology checks must
    distinguish 'ongoing' from 'ended'.
    """

    raw: str
    earliest: str          # ISO: YYYY | YYYY-MM | YYYY-MM-DD
    latest: str | None = None
    precision: Literal["day", "month", "year"]
    open_ended: bool = False

    def sort_key(self, end: bool = False) -> tuple[int, int, int]:
        v = self.latest if end and self.latest else self.earliest
        parts = [int(x) for x in v.split("-")]
        while len(parts) < 3:
            if len(parts) == 1:
                parts.append(12 if end else 1)
            elif len(parts) == 2:
                parts.append(28 if end else 1)
        return tuple(parts)  # type: ignore[return-value]


class Evidence(BaseModel):
    """A verified evidence item (post Stage 3)."""

    evidence_id: str
    packet_id: str
    claim_type: ClaimType = ClaimType.STATED_FACT
    category: EvidenceCategory = EvidenceCategory.OTHER
    raw_quote: str
    locations: list[EvidenceLocation] = Field(min_length=1)
    state: EvidenceState = EvidenceState.UNVERIFIED
    checks: list[VerificationCheck] = Field(default_factory=list)
    normalised_skills: list[SkillMatch] = Field(default_factory=list)
    normalised_dates: list[NormalisedDateRange] = Field(default_factory=list)
    sensitive_tags: list[str] = Field(default_factory=list)
    ambiguity_notes: list[str] = Field(default_factory=list)
    duplicate_of: str | None = None      # set on the discarded twin of a merge
    extraction_meta: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
