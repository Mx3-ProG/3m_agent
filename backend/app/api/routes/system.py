import os
from dataclasses import asdict
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends

from backend.app.agents.registry import agent_registry
from backend.app.providers.llm import llm_registry
from backend.app.security.auth import require_api_token
from backend.app.skills.registry import skill_registry

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "3M API", "time": datetime.now(UTC).isoformat()}


@router.get("/system", dependencies=[Depends(require_api_token)])
async def system_status() -> dict:
    skills = skill_registry.discover()
    ollama_reachable = False
    try:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
        async with httpx.AsyncClient(timeout=0.5) as client:
            ollama_reachable = (await client.get(f"{base_url}/api/tags")).is_success
    except httpx.HTTPError:
        pass
    return {
        "status": "operational",
        "agents": [asdict(descriptor) for descriptor in agent_registry.list_agents()],
        "skills": [skill.model_dump(mode="json") for skill in skills],
        "providers": {
            "available": llm_registry.list(),
            "configured": {
                "openai": bool(os.getenv("OPENAI_API_KEY")),
                "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
                "ollama": ollama_reachable,
                "demo": True,
            },
        },
    }
