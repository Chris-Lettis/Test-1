"""Packet ingestion pipeline — Stage 1 (plan §7)."""

from cvreview.ingestion.classify import classify_page, normalize_text, strip_footer
from cvreview.ingestion.duplicates import dhash_image, group_duplicates, text_similarity
from cvreview.ingestion.packet import ingest_packet

__all__ = [
    "classify_page",
    "normalize_text",
    "strip_footer",
    "dhash_image",
    "group_duplicates",
    "text_similarity",
    "ingest_packet",
]
