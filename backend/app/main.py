from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.api.router import api_router
from backend.app.api.routes.calendar import seed_demo_calendar
from backend.app.api.routes.orchestration import restore_runtime_states
from backend.app.core.config import get_settings
from backend.app.core.database import SessionLocal, initialize_database


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await initialize_database()
    async with SessionLocal() as session:
        await seed_demo_calendar(session)
        await restore_runtime_states(session)
    yield


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-3M-Token"],
)
app.include_router(api_router)


@app.exception_handler(Exception)
async def unhandled_exception(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500, content={"detail": "Erreur interne 3M", "type": type(exc).__name__}
    )
