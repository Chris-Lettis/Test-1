"""Skill alias registry (Stage 3).

Versioned YAML registry mapping surface forms ("Star CCM+", "STARCCM+",
"catia 3dx") to canonical skill ids. Deterministic lookup only: the pipeline
may *propose* new aliases but never auto-extends the registry (plan §15) —
new aliases require human curation and a registry version bump.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from cvreview.schemas.evidence import SkillMatch
from cvreview.settings import PROJECT_ROOT

REGISTRY_DIR = PROJECT_ROOT / "config" / "registry"

_punct_re = re.compile(r"[^\w+]+")


def normalise_skill_text(text: str) -> str:
    """Canonical surface form for lookup: lowercase, punctuation→space,
    except '+' which is meaningful (STAR-CCM+, C++)."""
    t = text.strip().lower()
    t = re.sub(r"(?<!\w)\+", " plus ", t)      # standalone plus → word
    t = re.sub(r"[^\w+\s]", " ", t)            # remaining punctuation → space
    t = re.sub(r"\s+", " ", t).strip()
    return t


class SkillRegistry:
    """Loaded once per process; immutable after load."""

    def __init__(self, path: Path | None = None) -> None:
        path = path or REGISTRY_DIR / "skill-aliases-v0.1.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.version: str = data["registry_version"]
        self._alias_index: dict[str, SkillMatch] = {}
        for skill in data["skills"]:
            match = SkillMatch(
                skill_id=skill["id"],
                canonical=skill["canonical"],
                matched_alias="",  # filled per lookup
                registry_version=self.version,
            )
            for alias in [skill["canonical"], *skill.get("aliases", [])]:
                key = normalise_skill_text(alias)
                self._alias_index.setdefault(key, match)

    def lookup(self, surface: str) -> SkillMatch | None:
        key = normalise_skill_text(surface)
        m = self._alias_index.get(key)
        if m is None:
            return None
        return m.model_copy(update={"matched_alias": surface.strip()})

    def find_in_text(self, text: str) -> list[SkillMatch]:
        """Find registry skills mentioned in free text (word-boundary scan).

        Used for deterministic prefiltering (plan §11 stage 4 step 1); it is
        deliberately conservative — only exact surface forms are matched.
        """
        norm = normalise_skill_text(text)
        found: dict[str, SkillMatch] = {}
        for key, match in self._alias_index.items():
            pattern = r"(?<![\w])" + re.escape(key) + r"(?![\w])"
            if re.search(pattern, norm):
                if match.skill_id not in found:
                    found[match.skill_id] = match.model_copy(
                        update={"matched_alias": key}
                    )
        return list(found.values())


@lru_cache(maxsize=1)
def default_registry() -> SkillRegistry:
    return SkillRegistry()
