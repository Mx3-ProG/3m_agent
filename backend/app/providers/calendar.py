import asyncio
import json
from abc import ABC, abstractmethod
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.models.entities import CalendarEvent

PARIS = ZoneInfo("Europe/Paris")


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def event_dict(event: CalendarEvent) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "starts_at": ensure_utc(event.starts_at).isoformat(),
        "ends_at": ensure_utc(event.ends_at).isoformat(),
        "location": event.location,
        "notes": event.notes,
        "source": event.source,
    }


class CalendarProvider(ABC):
    @abstractmethod
    async def status(self) -> dict: ...

    @abstractmethod
    async def list_events(self, session: AsyncSession, target_date: date) -> list[dict]: ...

    @abstractmethod
    async def find_free_slots(
        self, session: AsyncSession, target_date: date, duration_minutes: int
    ) -> list[dict]: ...

    @abstractmethod
    async def create_event(self, session: AsyncSession, values: dict) -> dict: ...

    @abstractmethod
    async def update_event(self, session: AsyncSession, event_id: str, values: dict) -> dict: ...

    @abstractmethod
    async def delete_event(self, session: AsyncSession, event_id: str) -> dict: ...


class DemoCalendarProvider(CalendarProvider):
    """Deterministic SQLite calendar. Replace this provider for EventKit later."""

    async def status(self) -> dict:
        return {"provider": "demo", "available": True, "authorization": "not_required"}

    async def list_events(self, session: AsyncSession, target_date: date) -> list[dict]:
        result = await session.execute(select(CalendarEvent).order_by(CalendarEvent.starts_at))
        events = []
        for event in result.scalars():
            local_start = ensure_utc(event.starts_at).astimezone(PARIS)
            if local_start.date() == target_date:
                events.append(event_dict(event))
        return events

    async def find_free_slots(
        self, session: AsyncSession, target_date: date, duration_minutes: int
    ) -> list[dict]:
        events = await self.list_events(session, target_date)
        return find_free_slots(events, target_date, duration_minutes)

    async def create_event(self, session: AsyncSession, values: dict) -> dict:
        event = CalendarEvent(**values, source="demo")
        session.add(event)
        await session.flush()
        return event_dict(event)

    async def update_event(self, session: AsyncSession, event_id: str, values: dict) -> dict:
        event = await session.get(CalendarEvent, event_id)
        if not event:
            raise ValueError("Événement introuvable")
        for key, value in values.items():
            if value is not None:
                setattr(event, key, value)
        await session.flush()
        return event_dict(event)

    async def delete_event(self, session: AsyncSession, event_id: str) -> dict:
        event = await session.get(CalendarEvent, event_id)
        if not event:
            raise ValueError("Événement introuvable")
        snapshot = event_dict(event)
        await session.delete(event)
        await session.flush()
        return snapshot


def find_free_slots(events: list[dict], target_date: date, duration_minutes: int) -> list[dict]:
    day_start = datetime.combine(target_date, time(9, 0), PARIS).astimezone(UTC)
    day_end = datetime.combine(target_date, time(18, 0), PARIS).astimezone(UTC)
    busy = sorted(
        (
            max(day_start, datetime.fromisoformat(item["starts_at"])),
            min(day_end, datetime.fromisoformat(item["ends_at"])),
        )
        for item in events
        if datetime.fromisoformat(item["ends_at"]) > day_start
        and datetime.fromisoformat(item["starts_at"]) < day_end
    )
    merged: list[tuple[datetime, datetime]] = []
    for starts_at, ends_at in busy:
        if merged and starts_at <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], ends_at))
        else:
            merged.append((starts_at, ends_at))

    free_ranges: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for starts_at, ends_at in merged:
        if starts_at > cursor:
            free_ranges.append((cursor, starts_at))
        cursor = max(cursor, ends_at)
    if cursor < day_end:
        free_ranges.append((cursor, day_end))

    duration = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=30)
    slots: list[dict] = []
    for range_start, range_end in free_ranges:
        candidate = range_start
        while candidate + duration <= range_end and len(slots) < 5:
            slots.append(
                {
                    "starts_at": candidate.isoformat(),
                    "ends_at": (candidate + duration).isoformat(),
                    "duration_minutes": duration_minutes,
                }
            )
            candidate += step
    return slots


class AppleCalendarProvider(CalendarProvider):
    """EventKit provider using a fixed, locally built macOS bridge executable."""

    def __init__(self, bridge_path: str, calendar_identifier: str = "") -> None:
        self.bridge_path = Path(bridge_path).expanduser().resolve()
        self.calendar_identifier = calendar_identifier

    async def _run(self, command: str, payload: dict | None = None) -> dict | list:
        if not self.bridge_path.is_file():
            raise RuntimeError(
                f"Pont Apple Calendar introuvable : {self.bridge_path}. "
                "Exécutez scripts/build-apple-calendar-bridge.sh."
            )
        arguments = [str(self.bridge_path), command]
        if payload is not None:
            arguments.append(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    default=lambda value: (
                        ensure_utc(value).isoformat() if isinstance(value, datetime) else str(value)
                    ),
                )
            )
        process = await asyncio.create_subprocess_exec(
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        if process.returncode != 0:
            detail = stderr.decode().strip() or "Erreur inconnue EventKit"
            raise RuntimeError(detail)
        return json.loads(stdout.decode())

    async def status(self) -> dict:
        try:
            result = await self._run("status")
            return {"provider": "apple", "available": True, **result}
        except (OSError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
            return {
                "provider": "apple",
                "available": False,
                "authorization": "unavailable",
                "error": str(exc),
            }

    async def list_events(self, session: AsyncSession, target_date: date) -> list[dict]:
        del session
        result = await self._run(
            "list",
            {"date": target_date.isoformat(), "calendar_identifier": self.calendar_identifier},
        )
        return list(result)

    async def find_free_slots(
        self, session: AsyncSession, target_date: date, duration_minutes: int
    ) -> list[dict]:
        events = await self.list_events(session, target_date)
        return find_free_slots(events, target_date, duration_minutes)

    async def create_event(self, session: AsyncSession, values: dict) -> dict:
        del session
        result = await self._run(
            "create", {**values, "calendar_identifier": self.calendar_identifier}
        )
        return dict(result)

    async def update_event(self, session: AsyncSession, event_id: str, values: dict) -> dict:
        del session
        result = await self._run("update", {"event_id": event_id, **values})
        return dict(result)

    async def delete_event(self, session: AsyncSession, event_id: str) -> dict:
        del session
        result = await self._run("delete", {"event_id": event_id})
        return dict(result)


settings = get_settings()
calendar_provider: CalendarProvider = (
    AppleCalendarProvider(
        settings.apple_calendar_bridge_path,
        settings.apple_calendar_identifier,
    )
    if settings.calendar_provider.casefold() == "apple"
    else DemoCalendarProvider()
)
