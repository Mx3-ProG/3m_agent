from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.models.entities import AuditLog, CalendarEvent
from backend.app.models.schemas import ConfirmationRequest, EventCreate, EventRead
from backend.app.providers.calendar import calendar_provider
from backend.app.security.auth import require_api_token
from backend.app.services.confirmations import consume_confirmation, create_confirmation

router = APIRouter(prefix="/calendar", tags=["calendar"], dependencies=[Depends(require_api_token)])


@router.get("/provider/status")
async def provider_status() -> dict:
    return await calendar_provider.status()


@router.get("/events", response_model=list[EventRead])
async def list_events(session: AsyncSession = Depends(get_session)) -> list[CalendarEvent]:
    result = await session.execute(select(CalendarEvent).order_by(CalendarEvent.starts_at.asc()))
    return list(result.scalars())


@router.post("/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate, session: AsyncSession = Depends(get_session)
) -> CalendarEvent:
    event = CalendarEvent(**payload.model_dump(), source="demo")
    session.add_all([event, AuditLog(action="calendar.create", target=event.id, outcome="success")])
    await session.commit()
    await session.refresh(event)
    return event


@router.post("/events/{event_id}/delete-request")
async def request_delete(event_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    if not await session.get(CalendarEvent, event_id):
        raise HTTPException(status_code=404, detail="Événement introuvable")
    confirmation = await create_confirmation(session, "calendar.delete", event_id)
    return {"confirmation_id": confirmation.id, "expires_at": confirmation.expires_at}


@router.post("/events/{event_id}/delete-confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_delete(
    event_id: str,
    payload: ConfirmationRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    event = await session.get(CalendarEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Événement introuvable")
    if not await consume_confirmation(
        session, payload.confirmation_id, "calendar.delete", event_id
    ):
        raise HTTPException(status_code=409, detail="Confirmation invalide ou expirée")
    await session.delete(event)
    session.add(AuditLog(action="calendar.delete", target=event_id, outcome="success"))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def seed_demo_calendar(session: AsyncSession) -> None:
    if (await session.execute(select(CalendarEvent).limit(1))).scalar_one_or_none():
        return
    tomorrow = datetime.now(UTC).replace(hour=9, minute=30, second=0, microsecond=0) + timedelta(
        days=1
    )
    session.add_all(
        [
            CalendarEvent(
                title="Revue de la journée",
                starts_at=tomorrow,
                ends_at=tomorrow + timedelta(minutes=30),
            ),
            CalendarEvent(
                title="Créneau projet 3M",
                starts_at=tomorrow + timedelta(hours=2),
                ends_at=tomorrow + timedelta(hours=4),
            ),
        ]
    )
    await session.commit()
