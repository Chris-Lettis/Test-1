"""Unit tests for the skill alias registry."""

import pytest

from cvreview.verification.aliases import (
    SkillRegistry,
    normalise_skill_text,
)


@pytest.fixture(scope="module")
def registry():
    return SkillRegistry()


class TestNormalisation:
    def test_punctuation_collapses(self):
        assert normalise_skill_text("STAR-CCM+") == "star ccm+"
        assert normalise_skill_text("Star CCM+") == "star ccm+"
        assert normalise_skill_text("STARCCM+") == "starccm+"

    def test_case_and_spaces(self):
        assert normalise_skill_text("  CATIA   3DX ") == "catia 3dx"


class TestLookup:
    def test_star_ccm_variants(self, registry):
        for surface in ["Star-CCM+", "STAR CCM+", "starccm+", "StarCCM+"]:
            m = registry.lookup(surface)
            assert m is not None, surface
            assert m.skill_id == "SKILL-STAR-CCM-PLUS"
            assert m.canonical == "STAR-CCM+"

    def test_catia_variants_resolve_distinctly(self, registry):
        assert registry.lookup("CATIA 3DX").skill_id == "SKILL-CATIA-3DEXPERIENCE"
        assert registry.lookup("CATIA V5").skill_id == "SKILL-CATIA-V5"
        assert registry.lookup("CATIA").skill_id == "SKILL-CATIA"

    def test_ansys_fluent_vs_generic(self, registry):
        assert registry.lookup("ANSYS Fluent").skill_id == "SKILL-ANSYS-FLUENT"
        assert registry.lookup("Ansys").skill_id == "SKILL-ANSYS"

    def test_registry_version_recorded(self, registry):
        m = registry.lookup("SolidWorks")
        assert m.registry_version == registry.version
        assert registry.version == "0.1.0"

    def test_unknown_skill_returns_none(self, registry):
        assert registry.lookup("ZBrush") is None
        assert registry.lookup("") is None


class TestFindInText:
    def test_finds_multiple(self, registry):
        text = ("Used STAR-CCM+ for CFD and SolidWorks for CAD, "
                "scripted in Python")
        ids = {m.skill_id for m in registry.find_in_text(text)}
        assert {"SKILL-STAR-CCM-PLUS", "SKILL-SOLIDWORKS", "SKILL-PYTHON"} <= ids

    def test_word_boundary_no_false_positives(self, registry):
        # 'nx' must not match inside other words
        ids = {m.skill_id for m in registry.find_in_text("anxious analysis")}
        assert "SKILL-SIEMENS-NX" not in ids
