import pytest


@pytest.mark.asyncio
async def test_health_is_public(client):
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_private_endpoint_requires_token(client):
    response = await client.get("/api/v1/tasks")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_vertical_chat_flow_persists_history(client, auth):
    response = await client.post(
        "/api/v1/conversations/chat",
        headers=auth,
        json={"message": "Bonjour 3M", "provider": "demo", "model": "3m-demo"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "Mode démonstration" in body["response"]

    history = await client.get(
        f"/api/v1/conversations/{body['conversation_id']}/messages", headers=auth
    )
    assert history.status_code == 200
    assert [item["role"] for item in history.json()] == ["user", "assistant"]


@pytest.mark.asyncio
async def test_task_lifecycle_and_confirmed_delete(client, auth):
    created = await client.post(
        "/api/v1/tasks", headers=auth, json={"title": "Tester 3M", "priority": "high"}
    )
    assert created.status_code == 201
    task = created.json()

    updated = await client.patch(
        f"/api/v1/tasks/{task['id']}", headers=auth, json={"status": "done"}
    )
    assert updated.json()["status"] == "done"

    request = await client.post(f"/api/v1/tasks/{task['id']}/delete-request", headers=auth)
    confirmation_id = request.json()["confirmation_id"]
    deleted = await client.post(
        f"/api/v1/tasks/{task['id']}/delete-confirm",
        headers=auth,
        json={"confirmation_id": confirmation_id},
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_memory_rejects_sensitive_item(client, auth):
    response = await client.post(
        "/api/v1/memory",
        headers=auth,
        json={"content": "secret", "sensitive": True},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_demo_calendar_is_seeded(client, auth):
    response = await client.get("/api/v1/calendar/events", headers=auth)
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 2
    assert events[0]["starts_at"].endswith("+00:00")


@pytest.mark.asyncio
async def test_system_lists_agents_and_skills(client, auth):
    response = await client.get("/api/v1/system", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["agents"]} == {"tasks", "calendar"}
    assert {item["id"] for item in body["skills"]} == {"tasks", "calendar"}


@pytest.mark.asyncio
async def test_calendar_provider_status_is_explicit(client, auth):
    response = await client.get("/api/v1/calendar/provider/status", headers=auth)
    assert response.status_code == 200
    assert response.json() == {
        "provider": "demo",
        "available": True,
        "authorization": "not_required",
    }
