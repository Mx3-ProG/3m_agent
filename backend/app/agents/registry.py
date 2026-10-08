from backend.app.agents.base import Agent, AgentDescriptor, CapabilityAgent


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        if agent.descriptor.id in self._agents:
            raise ValueError(f"Agent déjà enregistré : {agent.descriptor.id}")
        self._agents[agent.descriptor.id] = agent

    def unregister(self, agent_id: str) -> None:
        self._agents.pop(agent_id, None)

    def list_agents(self) -> list[AgentDescriptor]:
        return [agent.descriptor for agent in self._agents.values()]

    def get_agent(self, agent_id: str) -> Agent | None:
        return self._agents.get(agent_id)

    def get_capabilities(self) -> dict[str, list[str]]:
        return {key: agent.descriptor.capabilities for key, agent in self._agents.items()}


agent_registry = AgentRegistry()
agent_registry.register(
    CapabilityAgent(
        AgentDescriptor(
            id="tasks",
            name="TaskAgent",
            description="Gère les tâches personnelles persistées dans SQLite.",
            capabilities=["tâche", "priorité", "échéance", "todo"],
            tools=["tasks.read", "tasks.write"],
            permissions=["tasks:read", "tasks:write", "tasks:delete:confirm"],
        )
    )
)
agent_registry.register(
    CapabilityAgent(
        AgentDescriptor(
            id="calendar",
            name="CalendarAgent",
            description="Gère le calendrier de démonstration.",
            capabilities=["calendrier", "agenda", "rendez-vous", "créneau"],
            tools=["calendar.demo"],
            permissions=["calendar:read", "calendar:write", "calendar:delete:confirm"],
        )
    )
)
