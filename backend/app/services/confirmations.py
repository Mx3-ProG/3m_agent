from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import PendingAction


async def create_confirmation(
    session: AsyncSession, action: str, resource_id: str, payload: str = "{}"
) -> PendingAction:
    confirmation = PendingAction(
        action=action,
        resource_id=resource_id,
        payload=payload,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
    )
    session.add(confirmation)
    await session.commit()
    await session.refresh(confirmation)
    return confirmation


async def consume_confirmation(
    session: AsyncSession, confirmation_id: str, action: str, resource_id: str
) -> bool:
    confirmation = await session.get(PendingAction, confirmation_id)
    now = datetime.now(UTC)
    if (
        not confirmation
        or confirmation.action != action
        or confirmation.resource_id != resource_id
        or confirmation.consumed_at is not None
        or confirmation.expires_at.replace(tzinfo=UTC) < now
    ):
        return False
    confirmation.consumed_at = now
    await session.flush()
    return True
