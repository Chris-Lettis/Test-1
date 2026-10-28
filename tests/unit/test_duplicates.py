"""Unit tests for duplicate detection and provenance resolution."""

import io

import pytest
from PIL import Image

from cvreview.ingestion.duplicates import (
    dhash_distance,
    dhash_image,
    group_duplicates,
    text_similarity,
)
from cvreview.ingestion.provenance import resolve_quote
from cvreview.schemas.ingestion import SourceText, WordBox


def _png(width=100, height=60, color=(255, 255, 255)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class TestTextSimilarity:
    def test_identical(self):
        assert text_similarity("the quick brown fox", "the quick brown fox") == 1.0

    def test_disjoint(self):
        assert text_similarity("alpha beta", "gamma delta") == 0.0

    def test_partial(self):
        sim = text_similarity("cv header name email experience education",
                              "name email experience education projects skills")
        assert 0.3 < sim < 1.0


class TestDHash:
    def test_same_image_zero_distance(self):
        b = _png()
        assert dhash_distance(dhash_image(b), dhash_image(b)) == 0

    def test_different_images_differ(self):
        # structured images (vertical split) produce gradient-dependent hashes;
        # uniform images hash to 0 by construction and are useless as probes
        def split_png(left_color, right_color):
            img = Image.new("RGB", (100, 60), left_color)
            for x in range(50, 100):
                for y in range(60):
                    img.putpixel((x, y), right_color)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()

        d1 = dhash_image(split_png((0, 0, 0), (255, 255, 255)))
        d2 = dhash_image(split_png((255, 255, 255), (0, 0, 0)))
        assert dhash_distance(d1, d2) > 0


class TestGrouping:
    def test_near_duplicate_cv_grouped(self):
        # corpus-inspired: same CV rendered twice with a different header
        body = ("engineering experience designed the front wing "
                "education meng mechanical engineering "
                "technical skills cad cfd python projects wind tunnel")
        texts = {
            "DOC-A": f"name email phone {body}",
            "DOC-B": f"placement ref 804 {body}",
            "DOC-C": "dear sir madam i am writing to apply yours faithfully",
        }
        groups = group_duplicates(texts, {})
        assert len(groups) == 1
        ids, basis, sim = groups[0]
        assert set(ids) == {"DOC-A", "DOC-B"}
        assert basis == "text_similarity"
        assert sim >= 0.70

    def test_different_docs_not_grouped(self):
        texts = {
            "DOC-A": "engineering experience education skills",
            "DOC-B": "dear sir madam yours faithfully thank you",
        }
        assert group_duplicates(texts, {}) == []

    def test_exact_image_match_groups(self):
        b = _png()
        texts = {"DOC-A": "alpha beta", "DOC-B": "gamma delta"}
        h = dhash_image(b)
        groups = group_duplicates(texts, {"DOC-A": [h], "DOC-B": [h]})
        assert len(groups) == 1
        assert groups[0][1] == "exact_image"


def _make_source_text() -> SourceText:
    text = "Personally organised and assembled all composite moulds for the front wing."
    words = []
    pos = 0
    for w in text.split(" "):
        start = pos
        pos += len(w)
        words.append(WordBox(
            text=w, bbox=(0, 0, 10, 10),
            char_start=start, char_end=pos, source="ocr",
        ))
        pos += 1  # the joining space
    return SourceText(page_number=1, text=text, words=words, source="ocr")


class TestResolveQuote:
    def test_exact_quote(self):
        st = _make_source_text()
        res = resolve_quote(st, "assembled all composite moulds")
        assert res is not None
        cs, ce, boxes = res
        assert st.text[cs:ce] == "assembled all composite moulds"
        assert [b.text for b in boxes] == ["assembled", "all", "composite", "moulds"]

    def test_whitespace_tolerant(self):
        st = _make_source_text()
        res = resolve_quote(st, "assembled  all\ncomposite   moulds")
        assert res is not None

    def test_case_insensitive(self):
        st = _make_source_text()
        assert resolve_quote(st, "ASSEMBLED ALL Composite Moulds") is not None

    def test_missing_quote_returns_none(self):
        st = _make_source_text()
        assert resolve_quote(st, "this quote does not exist anywhere") is None

    def test_empty_quote_returns_none(self):
        st = _make_source_text()
        assert resolve_quote(st, "   ") is None
