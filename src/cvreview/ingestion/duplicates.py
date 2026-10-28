"""Duplicate and near-duplicate detection (Stage 1a).

Corpus evidence (plan §3.2): packets contain near-duplicate documents in
*different renderings* (808_6934's CV twice; 808_9411's letter twice), so
exact image hashing is insufficient. Strategy:

1. exact image hash    → identical pages (strongest)
2. text similarity     → same content, different rendering (authoritative)
3. perceptual image hash (dHash) → weak signal, recorded but never alone
   used to group documents.
"""

from __future__ import annotations

import hashlib

from PIL import Image

TEXT_SIMILARITY_THRESHOLD = 0.70
DHASH_NEAR_DISTANCE = 6


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _tokens(text: str) -> set[str]:
    import re
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 2}


def text_similarity(a: str, b: str) -> float:
    """Jaccard similarity over lowercase word tokens (≥2 chars)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def dhash_image(png_bytes: bytes, hash_size: int = 8) -> int:
    """Difference hash (dHash) of a page image as a 64-bit integer."""
    import io

    img = Image.open(io.BytesIO(png_bytes))
    g = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
    px = list(g.tobytes())
    bits = 0
    for row in range(hash_size):
        for col in range(hash_size):
            left = px[row * (hash_size + 1) + col]
            right = px[row * (hash_size + 1) + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return bits


def dhash_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def group_duplicates(
    doc_texts: dict[str, str],
    doc_dhashes: dict[str, list[int]],
) -> list[tuple[list[str], str, float | None]]:
    """Group documents with the same type that are near-duplicates.

    Returns a list of (doc_ids, basis, similarity). Grouping rule:
    text similarity ≥ TEXT_SIMILARITY_THRESHOLD → group on text_similarity.
    Exact-page image matches also group. dHash similarity below the text
    threshold is *not* sufficient on its own (weak signal).
    """
    import itertools

    doc_ids = sorted(doc_texts)
    groups: list[tuple[list[str], str, float | None]] = []
    assigned: set[str] = set()

    for a, b in itertools.combinations(doc_ids, 2):
        if a in assigned or b in assigned:
            continue
        sim = text_similarity(doc_texts[a], doc_texts[b])
        if sim >= TEXT_SIMILARITY_THRESHOLD:
            groups.append(([a, b], "text_similarity", round(sim, 3)))
            assigned.update((a, b))
            continue
        # exact page match check
        ha, hb = doc_dhashes.get(a, []), doc_dhashes.get(b, [])
        if ha and hb and any(x == y for x in ha for y in hb):
            groups.append(([a, b], "exact_image", None))
            assigned.update((a, b))

    return groups
