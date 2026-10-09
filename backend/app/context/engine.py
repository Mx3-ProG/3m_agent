import json
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.registry import agent_registry
from backend.app.context.models import (
    ContextEntityData,
    ContextMessage,
    ContextPackage,
    SystemCapabilitiesSnapshot,
)
from backend.app.context.temporal import date_resolver
from backend.app.core.config import get_settings
from backend.app.memory.provider import memory_provider
from backend.app.models.entities import (
    ContextEntity,
    Conversation,
    ExecutionTrace,
    Message,
    PendingAction,
)
from backend.app.tools.base import ToolResult
from backend.app.tools.registry import tool_registry


class ContextEngine:
    async def build(
        self, session: AsyncSession, conversation: Conversation, current_message: str
    ) -> ContextPackage:
        started = perf_counter()
        settings = get_settings()
        await self._refresh_summary_if_needed(session, conversation)

        message_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(settings.context_recent_messages)
        )
        raw_messages = list(reversed(list(message_result.scalars())))
        messages: list[ContextMessage] = []
        used = len(conversation.summary)
        for item in reversed(raw_messages):
            size = len(item.content)
            if used + size > settings.context_budget_characters:
                continue
            messages.append(
                ContextMessage(role=item.role, content=item.content, created_at=item.created_at)
            )
            used += size
        messages.reverse()

        entity_result = await session.execute(
            select(ContextEntity)
            .where(ContextEntity.conversation_id == conversation.id)
            .order_by(ContextEntity.updated_at.desc())
            .limit(40)
        )
        entities = [self._entity_payload(item) for item in entity_result.scalars()]
        pending_result = await session.execute(
            select(PendingAction)
            .where(
                PendingAction.conversation_id == conversation.id,
                PendingAction.status == "pending",
                PendingAction.expires_at > datetime.now(UTC),
            )
            .order_by(PendingAction.created_at.desc())
        )
        pending = [
            {
                "id": item.id,
                "action": item.action,
                "arguments": json.loads(item.payload),
                "expires_at": item.expires_at.isoformat(),
            }
            for item in pending_result.scalars()
        ]
        trace_result = await session.execute(
            select(ExecutionTrace)
            .where(ExecutionTrace.conversation_id == conversation.id)
            .order_by(ExecutionTrace.created_at.desc())
            .limit(8)
        )
        traces = list(trace_result.scalars())
        preferences = await memory_provider.explicit_preferences(session)
        temporal = date_resolver.resolve(current_message)
        try:
            working_memory = json.loads(conversation.metadata_json or "{}")
        except json.JSONDecodeError:
            working_memory = {}
        if temporal.resolved_date:
            working_memory["working_date"] = temporal.resolved_date
            conversation.metadata_json = json.dumps(working_memory, ensure_ascii=False)
        elif working_date := working_memory.get("working_date"):
            temporal.resolved_date = working_date

        package = ContextPackage(
            conversation_id=conversation.id,
            current_message=current_message,
            recent_messages=messages,
            conversation_summary=conversation.summary,
            active_topic=conversation.active_topic,
            referenced_entities=entities,
            pending_actions=pending,
            recent_agent_results=[
                {
                    "execution_id": item.id,
                    "intent": item.intent,
                    "agents": json.loads(item.agents_used),
                    "status": item.status,
                }
                for item in traces
            ],
            recent_tool_results=[
                {
                    "execution_id": item.id,
                    "tools": json.loads(item.tools_used),
                    "results": json.loads(item.results_json),
                }
                for item in traces
                if item.results_json != "[]"
            ],
            capabilities=SystemCapabilitiesSnapshot(
                agents=agent_registry.get_capabilities(enabled_only=True),
                tools=[item.name for item in tool_registry.list() if item.enabled],
            ),
            user_preferences=preferences,
            temporal=temporal,
            characters_used=used,
        )
        package.context_build_ms = int((perf_counter() - started) * 1000)
        return package

    async def record_execution(
        self,
        session: AsyncSession,
        conversation: Conversation,
        trace: ExecutionTrace,
        results: list[ToolResult],
    ) -> None:
        conversation.active_topic = trace.intent
        for result in results:
            items = result.output.get("items", [])
            if result.tool_name == "calendar.find_free_slots":
                plan_context = json.loads(trace.plan_json).get("context", {})
                await session.execute(
                    update(ContextEntity)
                    .where(
                        ContextEntity.conversation_id == conversation.id,
                        ContextEntity.entity_type == "calendar_slot",
                        ContextEntity.status.in_(["active", "selected"]),
                    )
                    .values(status="superseded")
                )
                for index, item in enumerate(items):
                    entity_data = {**item, "event_title": plan_context.get("event_title", "")}
                    session.add(
                        ContextEntity(
                            conversation_id=conversation.id,
                            entity_type="calendar_slot",
                            label=f"Créneau {index + 1}",
                            position=index,
                            data_json=json.dumps(entity_data, ensure_ascii=False),
                            source_execution_id=trace.id,
                        )
                    )
            elif result.tool_name == "calendar.list_events":
                for index, item in enumerate(items):
                    session.add(
                        ContextEntity(
                            conversation_id=conversation.id,
                            entity_type="calendar_event",
                            label=item.get("title", f"Événement {index + 1}"),
                            position=index,
                            data_json=json.dumps(item, ensure_ascii=False),
                            source_execution_id=trace.id,
                        )
                    )

    async def select_entity(
        self, session: AsyncSession, conversation_id: str, entity: ContextEntityData
    ) -> None:
        await session.execute(
            update(ContextEntity)
            .where(
                ContextEntity.conversation_id == conversation_id,
                ContextEntity.entity_type == entity.type,
                ContextEntity.status == "selected",
            )
            .values(status="active")
        )
        stored = await session.get(ContextEntity, entity.id)
        if stored:
            stored.status = "selected"

    async def _refresh_summary_if_needed(
        self, session: AsyncSession, conversation: Conversation
    ) -> None:
        settings = get_settings()
        count = await session.scalar(
            select(func.count(Message.id)).where(Message.conversation_id == conversation.id)
        )
        if not count or count < settings.conversation_summary_threshold:
            return
        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.desc())
            .limit(12)
        )
        items = list(reversed(list(result.scalars())))
        conversation.summary = (
            "Contexte récent vérifié : "
            + " ".join(f"{item.role}: {item.content[:240]}" for item in items)[:3000]
        )

    @staticmethod
    def _entity_payload(entity: ContextEntity) -> ContextEntityData:
        return ContextEntityData(
            id=entity.id,
            type=entity.entity_type,
            label=entity.label,
            position=entity.position,
            data=json.loads(entity.data_json),
            source_execution_id=entity.source_execution_id,
            status=entity.status,
        )


context_engine = ContextEngine()
