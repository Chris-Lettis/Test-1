"""Pydantic schemas for Increment 1: packet ingestion & provenance.

These models are the canonical representation of a candidate packet after
Stage 1 (plan §7–§9). Everything downstream (extraction, verification,
mapping, assessment) must be able to trace any quote back to a PageModel
and its rendered PNG via these structures.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

TextSource = Literal["text_layer", "ocr", "none"]


class PageType(str, Enum):
    """Page-level classification (deterministic rules; plan §7 Stage 1a)."""

    FORM = "FORM"                        # ATS applicant-summary form (text layer)
    CV = "CV"                            # substantive CV content
    COVER_LETTER = "COVER_LETTER"        # substantive cover-letter content
    PORTFOLIO = "PORTFOLIO"              # image/portfolio content (future use)
    DIVIDER = "DIVIDER"                  # section banner only ("Cover Letter")
    BLANK = "BLANK"                      # no content beyond (at most) a footer
    NO_DATA = "NO_DATA"                  # ATS "No data available" placeholder
    UNKNOWN_SUBSTANTIVE = "UNKNOWN_SUBSTANTIVE"  # has content we could not type


class DocType(str, Enum):
    FORM = "FORM"
    CV = "CV"
    COVER_LETTER = "COVER_LETTER"
    PORTFOLIO = "PORTFOLIO"
    UNKNOWN_SUBSTANTIVE = "UNKNOWN_SUBSTANTIVE"
    UNKNOWN = "UNKNOWN"


class WordBox(BaseModel):
    """A single word with its bounding box and provenance.

    Coordinates are in PNG pixel space at RENDER_DPI (the same space a
    reviewer's highlight overlay will use). char_start/char_end index into
    the owning SourceText.text so any substring can be resolved to boxes.
    """

    text: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1 (pixels)
    char_start: int
    char_end: int
    confidence: float | None = None  # None for text-layer words (trusted)
    source: TextSource


class SourceText(BaseModel):
    """Verbatim text of one page with word-level provenance."""

    page_number: int
    text: str
    words: list[WordBox] = Field(default_factory=list)
    source: TextSource = "none"
    mean_ocr_confidence: float | None = None  # None unless OCR was used


class PageModel(BaseModel):
    page_number: int
    width_pt: float
    height_pt: float
    render_path: str  # relative to the packet directory
    ink_ratio: float
    has_text_layer: bool
    source_text: SourceText
    page_type: PageType
    classification_reason: str
    needs_review: bool = False
    flags: list[str] = Field(default_factory=list)  # e.g. "divider_fragment"


class DocumentModel(BaseModel):
    """A substantive document within the packet (contiguous typed pages)."""

    doc_id: str
    doc_type: DocType
    page_numbers: list[int]
    flags: list[str] = Field(default_factory=list)


class DuplicateGroup(BaseModel):
    """Documents judged to be near-duplicate renderings of the same content."""

    group_id: str
    doc_ids: list[str]
    basis: Literal["exact_image", "text_similarity", "image_hash"]
    similarity: float | None = None


class PacketModel(BaseModel):
    """Top-level output of Stage 1 for one candidate packet."""

    packet_id: str
    source_file: str  # path relative to data/raw; never committed to git
    file_sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    config: dict[str, str | int | float] = Field(default_factory=dict)
    pages: list[PageModel] = Field(default_factory=list)
    documents: list[DocumentModel] = Field(default_factory=list)
    duplicate_groups: list[DuplicateGroup] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AuditEvent(BaseModel):
    """Append-only audit record (plan §19)."""

    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str
    stage: str
    action: str
    packet_id: str | None = None
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    config: dict[str, str | int | float] = Field(default_factory=dict)
