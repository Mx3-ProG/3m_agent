from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(slots=True)
class AgentDescriptor:
    id: str
    name: str
    description: str
    capabilities: list[str]
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    state: str = "available"
    error: str | None = None


class Agent(ABC):
    descriptor: AgentDescriptor

    @abstractmethod
    async def can_handle(self, intent: str) -> bool:
        raise NotImplementedError


class CapabilityAgent(Agent):
    def __init__(self, descriptor: AgentDescriptor) -> None:
        self.descriptor = descriptor

    async def can_handle(self, intent: str) -> bool:
        normalized = intent.casefold()
        return any(
            capability.casefold() in normalized for capability in self.descriptor.capabilities
        )
