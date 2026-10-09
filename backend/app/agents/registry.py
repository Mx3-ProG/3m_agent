from datetime import UTC, datetime

from backend.app.agents.base import Agent, AgentDescriptor, ExecutableAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.descriptor.id in self._agents:
            raise ValueError(f"Agent déjà enregistré : {agent.descriptor.id}")
        self._agents[agent.descriptor.id] = agent

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def list_agents(self, *, include_disabled: bool = True) -> list[AgentDescriptor]:
        agents = [agent.descriptor for agent in self._agents.values()]
        if not include_disabled:
            agents = [descriptor for descriptor in agents if descriptor.enabled]
        return sorted(agents, key=lambda item: item.id)

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def get_capabilities(self, *, enabled_only: bool = False) -> dict[str, list[str]]:
        return {
            key: agent.descriptor.capabilities
            for key, agent in self._agents.items()
            if not enabled_only or agent.descriptor.enabled
        }

    def set_enabled(self, agent_id: str, enabled: bool) -> AgentDescriptor:
        agent = self._agents[agent_id]
        agent.descriptor.enabled = enabled
        agent.descriptor.status = "healthy" if enabled else "disabled"
        return agent.descriptor

    def mark_used(self, agent_id: str) -> None:
        self._agents[agent_id].descriptor.last_used_at = datetime.now(UTC)


agent_registry = AgentRegistry()
agent_registry.register(
    ExecutableAgent(
        AgentDescriptor(
            id="tasks",
            name="TaskAgent",
            description="Gère réellement les tâches personnelles persistées dans SQLite.",
            capabilities=[
                "list_tasks",
                "create_task",
                "update_task",
                "complete_task",
                "delete_task",
            ],
            tools=[
                "tasks.list",
                "tasks.create",
                "tasks.update",
                "tasks.complete",
                "tasks.delete",
            ],
            permissions=["tasks.read", "tasks.write"],
        )
    )
)
agent_registry.register(
    ExecutableAgent(
        AgentDescriptor(
            id="calendar",
            name="CalendarAgent",
            description="Interroge et modifie le calendrier SQLite de démonstration.",
            capabilities=[
                "list_events",
                "find_free_slots",
                "create_event",
                "update_event",
                "delete_event",
            ],
            tools=[
                "calendar.list_events",
                "calendar.find_free_slots",
                "calendar.create_event",
                "calendar.update_event",
                "calendar.delete_event",
            ],
            permissions=["calendar.read", "calendar.write"],
        )
    )
)
