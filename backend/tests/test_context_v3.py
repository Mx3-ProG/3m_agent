import json
from datetime import datetime

import pytest
from sqlalchemy import select

from backend.app.context.temporal import date_resolver
from backend.app.core.database import SessionLocal
from backend.app.models.entities import CalendarEvent, Conversation, Message, PendingAction


async def chat(client, auth, message, conversation_id=None):
    payload = {"message": message, "provider": "demo", "model": "3m-demo"}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return await client.post("/api/v1/conversations/chat", headers=auth, json=payload)


@pytest.mark.asyncio
async def test_conversation_persists_and_can_be_reopened(client, auth):
    created = await client.post("/api/v1/conversations", headers=auth, json={})
    conversation_id = created.json()["id"]
    await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        headers=auth,
        json={"message": "Bonjour", "provider": "demo"},
    )
    async with SessionLocal() as restarted_session:
        stored = await restarted_session.get(Conversation, conversation_id)
        assert stored is not None
        messages = list(
            (
                await restarted_session.execute(
                    select(Message).where(Message.conversation_id == conversation_id)
                )
            ).scalars()
        )
        assert [item.role for item in messages] == ["user", "assistant"]

    reopened = await client.get(f"/api/v1/conversations/{conversation_id}/messages", headers=auth)
    assert [item["content"] for item in reopened.json()][0] == "Bonjour"


@pytest.mark.asyncio
async def test_resume_selected_slot_after_reopen_and_adjust_duration(client, auth):
    first = await chat(client, auth, "Trouve-moi deux heures demain.")
    conversation_id = first.json()["conversation_id"]
    selected = await chat(client, auth, "Je préfère le deuxième.", conversation_id)
    assert "J’ai retenu" in selected.json()["response"]
    assert selected.json()["confirmation_id"] is None

    debug = await client.get(f"/api/v1/debug/conversations/{conversation_id}/context", headers=auth)
    entities = debug.json()["referenced_entities"]
    chosen = next(item for item in entities if item["status"] == "selected")

    proposed = await chat(client, auth, "Mets du sport dessus.", conversation_id)
    assert proposed.json()["state"] == "waiting_confirmation"
    confirmation_id = proposed.json()["confirmation_id"]
    async with SessionLocal() as session:
        pending = await session.get(PendingAction, confirmation_id)
        payload = json.loads(pending.payload)
        assert payload["starts_at"] == chosen["data"]["starts_at"]
        assert payload["title"] == "Sport"

    adjusted = await chat(client, auth, "Finalement mets seulement une heure.", conversation_id)
    assert "maintenant" in adjusted.json()["response"]
    confirmed = await chat(client, auth, "Vas-y.", conversation_id)
    assert "C’est fait" in confirmed.json()["response"]
    async with SessionLocal() as session:
        event = (
            (
                await session.execute(
                    select(CalendarEvent)
                    .where(CalendarEvent.title == "Sport")
                    .order_by(CalendarEvent.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        assert event is not None
        assert (event.ends_at - event.starts_at).total_seconds() == 3600


@pytest.mark.asyncio
async def test_pending_action_can_be_rejected(client, auth):
    proposed = await chat(client, auth, "Réserve demain 16h-17h pour le sport.")
    rejected = await chat(client, auth, "Non, laisse tomber.", proposed.json()["conversation_id"])
    assert "Rien n’a été modifié" in rejected.json()["response"]
    async with SessionLocal() as session:
        pending = await session.get(PendingAction, proposed.json()["confirmation_id"])
        assert pending.status == "rejected"


@pytest.mark.asyncio
async def test_context_isolation_between_conversations(client, auth):
    first = await chat(client, auth, "Trouve-moi deux heures demain pour le sport.")
    await chat(client, auth, "Je préfère le deuxième.", first.json()["conversation_id"])
    other = await chat(client, auth, "Liste mes tâches.")
    response = await chat(client, auth, "Mets du sport dessus.", other.json()["conversation_id"])
    assert response.json()["confirmation_id"] is None


@pytest.mark.asyncio
async def test_capabilities_snapshot_excludes_disabled_agents(client, auth):
    await client.post("/api/v1/agents/calendar/disable", headers=auth)
    response = await chat(client, auth, "Qu'est-ce que tu sais faire ?")
    text = response.json()["response"]
    assert "tasks" in text
    assert "calendar" not in text


@pytest.mark.asyncio
async def test_context_budget_uses_summary_and_recent_messages(client, auth):
    async with SessionLocal() as session:
        conversation = Conversation(title="Longue conversation")
        session.add(conversation)
        await session.flush()
        session.add_all(
            [
                Message(
                    conversation_id=conversation.id,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"Message vérifié numéro {index}",
                )
                for index in range(26)
            ]
        )
        await session.commit()
        conversation_id = conversation.id
    debug = await client.get(f"/api/v1/debug/conversations/{conversation_id}/context", headers=auth)
    context = debug.json()
    assert context["conversation_summary"].startswith("Contexte récent vérifié")
    assert len(context["recent_messages"]) <= 20
    assert context["characters_used"] <= 16_000


def test_temporal_resolution_is_centralized():
    now = datetime.fromisoformat("2026-10-08T10:00:00+02:00")
    tomorrow = date_resolver.resolve("demain après-midi", now=now)
    assert tomorrow.resolved_date == "2026-10-09"
    assert tomorrow.period == "afternoon"
    monday = date_resolver.resolve("lundi prochain", now=now)
    assert monday.resolved_date == "2026-10-12"
