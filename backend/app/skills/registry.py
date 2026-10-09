from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SkillManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    name: str
    version: str
    capabilities: list[str]
    permissions: list[str]
    dependencies: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    enabled: bool = True


class SkillRegistry:
    def __init__(self, root: Path = Path("skills")) -> None:
        self.root = root
        self._skills: dict[str, SkillManifest] = {}
        self.errors: dict[str, str] = {}

    def discover(self) -> list[SkillManifest]:
        previous_states = {key: item.enabled for key, item in self._skills.items()}
        self._skills.clear()
        self.errors.clear()
        if not self.root.exists():
            return []
        for path in self.root.glob("*/skill.yaml"):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
                manifest = SkillManifest.model_validate(data)
                if manifest.id in previous_states:
                    manifest.enabled = previous_states[manifest.id]
                self._skills[manifest.id] = manifest
            except Exception as exc:
                self.errors[path.parent.name] = str(exc)
        return self.list()

    def list(self, *, include_disabled: bool = True) -> list[SkillManifest]:
        skills = list(self._skills.values())
        if not include_disabled:
            skills = [skill for skill in skills if skill.enabled]
        return sorted(skills, key=lambda item: item.id)

    def get(self, skill_id: str) -> SkillManifest | None:
        return self._skills.get(skill_id)

    def set_enabled(self, skill_id: str, enabled: bool) -> SkillManifest:
        skill = self._skills[skill_id]
        skill.enabled = enabled
        return skill


skill_registry = SkillRegistry()
skill_registry.discover()
