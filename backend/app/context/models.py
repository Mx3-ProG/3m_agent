from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ContextMessage(BaseModel):
    role: str
    content: str
    created_at: datetime


class ContextEntityData(BaseModel):
    id: str
    type: str
    label: str
    position: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    source_execution_id: str | None = None
    status: str = "active"


class SystemCapabilitiesSnapshot(BaseModel):
    agents: dict[str, list[str]] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)


class TemporalContext(BaseModel):
    timezone: str
    now: datetime
    today: str
    resolved_date: str | None = None
    period: str | None = None


class ContextPackage(BaseModel):
    conversation_id: str
    current_message: str
    recent_messages: list[ContextMessage] = Field(default_factory=list)
    conversation_summary: str = ""
    active_topic: str = ""
    referenced_entities: list[ContextEntityData] = Field(default_factory=list)
    pending_actions: list[dict] = Field(default_factory=list)
    recent_agent_results: list[dict] = Field(default_factory=list)
    recent_tool_results: list[dict] = Field(default_factory=list)
    capabilities: SystemCapabilitiesSnapshot
    user_preferences: list[str] = Field(default_factory=list)
    temporal: TemporalContext
    context_build_ms: int = 0
    characters_used: int = 0
