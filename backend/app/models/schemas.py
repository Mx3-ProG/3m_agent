import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    conversation_id: str | None = None
    provider: Literal["demo", "openai", "anthropic", "ollama"] | None = None
    model: str | None = Field(default=None, max_length=120)
    preferred_agent: str | None = Field(default=None, max_length=80)


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: str
    response: str
    provider: str
    model: str
    execution_id: str | None = None
    state: str = "responding"
    agents_used: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    confirmation_id: str | None = None


class MessageRead(ORMModel):
    id: str
    role: str
    content: str
    provider: str | None
    model: str | None
    agent_used: str | None = None
    tools_used: list[str] = Field(default_factory=list)
    execution_id: str | None = None
    created_at: datetime

    @field_validator("tools_used", mode="before")
    @classmethod
    def parse_tools(cls, value):
        return json.loads(value) if isinstance(value, str) else value


class ConversationRead(ORMModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime
    status: str
    summary: str = ""
    active_topic: str = ""


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: Literal["active", "archived"] | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    status: Literal["open", "in_progress", "done"] | None = None
    due_at: datetime | None = None


class TaskRead(ORMModel):
    id: str
    title: str
    description: str
    priority: str
    status: str
    due_at: datetime | None
    created_at: datetime


class EventCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    starts_at: datetime
    ends_at: datetime
    location: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_range(self) -> "EventCreate":
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at doit être postérieur à starts_at")
        return self


class EventRead(ORMModel):
    id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    location: str
    notes: str
    source: str

    @field_serializer("starts_at", "ends_at")
    def serialize_utc(self, value: datetime) -> str:
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat()


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="preference", min_length=1, max_length=40)
    sensitive: bool = False


class MemoryRead(ORMModel):
    id: str
    content: str
    category: str
    sensitive: bool
    created_at: datetime


class ConfirmationRequest(BaseModel):
    confirmation_id: str
