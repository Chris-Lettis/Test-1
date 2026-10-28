"""Packet orchestration — builds the PacketModel for one candidate PDF."""

from __future__ import annotations

import io
import re
import uuid
from pathlib import Path

import pymupdf
import structlog

from cvreview.audit import AuditLog
from cvreview.ingestion.classify import PageType, classify_page
from cvreview.ingestion.duplicates import (
    DHASH_NEAR_DISTANCE,
    dhash_distance,
    dhash_image,
    file_sha256,
    group_duplicates,
)
from cvreview.ingestion.ocr import ocr_page
from cvreview.ingestion.textlayer import extract_text_layer
from cvreview.schemas.ingestion import (
    DocType,
    DocumentModel,
    DuplicateGroup,
    PageModel,
    PacketModel,
)
from cvreview.settings import (
    PACKETS_DIR,
    RENDER_DPI,
    TEXT_LAYER_RICH_WORDS,
    VERSIONS,
)

logger = structlog.get_logger()

_PACKET_ID_RE = re.compile(r"^(\d+_\d+)")


def extract_packet_id(path: Path) -> str:
    """ATS numeric id from the filename (data minimisation: never the name)."""
    m = _PACKET_ID_RE.match(path.stem)
    if not m:
        raise ValueError(f"filename does not carry an ATS packet id: {path.name}")
    return m.group(1)


def _ink_ratio(pix: pymupdf.Pixmap) -> float:
    """Fraction of sampled pixels darker than the 'ink' threshold."""
    s = pix.samples
    n_channels = pix.n
    total = 0
    dark = 0
    step = 3 * n_channels  # sample every 3rd pixel for speed
    for i in range(0, len(s), step):
        r, g, b = s[i], s[i + 1], s[i + 2]
        total += 1
        if (r + g + b) / 3 < 200:
            dark += 1
    return dark / total if total else 0.0


def _segment_documents(pages: list[PageModel]) -> list[DocumentModel]:
    """Group consecutively-typed substantive pages into documents.

    FORM stands alone; DIVIDER / BLANK / NO_DATA pages belong to no document;
    everything else groups with adjacent pages of the same type.
    """
    docs: list[DocumentModel] = []
    current: DocumentModel | None = None
    for page in pages:
        t = page.page_type
        if t in (PageType.FORM, PageType.DIVIDER, PageType.BLANK, PageType.NO_DATA):
            current = None
            if t == PageType.FORM:
                docs.append(DocumentModel(
                    doc_id=f"DOC-{page.page_number:02d}",
                    doc_type=DocType.FORM,
                    page_numbers=[page.page_number],
                ))
            continue
        if current is not None and current.doc_type.value == t.value:
            current.page_numbers.append(page.page_number)
        else:
            current = DocumentModel(
                doc_id=f"DOC-{page.page_number:02d}",
                doc_type=DocType(t.value),
                page_numbers=[page.page_number],
                flags=list(page.flags),
            )
            docs.append(current)
    return [d for d in docs if d.doc_type != DocType.FORM or len(d.page_numbers) > 0]


def ingest_packet(pdf_path: Path, *, audit_log: AuditLog | None = None,
                  write_pngs: bool = True) -> PacketModel:
    packet_id = extract_packet_id(pdf_path)
    run_id = uuid.uuid4().hex[:12]
    audit = audit_log or AuditLog(
        PACKETS_DIR / packet_id / "audit.jsonl", run_id
    )
    packet_dir = PACKETS_DIR / packet_id
    pages_dir = packet_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    audit.emit("ingestion", "INGEST_START", packet_id,
               source_file=pdf_path.name, render_dpi=RENDER_DPI)

    sha = file_sha256(pdf_path)
    doc = pymupdf.open(pdf_path)
    pages: list[PageModel] = []
    doc_dhashes: dict[str, list[int]] = {}

    for idx, page in enumerate(doc):
        page_number = idx + 1
        pix = page.get_pixmap(dpi=RENDER_DPI)
        png_bytes = pix.tobytes("png")
        if write_pngs:
            (pages_dir / f"page_{page_number:02d}.png").write_bytes(png_bytes)
        ink = _ink_ratio(pix)

        text_layer = page.get_text("text").strip()
        route_flags: list[str] = []
        if len(text_layer.split()) >= TEXT_LAYER_RICH_WORDS:
            st = extract_text_layer(page_number, page)
        else:
            st_ocr = ocr_page(page_number, png_bytes)
            # Tesseract can miss sparse isolated overlays (ATS divider
            # banners on grey backgrounds); the text layer sees them. Choose
            # whichever capture found more words; ties go to the text layer.
            st_tl = extract_text_layer(page_number, page)
            if len(st_tl.words) > len(st_ocr.words):
                st = st_tl
                route_flags.append("text_layer_over_ocr")
            else:
                st = st_ocr

        prev_type = None
        for p in reversed(pages):
            if p.page_type in (PageType.CV, PageType.COVER_LETTER):
                prev_type = p.page_type.value
                break

        ptype, reason, flags = classify_page(
            st.text, ink, previous_substantive_type=prev_type
        )
        flags.extend(route_flags)
        needs_review = "needs_review" in flags or ptype == PageType.UNKNOWN_SUBSTANTIVE

        pm = PageModel(
            page_number=page_number,
            width_pt=page.rect.width,
            height_pt=page.rect.height,
            render_path=f"pages/page_{page_number:02d}.png",
            ink_ratio=round(ink, 5),
            has_text_layer=st.source == "text_layer",
            source_text=st,
            page_type=ptype,
            classification_reason=reason,
            needs_review=needs_review,
            flags=flags,
        )
        pages.append(pm)
        audit.emit("ingestion", "PAGE_CLASSIFIED", packet_id,
                   page=page_number, page_type=ptype.value,
                   text_source=st.source, ink_ratio=round(ink, 5),
                   reason=reason, needs_review=needs_review)

    documents = _segment_documents(pages)

    # Near-duplicate detection across substantive documents
    doc_texts: dict[str, str] = {}
    for d in documents:
        doc_texts[d.doc_id] = "\n".join(
            next(p.source_text.text for p in pages if p.page_number == n)
            for n in d.page_numbers
        )
    for d in documents:
        doc_dhashes[d.doc_id] = [
            dhash_image((pages_dir / f"page_{n:02d}.png").read_bytes())
            for n in d.page_numbers
        ] if write_pngs else []

    groups: list[DuplicateGroup] = []
    for doc_ids, basis, sim in group_duplicates(doc_texts, doc_dhashes):
        gid = f"DUP-{len(groups) + 1}"
        groups.append(DuplicateGroup(group_id=gid, doc_ids=doc_ids,
                                     basis=basis, similarity=sim))
        for d in documents:
            if d.doc_id in doc_ids:
                d.flags.append(gid)
        audit.emit("ingestion", "DUPLICATES_DETECTED", packet_id,
                   group_id=gid, docs=",".join(doc_ids), basis=basis,
                   similarity=sim)

    # Weak image-similarity signals (recorded, never grouped on alone)
    if write_pngs:
        import itertools
        for a, b in itertools.combinations([d for d in documents], 2):
            da, db = doc_dhashes.get(a.doc_id, []), doc_dhashes.get(b.doc_id, [])
            if da and db and any(dhash_distance(x, y) <= DHASH_NEAR_DISTANCE
                                 for x in da for y in db):
                if not any(a.doc_id in g.doc_ids for g in groups):
                    for d in (a, b):
                        d.flags.append("image_similarity_signal")

    warnings: list[str] = []
    if not any(d.doc_type == DocType.CV for d in documents):
        warnings.append("INCOMPLETE_PACKET: no CV content identified")
    if not any(d.doc_type == DocType.COVER_LETTER for d in documents):
        warnings.append("NO_COVER_LETTER: packet metadata only, not an assessment outcome")
    for p in pages:
        if p.needs_review:
            warnings.append(f"PAGE_{p.page_number}_NEEDS_REVIEW: {p.page_type.value}")

    packet = PacketModel(
        packet_id=packet_id,
        source_file=str(pdf_path.name),
        file_sha256=sha,
        config={
            **{k: str(v) for k, v in VERSIONS.items()},
            "render_dpi": RENDER_DPI,
        },
        pages=pages,
        documents=documents,
        duplicate_groups=groups,
        warnings=warnings,
    )

    out = packet_dir / "packet.json"
    out.write_text(packet.model_dump_json(indent=2), encoding="utf-8")
    audit.emit("ingestion", "INGEST_COMPLETE", packet_id,
               pages=len(pages), documents=len(documents),
               duplicate_groups=len(groups), warnings=len(warnings),
               output=str(out.name))
    return packet
