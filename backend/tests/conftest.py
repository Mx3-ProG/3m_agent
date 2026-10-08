import os
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio

os.environ["THREEM_DATABASE_URL"] = "sqlite+aiosqlite:///./data/test-3m.sqlite3"
os.environ["THREEM_API_TOKEN"] = "test-token"
os.environ["THREEM_DEFAULT_LLM_PROVIDER"] = "demo"
os.environ["THREEM_DEFAULT_LLM_MODEL"] = "3m-demo"

from backend.app.api.routes.calendar import seed_demo_calendar  # noqa: E402
from backend.app.core.database import Base, SessionLocal, engine  # noqa: E402
from backend.app.main import app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def database() -> AsyncIterator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with SessionLocal() as session:
        await seed_demo_calendar(session)
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-3M-Token": "test-token"}
