import json

import pytest
from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.models.entities import PendingAction, Task
from backend.app.orchestrator.models import ExecutionPlan, ExecutionStep, PlanValidationError
from backend.app.orchestrator.router import intent_router
from backend.app.orchestrator.service import orchestrator
from backend.app.providers.llm import LLMMessage, LLMProvider


class SemanticCalendarProvider(LLMProvider):
    id = "semantic-test"

    async def complete(self, messages: list[LLMMessage], model: str, system: str) -> str:
        return (
            '{"intent":"calendar_overview","agent_id":"calendar",'
            '"tool_name":"calendar.list_events","reason":"La journée concerne le calendrier"}'
        )


async def chat(client, auth, message, conversation_id=None, preferred_agent=None):
    body = {"message": message, "provider": "demo", "model": "3m-demo"}
    if conversation_id:
        body["conversation_id"] = conversation_id
    if preferred_agent:
        body["preferred_agent"] = preferred_agent
    return await client.post("/api/v1/conversations/chat", headers=auth, json=body)


@pytest.mark.asyncio
async def test_calendar_list_routes_to_real_tool_without_confirmation(client, auth):
    response = await chat(client, auth, "Liste mes événements demain.")
    assert response.status_code == 200
    body = response.json()
    assert body["agents_used"] == ["calendar"]
    assert body["tools_used"] == ["calendar.list_events"]
    assert body["confirmation_id"] is None
    assert "Revue de la journée" in body["response"]


@pytest.mark.asyncio
async def test_find_free_slots_returns_structured_tool_result(client, auth):
    response = await chat(client, auth, "Trouve-moi deux heures libres demain.")
    body = response.json()
    assert body["tools_used"] == ["calendar.find_free_slots"]
    assert "J’ai trouvé" in body["response"]
    execution = await client.get(f"/api/v1/executions/{body['execution_id']}", headers=auth)
    result = execution.json()["results"][0]
    assert result["status"] == "success"
    assert result["output"]["count"] >= 1
    assert result["output"]["items"][0]["duration_minutes"] == 120


@pytest.mark.asyncio
async def test_stream_exposes_real_orchestration_states(client, auth):
    response = await client.post(
        "/api/v1/conversations/chat/stream",
        headers=auth,
        json={"message": "Liste mes événements demain.", "provider": "demo"},
    )
    assert response.status_code == 200
    body = response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert body.index("event: planning") < body.index("event: calling_agent")
    assert body.index("event: calling_agent") < body.index("event: executing_tool")
    assert body.index("event: executing_tool") < body.index("event: result")
    assert '"tool_name": "calendar.list_events"' in body


@pytest.mark.asyncio
async def test_ambiguous_wording_can_use_structured_semantic_route():
    plan = await intent_router.semantic_plan(
        "Est-ce que ma journée de demain est chargée ?",
        SemanticCalendarProvider(),
        "test",
    )
    assert plan is not None
    assert plan.steps[0].agent_id == "calendar"
    assert plan.steps[0].tool_name == "calendar.list_events"
    orchestrator.validate_plan(plan)


@pytest.mark.asyncio
async def test_calendar_write_waits_for_conversational_confirmation(client, auth):
    before = (await client.get("/api/v1/calendar/events", headers=auth)).json()
    proposed = await chat(client, auth, "Réserve demain 10h-12h pour le sport.")
    body = proposed.json()
    assert body["state"] == "waiting_confirmation"
    assert body["confirmation_id"]
    after_proposal = (await client.get("/api/v1/calendar/events", headers=auth)).json()
    assert len(after_proposal) == len(before)

    approved = await chat(client, auth, "Oui", body["conversation_id"])
    assert approved.status_code == 200
    assert "C’est fait" in approved.json()["response"]
    after_approval = (await client.get("/api/v1/calendar/events", headers=auth)).json()
    assert len(after_approval) == len(before) + 1
    assert any(event["title"] == "Sport" for event in after_approval)


@pytest.mark.asyncio
async def test_slot_reference_then_yes_executes_exact_stored_action(client, auth):
    first = await chat(client, auth, "Trouve-moi deux heures demain pour faire du sport.")
    second = await chat(client, auth, "Prends la deuxième.", first.json()["conversation_id"])
    assert second.json()["state"] == "waiting_confirmation"
    async with SessionLocal() as session:
        pending = await session.get(PendingAction, second.json()["confirmation_id"])
        stored = json.loads(pending.payload)
        assert stored["title"] == "Sport"
    third = await chat(client, auth, "Oui.", first.json()["conversation_id"])
    assert "Sport" in third.json()["response"]


@pytest.mark.asyncio
async def test_task_agent_creates_task_without_sensitive_confirmation(client, auth):
    response = await chat(client, auth, "Ajoute acheter du café à mes tâches.")
    body = response.json()
    assert body["tools_used"] == ["tasks.create"]
    assert body["confirmation_id"] is None
    tasks = (await client.get("/api/v1/tasks", headers=auth)).json()
    assert any(task["title"] == "acheter du café" for task in tasks)


@pytest.mark.asyncio
async def test_disabled_calendar_agent_is_never_executed(client, auth):
    disabled = await client.post("/api/v1/agents/calendar/disable", headers=auth)
    assert disabled.status_code == 200
    response = await chat(client, auth, "Quels sont mes rendez-vous demain ?")
    body = response.json()
    assert body["tools_used"] == []
    assert "désactivé" in body["response"]
    assert body["state"] == "error"


@pytest.mark.asyncio
async def test_unknown_email_capability_does_not_hallucinate(client, auth):
    response = await chat(client, auth, "Lis mes emails.")
    body = response.json()
    assert body["tools_used"] == []
    assert "pas encore de module" in body["response"]
    execution = await client.get(f"/api/v1/executions/{body['execution_id']}", headers=auth)
    assert execution.json()["intent"] == "unsupported_capability"


@pytest.mark.asyncio
async def test_multi_agent_plan_executes_in_order(client, auth):
    response = await chat(
        client,
        auth,
        "Regarde mes disponibilités demain et ajoute une tâche de préparation.",
    )
    body = response.json()
    assert body["agents_used"] == ["calendar", "tasks"]
    assert body["tools_used"] == ["calendar.find_free_slots", "tasks.create"]
    async with SessionLocal() as session:
        tasks = list((await session.execute(select(Task))).scalars())
        assert tasks


def test_unknown_tool_is_rejected_before_execution():
    plan = ExecutionPlan(
        intent="malicious",
        route_reason="test",
        steps=[
            ExecutionStep(
                id="step_1",
                agent_id="calendar",
                tool_name="rm_everything",
                arguments={},
            )
        ],
    )
    with pytest.raises(PlanValidationError, match="Outil non enregistré"):
        orchestrator.validate_plan(plan)


def test_max_step_guard_stops_repeated_planning():
    plan = ExecutionPlan(
        intent="loop",
        route_reason="test",
        steps=[
            ExecutionStep(
                id=f"step_{index}",
                agent_id="tasks",
                tool_name="tasks.list",
            )
            for index in range(9)
        ],
    )
    with pytest.raises(PlanValidationError, match="maximum 8 étapes"):
        orchestrator.validate_plan(plan, max_steps=8)


@pytest.mark.asyncio
async def test_explicit_agent_route_and_health_endpoints(client, auth):
    response = await chat(client, auth, "Regarde demain.", preferred_agent="calendar")
    assert response.json()["agents_used"] == ["calendar"]
    agents = await client.get("/api/v1/agents", headers=auth)
    calendar = next(item for item in agents.json() if item["id"] == "calendar")
    assert calendar["health"]["healthy"] is True
    assert calendar["health"]["provider"]["provider"] == "demo"
    assert calendar["tool_count"] == 5
    tools = await client.get("/api/v1/tools", headers=auth)
    assert len(tools.json()) == 10
