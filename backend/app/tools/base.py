from abc import ABC, abstractmethod
from enum import StrEnum
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


class PermissionLevel(StrEnum):
    SAFE_READ = "safe_read"
    WRITE = "write"
    SENSITIVE = "sensitive"
    DANGEROUS = "dangerous"


class ToolDefinition(BaseModel):
    name: str
    description: str
    agent_id: str
    skill_id: str
    permission: str
    permission_level: PermissionLevel
    requires_confirmation: bool = False
    enabled: bool = True
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]


class ToolResult(BaseModel):
    tool_name: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_ms: int = 0


class ToolContext(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    session: AsyncSession
    conversation_id: str


class Tool(ABC):
    name: str
    description: str
    agent_id: str
    skill_id: str
    permission: str
    permission_level: PermissionLevel
    requires_confirmation: bool = False
    enabled: bool = True
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            agent_id=self.agent_id,
            skill_id=self.skill_id,
            permission=self.permission,
            permission_level=self.permission_level,
            requires_confirmation=self.requires_confirmation,
            enabled=self.enabled,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
        )

    async def invoke(self, arguments: dict, context: ToolContext) -> ToolResult:
        started = perf_counter()
        try:
            validated = self.input_model.model_validate(arguments)
            output = await self.execute(validated, context)
            validated_output = self.output_model.model_validate(output)
            return ToolResult(
                tool_name=self.name,
                status="success",
                output=validated_output.model_dump(mode="json"),
                duration_ms=int((perf_counter() - started) * 1000),
            )
        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                status="error",
                error=str(exc),
                duration_ms=int((perf_counter() - started) * 1000),
            )

    @abstractmethod
    async def execute(self, arguments: BaseModel, context: ToolContext) -> BaseModel | dict: ...
