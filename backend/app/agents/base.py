from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from backend.app.tools.base import Tool, ToolContext, ToolResult


@dataclass(slots=True)
class AgentDescriptor:
    id: str
    name: str
    description: str
    capabilities: list[str]
    tools: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    enabled: bool = True
    status: str = "healthy"
    error: str | None = None
    last_used_at: datetime | None = None


class Agent(ABC):
    descriptor: AgentDescriptor

    @abstractmethod
    async def can_handle(self, intent: str) -> bool: ...

    @abstractmethod
    async def execute(self, tool: Tool, arguments: dict, context: ToolContext) -> ToolResult: ...

    @abstractmethod
    async def health_check(self) -> dict: ...


class ExecutableAgent(Agent):
    def __init__(self, descriptor: AgentDescriptor) -> None:
        self.descriptor = descriptor

    async def can_handle(self, intent: str) -> bool:
        normalized = intent.casefold()
        return any(
            capability.casefold() in normalized for capability in self.descriptor.capabilities
        )

    async def execute(self, tool: Tool, arguments: dict, context: ToolContext) -> ToolResult:
        if not self.descriptor.enabled:
            return ToolResult(
                tool_name=tool.name, status="error", error=f"{self.descriptor.name} est désactivé"
            )
        if tool.agent_id != self.descriptor.id or tool.name not in self.descriptor.tools:
            return ToolResult(
                tool_name=tool.name,
                status="error",
                error=f"L'outil {tool.name} n'appartient pas à {self.descriptor.name}",
            )
        if not tool.enabled:
            return ToolResult(tool_name=tool.name, status="error", error="Outil désactivé")
        return await tool.invoke(arguments, context)

    async def health_check(self) -> dict:
        return {
            "status": self.descriptor.status,
            "healthy": self.descriptor.enabled and self.descriptor.status == "healthy",
            "error": self.descriptor.error,
        }


CapabilityAgent = ExecutableAgent
