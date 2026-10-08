from fastapi import APIRouter

from backend.app.api.routes import calendar, chat, memory, system, tasks, voice

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(chat.router)
api_router.include_router(tasks.router)
api_router.include_router(calendar.router)
api_router.include_router(memory.router)
api_router.include_router(voice.router)
