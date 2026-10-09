from fastapi import APIRouter

from backend.app.api.routes import (
    calendar,
    chat,
    context_debug,
    memory,
    orchestration,
    system,
    tasks,
    voice,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(chat.router)
api_router.include_router(tasks.router)
api_router.include_router(calendar.router)
api_router.include_router(memory.router)
api_router.include_router(voice.router)
api_router.include_router(orchestration.router)
api_router.include_router(context_debug.router)
