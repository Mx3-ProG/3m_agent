from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.providers.calendar import calendar_provider
from backend.app.providers.tasks import task_provider
from backend.app.tools.base import PermissionLevel, Tool, ToolContext


class EventsInput(BaseModel):
    date: date


class FreeSlotsInput(EventsInput):
    duration_minutes: int = Field(ge=15, le=480)


class CreateEventInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    starts_at: datetime
    ends_at: datetime
    location: str = Field(default="", max_length=240)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_range(self) -> "CreateEventInput":
        if self.ends_at <= self.starts_at:
            raise ValueError("La fin doit être postérieure au début")
        return self


class UpdateEventInput(BaseModel):
    event_id: str
    title: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    location: str | None = None
    notes: str | None = None


class ResourceInput(BaseModel):
    resource_id: str


class ItemsOutput(BaseModel):
    items: list[dict]
    count: int


class ItemOutput(BaseModel):
    item: dict


class EmptyInput(BaseModel):
    pass


class CreateTaskInput(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=4000)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    due_at: datetime | None = None


class UpdateTaskInput(BaseModel):
    task_id: str
    title: str | None = None
    description: str | None = None
    priority: Literal["low", "medium", "high", "urgent"] | None = None
    status: Literal["open", "in_progress", "done"] | None = None
    due_at: datetime | None = None


class CalendarListEventsTool(Tool):
    name = "calendar.list_events"
    description = "Liste les événements du calendrier pour une date précise."
    agent_id = skill_id = "calendar"
    permission = "calendar.read"
    permission_level = PermissionLevel.SAFE_READ
    input_model = EventsInput
    output_model = ItemsOutput

    async def execute(self, arguments: EventsInput, context: ToolContext) -> dict:
        items = await calendar_provider.list_events(context.session, arguments.date)
        return {"items": items, "count": len(items)}


class CalendarFindFreeSlotsTool(Tool):
    name = "calendar.find_free_slots"
    description = "Trouve des créneaux libres d'une durée donnée entre 9h et 18h."
    agent_id = skill_id = "calendar"
    permission = "calendar.read"
    permission_level = PermissionLevel.SAFE_READ
    input_model = FreeSlotsInput
    output_model = ItemsOutput

    async def execute(self, arguments: FreeSlotsInput, context: ToolContext) -> dict:
        items = await calendar_provider.find_free_slots(
            context.session, arguments.date, arguments.duration_minutes
        )
        return {"items": items, "count": len(items)}


class CalendarCreateEventTool(Tool):
    name = "calendar.create_event"
    description = "Crée un événement dans le calendrier de démonstration."
    agent_id = skill_id = "calendar"
    permission = "calendar.write"
    permission_level = PermissionLevel.SENSITIVE
    requires_confirmation = True
    input_model = CreateEventInput
    output_model = ItemOutput

    async def execute(self, arguments: CreateEventInput, context: ToolContext) -> dict:
        item = await calendar_provider.create_event(context.session, arguments.model_dump())
        return {"item": item}


class CalendarUpdateEventTool(Tool):
    name = "calendar.update_event"
    description = "Modifie un événement existant."
    agent_id = skill_id = "calendar"
    permission = "calendar.write"
    permission_level = PermissionLevel.SENSITIVE
    requires_confirmation = True
    input_model = UpdateEventInput
    output_model = ItemOutput

    async def execute(self, arguments: UpdateEventInput, context: ToolContext) -> dict:
        values = arguments.model_dump(exclude={"event_id"}, exclude_none=True)
        item = await calendar_provider.update_event(context.session, arguments.event_id, values)
        return {"item": item}


class CalendarDeleteEventTool(Tool):
    name = "calendar.delete_event"
    description = "Supprime un événement existant."
    agent_id = skill_id = "calendar"
    permission = "calendar.write"
    permission_level = PermissionLevel.DANGEROUS
    requires_confirmation = True
    input_model = ResourceInput
    output_model = ItemOutput

    async def execute(self, arguments: ResourceInput, context: ToolContext) -> dict:
        item = await calendar_provider.delete_event(context.session, arguments.resource_id)
        return {"item": item}


class TasksListTool(Tool):
    name = "tasks.list"
    description = "Liste les tâches personnelles."
    agent_id = skill_id = "tasks"
    permission = "tasks.read"
    permission_level = PermissionLevel.SAFE_READ
    input_model = EmptyInput
    output_model = ItemsOutput

    async def execute(self, arguments: EmptyInput, context: ToolContext) -> dict:
        items = await task_provider.list_tasks(context.session)
        return {"items": items, "count": len(items)}


class TasksCreateTool(Tool):
    name = "tasks.create"
    description = "Crée une tâche personnelle."
    agent_id = skill_id = "tasks"
    permission = "tasks.write"
    permission_level = PermissionLevel.WRITE
    input_model = CreateTaskInput
    output_model = ItemOutput

    async def execute(self, arguments: CreateTaskInput, context: ToolContext) -> dict:
        item = await task_provider.create_task(context.session, arguments.model_dump())
        return {"item": item}


class TasksUpdateTool(Tool):
    name = "tasks.update"
    description = "Modifie une tâche existante."
    agent_id = skill_id = "tasks"
    permission = "tasks.write"
    permission_level = PermissionLevel.WRITE
    input_model = UpdateTaskInput
    output_model = ItemOutput

    async def execute(self, arguments: UpdateTaskInput, context: ToolContext) -> dict:
        values = arguments.model_dump(exclude={"task_id"}, exclude_none=True)
        item = await task_provider.update_task(context.session, arguments.task_id, values)
        return {"item": item}


class TasksCompleteTool(Tool):
    name = "tasks.complete"
    description = "Marque une tâche comme terminée."
    agent_id = skill_id = "tasks"
    permission = "tasks.write"
    permission_level = PermissionLevel.WRITE
    input_model = ResourceInput
    output_model = ItemOutput

    async def execute(self, arguments: ResourceInput, context: ToolContext) -> dict:
        item = await task_provider.complete_task(context.session, arguments.resource_id)
        return {"item": item}


class TasksDeleteTool(Tool):
    name = "tasks.delete"
    description = "Supprime une tâche personnelle."
    agent_id = skill_id = "tasks"
    permission = "tasks.write"
    permission_level = PermissionLevel.DANGEROUS
    requires_confirmation = True
    input_model = ResourceInput
    output_model = ItemOutput

    async def execute(self, arguments: ResourceInput, context: ToolContext) -> dict:
        item = await task_provider.delete_task(context.session, arguments.resource_id)
        return {"item": item}


ALL_TOOLS = (
    CalendarListEventsTool(),
    CalendarFindFreeSlotsTool(),
    CalendarCreateEventTool(),
    CalendarUpdateEventTool(),
    CalendarDeleteEventTool(),
    TasksListTool(),
    TasksCreateTool(),
    TasksUpdateTool(),
    TasksCompleteTool(),
    TasksDeleteTool(),
)
