import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.registry import agent_registry
from backend.app.core.database import get_session
from backend.app.models.entities import (
    AgentRuntimeState,
    ExecutionTrace,
    PendingAction,
    SkillRuntimeState,
)
from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.orchestrator.service import orchestrator
from backend.app.providers.calendar import calendar_provider
from backend.app.security.auth import require_api_token
from backend.app.skills.registry import skill_registry
from backend.app.tools.registry import tool_registry

router = APIRouter(tags=["orchestration"], dependencies=[Depends(require_api_token)])


async def agent_payload(agent_id: str) -> dict:
    agent = agent_registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent introuvable")
    payload = asdict(agent.descriptor)
    payload["health"] = await agent.health_check()
    if agent_id == "calendar":
        provider = await calendar_provider.status()
        payload["health"]["provider"] = provider
        if not provider["available"]:
            payload["health"].update(
                healthy=False,
                status="degraded",
                error=provider.get("error", "Provider calendrier indisponible"),
            )
    payload["tool_count"] = len(agent.descriptor.tools)
    return payload


@router.get("/agents")
async def list_agents() -> list[dict]:
    return [await agent_payload(item.id) for item in agent_registry.list_agents()]


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    return await agent_payload(agent_id)


async def set_agent_enabled(agent_id: str, enabled: bool, session: AsyncSession) -> dict:
    if not agent_registry.get_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent introuvable")
    descriptor = agent_registry.set_enabled(agent_id, enabled)
    state = await session.get(AgentRuntimeState, agent_id)
    if not state:
        state = AgentRuntimeState(agent_id=agent_id, enabled=enabled)
        session.add(state)
    else:
        state.enabled = enabled
    await session.commit()
    return asdict(descriptor)


@router.post("/agents/{agent_id}/enable")
async def enable_agent(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await set_agent_enabled(agent_id, True, session)


@router.post("/agents/{agent_id}/disable")
async def disable_agent(agent_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await set_agent_enabled(agent_id, False, session)


@router.get("/skills")
async def list_skills() -> list[dict]:
    return [skill.model_dump(mode="json") for skill in skill_registry.list()]


async def set_skill_enabled(skill_id: str, enabled: bool, session: AsyncSession) -> dict:
    skill = skill_registry.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Compétence introuvable")
    skill_registry.set_enabled(skill_id, enabled)
    state = await session.get(SkillRuntimeState, skill_id)
    if not state:
        state = SkillRuntimeState(skill_id=skill_id, enabled=enabled)
        session.add(state)
    else:
        state.enabled = enabled
    for agent_id in skill.agents:
        if agent_registry.get_agent(agent_id):
            agent_registry.set_enabled(agent_id, enabled)
            agent_state = await session.get(AgentRuntimeState, agent_id)
            if not agent_state:
                session.add(AgentRuntimeState(agent_id=agent_id, enabled=enabled))
            else:
                agent_state.enabled = enabled
    await session.commit()
    return skill.model_dump(mode="json")


@router.post("/skills/{skill_id}/enable")
async def enable_skill(skill_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await set_skill_enabled(skill_id, True, session)


@router.post("/skills/{skill_id}/disable")
async def disable_skill(skill_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await set_skill_enabled(skill_id, False, session)


@router.get("/tools")
async def list_tools() -> list[dict]:
    return [definition.model_dump(mode="json") for definition in tool_registry.list()]


def trace_payload(trace: ExecutionTrace) -> dict:
    return {
        "id": trace.id,
        "conversation_id": trace.conversation_id,
        "message_id": trace.message_id,
        "intent": trace.intent,
        "status": trace.status,
        "route_reason": trace.route_reason,
        "plan": json.loads(trace.plan_json),
        "results": json.loads(trace.results_json),
        "agents_used": json.loads(trace.agents_used),
        "tools_used": json.loads(trace.tools_used),
        "error": trace.error,
        "duration_ms": trace.duration_ms,
        "context_build_ms": trace.context_build_ms,
        "routing_ms": trace.routing_ms,
        "agent_execution_ms": trace.agent_execution_ms,
        "llm_ms": trace.llm_ms,
        "created_at": trace.created_at,
    }


@router.get("/executions")
async def list_executions(session: AsyncSession = Depends(get_session)) -> list[dict]:
    result = await session.execute(
        select(ExecutionTrace).order_by(ExecutionTrace.created_at.desc()).limit(100)
    )
    return [trace_payload(trace) for trace in result.scalars()]


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    trace = await session.get(ExecutionTrace, execution_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Exécution introuvable")
    return trace_payload(trace)


async def resolve_confirmation(
    confirmation_id: str, approved: bool, session: AsyncSession
) -> ChatResponse:
    pending = await session.get(PendingAction, confirmation_id)
    if not pending or pending.status != "pending" or not pending.conversation_id:
        raise HTTPException(status_code=409, detail="Confirmation invalide ou déjà traitée")
    return await orchestrator.chat(
        ChatRequest(
            message="Oui" if approved else "Non",
            conversation_id=pending.conversation_id,
        ),
        session,
    )


@router.post("/confirmations/{confirmation_id}/approve", response_model=ChatResponse)
async def approve_confirmation(
    confirmation_id: str, session: AsyncSession = Depends(get_session)
) -> ChatResponse:
    return await resolve_confirmation(confirmation_id, True, session)


@router.post("/confirmations/{confirmation_id}/reject", response_model=ChatResponse)
async def reject_confirmation(
    confirmation_id: str, session: AsyncSession = Depends(get_session)
) -> ChatResponse:
    return await resolve_confirmation(confirmation_id, False, session)


async def restore_runtime_states(session: AsyncSession) -> None:
    skill_registry.discover()
    skill_states = await session.execute(select(SkillRuntimeState))
    for state in skill_states.scalars():
        if skill_registry.get(state.skill_id):
            skill_registry.set_enabled(state.skill_id, state.enabled)
    agent_states = await session.execute(select(AgentRuntimeState))
    for state in agent_states.scalars():
        if agent_registry.get_agent(state.agent_id):
            descriptor = agent_registry.set_enabled(state.agent_id, state.enabled)
            descriptor.last_used_at = state.last_used_at
