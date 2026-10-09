from backend.app.tools.base import Tool, ToolDefinition
from backend.app.tools.domain import ALL_TOOLS


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Outil déjà enregistré : {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self, *, agent_id: str | None = None) -> list[ToolDefinition]:
        tools = self._tools.values()
        if agent_id:
            tools = [tool for tool in tools if tool.agent_id == agent_id]
        return sorted((tool.definition for tool in tools), key=lambda item: item.name)

    def set_enabled(self, name: str, enabled: bool) -> ToolDefinition:
        tool = self._tools[name]
        tool.enabled = enabled
        return tool.definition


tool_registry = ToolRegistry()
for registered_tool in ALL_TOOLS:
    tool_registry.register(registered_tool)
