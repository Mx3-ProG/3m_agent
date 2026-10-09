from typing import Any, Literal

from pydantic import BaseModel, Field


class ExecutionStep(BaseModel):
    id: str
    agent_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    permission: str = ""
    requires_confirmation: bool = False
    status: Literal["pending", "running", "success", "error", "waiting_confirmation"] = "pending"


class ExecutionPlan(BaseModel):
    intent: str
    steps: list[ExecutionStep] = Field(default_factory=list)
    route_reason: str
    context: dict[str, Any] = Field(default_factory=dict)
    final_response_strategy: Literal[
        "deterministic", "llm", "unsupported", "selection", "capabilities"
    ] = "deterministic"


class PlanValidationError(ValueError):
    pass
