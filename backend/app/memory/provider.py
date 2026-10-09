from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import MemoryItem


class MemoryProvider(Protocol):
    async def explicit_preferences(self, session: AsyncSession, limit: int = 20) -> list[str]: ...


class SQLiteMemoryProvider:
    async def explicit_preferences(self, session: AsyncSession, limit: int = 20) -> list[str]:
        result = await session.execute(
            select(MemoryItem.content)
            .where(MemoryItem.sensitive.is_(False), MemoryItem.category == "preference")
            .order_by(MemoryItem.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())


memory_provider: MemoryProvider = SQLiteMemoryProvider()
