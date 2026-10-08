from pathlib import Path

from backend.app.agents.base import AgentDescriptor, CapabilityAgent
from backend.app.agents.registry import AgentRegistry
from backend.app.skills.registry import SkillRegistry


def test_agent_registry_registers_and_unregisters():
    registry = AgentRegistry()
    agent = CapabilityAgent(
        AgentDescriptor(id="test", name="Test", description="Test", capabilities=["essai"])
    )
    registry.register(agent)
    assert registry.get_agent("test") is agent
    assert registry.get_capabilities() == {"test": ["essai"]}
    registry.unregister("test")
    assert registry.list_agents() == []


def test_skill_registry_discovers_manifests():
    registry = SkillRegistry(Path("skills"))
    skills = registry.discover()
    assert {skill.id for skill in skills} == {"tasks", "calendar"}
