from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class SkillManifest:
    id: str
    name: str
    version: str
    capabilities: list[str]
    permissions: list[str]
    dependencies: list[str]
    enabled: bool


class SkillRegistry:
    def __init__(self, root: Path = Path("skills")) -> None:
        self.root = root
        self._skills: dict[str, SkillManifest] = {}

    def discover(self) -> list[SkillManifest]:
        self._skills.clear()
        if not self.root.exists():
            return []
        for path in self.root.glob("*/skill.yaml"):
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            manifest = SkillManifest(**data)
            self._skills[manifest.id] = manifest
        return self.list()

    def list(self) -> list[SkillManifest]:
        return sorted(self._skills.values(), key=lambda item: item.id)

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillManifest:
        skill = self._skills[skill_id]
        skill.enabled = enabled
        return skill


skill_registry = SkillRegistry()
