import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import perf_counter
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agents.registry import agent_registry
from backend.app.context.engine import context_engine
from backend.app.context.models import ContextPackage
from backend.app.core.config import get_personality, get_settings
from backend.app.models.entities import (
    AgentRuntimeState,
    AuditLog,
    Conversation,
    ExecutionTrace,
    Message,
    PendingAction,
)
from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.orchestrator.models import ExecutionPlan, ExecutionStep, PlanValidationError
from backend.app.orchestrator.router import (
    duration_from_message,
    event_title_from_message,
    intent_router,
    normalized,
)
from backend.app.providers.llm import LLMMessage, llm_registry
from backend.app.skills.registry import skill_registry
from backend.app.tools.base import ToolContext, ToolResult
from backend.app.tools.registry import tool_registry

logger = logging.getLogger("3m.orchestrator")
PARIS = ZoneInfo("Europe/Paris")
POSITIVE_CONFIRMATIONS = re.compile(r"^(oui|vas-y|vas y|fais-le|fais le|confirme|d'accord|ok)\b")
NEGATIVE_CONFIRMATIONS = re.compile(r"^(non|annule|annuler|laisse tomber|ne fais rien|stop)\b")
ORDINALS = {
    "premier": 0,
    "premiere": 0,
    "première": 0,
    "deuxieme": 1,
    "deuxième": 1,
    "second": 1,
    "seconde": 1,
    "troisieme": 2,
    "troisième": 2,
}
ProgressSink = Callable[[str, dict], Awaitable[None]]


class Orchestrator:
    async def chat(
        self,
        request: ChatRequest,
        session: AsyncSession,
        on_progress: ProgressSink | None = None,
    ) -> ChatResponse:
        started = perf_counter()
        settings = get_settings()
        conversation = await self._get_conversation(session, request.conversation_id)
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        session.add(user_message)
        await session.flush()
        await self._emit(on_progress, "planning", label="3M analyse votre demande…")
        context = await context_engine.build(session, conversation, request.message)

        pending = await self._get_pending_action(session, conversation.id)
        confirmation = normalized(request.message.strip())
        if pending and POSITIVE_CONFIRMATIONS.match(confirmation):
            return await self._resolve_confirmation(
                session,
                conversation,
                user_message,
                pending,
                approved=True,
                started=started,
                on_progress=on_progress,
            )
        if pending and NEGATIVE_CONFIRMATIONS.match(confirmation):
            return await self._resolve_confirmation(
                session,
                conversation,
                user_message,
                pending,
                approved=False,
                started=started,
                on_progress=on_progress,
            )
        if pending and confirmation.startswith("mets "):
            payload = json.loads(pending.payload)
            payload["title"] = event_title_from_message(request.message)
            pending.payload = json.dumps(payload, ensure_ascii=False)
            response = (
                f"D’accord, je l’appellerai « {payload['title']} ». Je confirme la création ?"
            )
            await self._emit(
                on_progress,
                "waiting_confirmation",
                label="Une confirmation est nécessaire.",
            )
            return await self._save_response(
                session,
                conversation,
                response,
                provider="orchestrator",
                model="pending-action-v2",
                state="waiting_confirmation",
                confirmation_id=pending.id,
            )
        if pending and any(word in confirmation for word in ("heure", "minutes")):
            payload = json.loads(pending.payload)
            if "starts_at" in payload and "ends_at" in payload:
                starts_at = datetime.fromisoformat(payload["starts_at"])
                payload["ends_at"] = (
                    starts_at + timedelta(minutes=duration_from_message(request.message))
                ).isoformat()
                pending.payload = json.dumps(payload, ensure_ascii=False)
                await self._emit(
                    on_progress,
                    "waiting_confirmation",
                    label="La proposition a été mise à jour.",
                )
                return await self._save_response(
                    session,
                    conversation,
                    self._pending_update_response(payload),
                    provider="orchestrator",
                    model="context-v3",
                    state="waiting_confirmation",
                    confirmation_id=pending.id,
                )

        routing_started = perf_counter()
        follow_up_plan = await self._plan_slot_follow_up(session, context, request.message)
        selected_action = self._plan_selected_entity_action(context, request.message)
        plan = (
            follow_up_plan
            or selected_action
            or intent_router.plan(
                request.message,
                request.preferred_agent,
                context.temporal.resolved_date,
            )
        )

        if self._asks_capabilities(request.message):
            plan = ExecutionPlan(
                intent="capabilities_snapshot",
                route_reason="Réponse construite depuis les registres actifs.",
                final_response_strategy="capabilities",
            )
        routing_ms = max(1, int((perf_counter() - routing_started) * 1000))

        if plan.final_response_strategy == "selection":
            trace = await self._create_trace(
                session,
                conversation.id,
                user_message.id,
                plan,
                "success",
                [],
                started,
                context_build_ms=context.context_build_ms,
                routing_ms=routing_ms,
            )
            await self._emit(on_progress, "responding", label="Sélection mémorisée…")
            return await self._save_response(
                session,
                conversation,
                plan.context["response"],
                provider="orchestrator",
                model="context-v3",
                execution_id=trace.id,
            )

        if plan.final_response_strategy == "capabilities":
            trace = await self._create_trace(
                session,
                conversation.id,
                user_message.id,
                plan,
                "success",
                [],
                started,
                context_build_ms=context.context_build_ms,
                routing_ms=routing_ms,
            )
            return await self._save_response(
                session,
                conversation,
                self._capabilities_response(context),
                provider="orchestrator",
                model="registries-v3",
                execution_id=trace.id,
            )

        if plan.final_response_strategy == "llm" and request.provider != "demo":
            provider_id = request.provider or settings.default_llm_provider
            model = request.model or settings.default_llm_model
            try:
                semantic_plan = await intent_router.semantic_plan(
                    request.message, llm_registry.get(provider_id), model
                )
                if semantic_plan:
                    plan = semantic_plan
            except Exception as exc:
                logger.info("[3M] semantic_router=fallback reason=%s", type(exc).__name__)
            routing_ms = max(1, int((perf_counter() - routing_started) * 1000))

        if plan.final_response_strategy == "unsupported":
            await self._emit(on_progress, "error", label="Cette capacité n’est pas disponible.")
            response = self._unsupported_response(plan)
            trace = await self._create_trace(
                session,
                conversation.id,
                user_message.id,
                plan,
                "unsupported",
                [],
                started,
                context_build_ms=context.context_build_ms,
                routing_ms=routing_ms,
            )
            return await self._save_response(
                session,
                conversation,
                response,
                provider="orchestrator",
                model="routing-v2",
                execution_id=trace.id,
                state="error",
            )

        if plan.final_response_strategy == "llm":
            await self._emit(on_progress, "responding", label="3M prépare sa réponse…")
            return await self._general_chat(
                request,
                session,
                conversation,
                user_message,
                plan,
                started,
                context,
                routing_ms,
            )

        try:
            self.validate_plan(plan, settings.max_execution_steps)
        except PlanValidationError as exc:
            trace = await self._create_trace(
                session,
                conversation.id,
                user_message.id,
                plan,
                "rejected",
                [],
                started,
                error=str(exc),
                context_build_ms=context.context_build_ms,
                routing_ms=routing_ms,
            )
            response = self._validation_error_response(str(exc))
            return await self._save_response(
                session,
                conversation,
                response,
                provider="orchestrator",
                model="policy-v2",
                execution_id=trace.id,
                state="error",
            )

        await self._emit(
            on_progress,
            "calling_agent",
            label=" · ".join(
                agent_registry.get_agent(step.agent_id).descriptor.name for step in plan.steps
            ),
            agents=sorted({step.agent_id for step in plan.steps}),
        )

        results: list[ToolResult] = []
        confirmation_id: str | None = None
        execution_status = "success"
        for step in plan.steps:
            if any(
                result.status != "success"
                for result in results
                if result.tool_name
                in {item.tool_name for item in plan.steps if item.id in step.depends_on}
            ):
                step.status = "error"
                results.append(
                    ToolResult(
                        tool_name=step.tool_name,
                        status="error",
                        error="Dépendance précédente en échec",
                    )
                )
                execution_status = "partial_failure"
                break
            tool = tool_registry.get(step.tool_name)
            if tool is None:
                execution_status = "rejected"
                results.append(
                    ToolResult(tool_name=step.tool_name, status="error", error="Outil inconnu")
                )
                break
            if tool.requires_confirmation:
                pending_action = await self._store_pending_action(
                    session, conversation.id, step.agent_id, step.tool_name, step.arguments
                )
                confirmation_id = pending_action.id
                step.status = "waiting_confirmation"
                execution_status = "waiting_confirmation"
                await self._emit(
                    on_progress,
                    "waiting_confirmation",
                    label="Une confirmation est nécessaire avant cette action.",
                    agent_id=step.agent_id,
                    tool_name=step.tool_name,
                )
                break
            result = await self._execute_step(
                session, conversation.id, step, on_progress=on_progress
            )
            results.append(result)
            if result.status != "success":
                execution_status = "partial_failure" if len(results) > 1 else "error"
                break

        trace = await self._create_trace(
            session,
            conversation.id,
            user_message.id,
            plan,
            execution_status,
            results,
            started,
            context_build_ms=context.context_build_ms,
            routing_ms=routing_ms,
            agent_execution_ms=max(1, sum(result.duration_ms for result in results)),
        )
        await context_engine.record_execution(session, conversation, trace, results)
        response = self._render_response(plan, results, confirmation_id)
        if execution_status != "waiting_confirmation":
            await self._emit(on_progress, "responding", label="3M restitue le résultat…")
        return await self._save_response(
            session,
            conversation,
            response,
            provider="orchestrator",
            model="tools-v2",
            execution_id=trace.id,
            state=execution_status,
            agents_used=sorted({step.agent_id for step in plan.steps}),
            tools_used=[result.tool_name for result in results],
            confirmation_id=confirmation_id,
        )

    def validate_plan(self, plan: ExecutionPlan, max_steps: int | None = None) -> None:
        limit = max_steps or get_settings().max_execution_steps
        if len(plan.steps) > limit:
            raise PlanValidationError(f"Plan refusé : maximum {limit} étapes")
        seen: set[str] = set()
        for step in plan.steps:
            if step.id in seen:
                raise PlanValidationError(f"Étape dupliquée : {step.id}")
            if any(dependency not in seen for dependency in step.depends_on):
                raise PlanValidationError(f"Dépendance invalide pour {step.id}")
            seen.add(step.id)
            agent = agent_registry.get_agent(step.agent_id)
            if not agent:
                raise PlanValidationError(f"Agent inconnu : {step.agent_id}")
            if not agent.descriptor.enabled:
                raise PlanValidationError(f"{agent.descriptor.name} est désactivé")
            skill = skill_registry.get(step.agent_id)
            if not skill or not skill.enabled:
                raise PlanValidationError(f"La compétence {step.agent_id} est désactivée")
            tool = tool_registry.get(step.tool_name)
            if not tool:
                raise PlanValidationError(f"Outil non enregistré : {step.tool_name}")
            if not tool.enabled:
                raise PlanValidationError(f"Outil désactivé : {step.tool_name}")
            if tool.agent_id != step.agent_id or step.tool_name not in agent.descriptor.tools:
                raise PlanValidationError(
                    f"L'outil {step.tool_name} n'est pas autorisé pour {step.agent_id}"
                )
            if tool.permission not in agent.descriptor.permissions:
                raise PlanValidationError(f"Permission absente : {tool.permission}")
            step.permission = tool.permission
            step.requires_confirmation = tool.requires_confirmation

    async def _execute_step(
        self,
        session: AsyncSession,
        conversation_id: str,
        step: ExecutionStep,
        on_progress: ProgressSink | None = None,
    ) -> ToolResult:
        settings = get_settings()
        agent = agent_registry.get_agent(step.agent_id)
        tool = tool_registry.get(step.tool_name)
        if not agent or not tool:
            return ToolResult(tool_name=step.tool_name, status="error", error="Route invalide")
        step.status = "running"
        await self._emit(
            on_progress,
            "executing_tool",
            label=f"{agent.descriptor.name} exécute {step.tool_name}…",
            agent_id=step.agent_id,
            tool_name=step.tool_name,
        )
        try:
            result = await asyncio.wait_for(
                agent.execute(
                    tool,
                    step.arguments,
                    ToolContext(session=session, conversation_id=conversation_id),
                ),
                timeout=settings.tool_timeout_seconds,
            )
        except TimeoutError:
            result = ToolResult(
                tool_name=step.tool_name, status="error", error="Délai d'exécution dépassé"
            )
        step.status = "success" if result.status == "success" else "error"
        if result.status == "success":
            agent_registry.mark_used(step.agent_id)
            state = await session.get(AgentRuntimeState, step.agent_id)
            if not state:
                state = AgentRuntimeState(agent_id=step.agent_id, enabled=True)
                session.add(state)
            state.last_used_at = datetime.now(UTC)
        session.add(
            AuditLog(
                action=f"tool.{step.tool_name}",
                target=conversation_id,
                outcome=result.status,
                detail=json.dumps(
                    {"duration_ms": result.duration_ms, "error": result.error},
                    ensure_ascii=False,
                ),
            )
        )
        return result

    async def _general_chat(
        self,
        request: ChatRequest,
        session: AsyncSession,
        conversation: Conversation,
        user_message: Message,
        plan: ExecutionPlan,
        started: float,
        context: ContextPackage,
        routing_ms: int,
    ) -> ChatResponse:
        settings = get_settings()
        personality = get_personality()
        provider_id = request.provider or settings.default_llm_provider
        model = request.model or settings.default_llm_model
        history_items = context.recent_messages
        capabilities = ", ".join(
            capability for values in context.capabilities.agents.values() for capability in values
        )
        system = (
            f"Tu es {personality.name}. Langue principale : {personality.language}. "
            f"{personality.response_style}\n{personality.system_instructions}\n"
            f"Capacités réellement disponibles : {capabilities or 'aucune'}. "
            "N'affirme jamais avoir utilisé une capacité absente. Les outils sont exécutés par "
            "Python, jamais par toi."
            f"\nRésumé fiable : {context.conversation_summary or 'aucun'}"
            f"\nSujet actif : {context.active_topic or 'aucun'}"
            f"\nContexte temporel : {context.temporal.model_dump_json()}"
        )
        llm_started = perf_counter()
        response_text = await llm_registry.get(provider_id).complete(
            [LLMMessage(role=item.role, content=item.content) for item in history_items],
            model,
            system,
        )
        llm_ms = max(1, int((perf_counter() - llm_started) * 1000))
        trace = await self._create_trace(
            session,
            conversation.id,
            user_message.id,
            plan,
            "success",
            [],
            started,
            context_build_ms=context.context_build_ms,
            routing_ms=routing_ms,
            llm_ms=llm_ms,
        )
        return await self._save_response(
            session,
            conversation,
            response_text,
            provider=provider_id,
            model=model,
            execution_id=trace.id,
            state="responding",
        )

    async def _resolve_confirmation(
        self,
        session: AsyncSession,
        conversation: Conversation,
        user_message: Message,
        pending: PendingAction,
        approved: bool,
        started: float,
        on_progress: ProgressSink | None = None,
    ) -> ChatResponse:
        if not approved:
            pending.status = "rejected"
            pending.consumed_at = datetime.now(UTC)
            plan = ExecutionPlan(
                intent="reject_confirmation",
                route_reason="Refus conversationnel associé à l'action persistée.",
            )
            trace = await self._create_trace(
                session, conversation.id, user_message.id, plan, "rejected", [], started
            )
            return await self._save_response(
                session,
                conversation,
                "D’accord, action annulée. Rien n’a été modifié.",
                provider="orchestrator",
                model="confirmation-v2",
                execution_id=trace.id,
                state="responding",
            )

        step = ExecutionStep(
            id="confirmed_step",
            agent_id=pending.agent_id or "",
            tool_name=pending.tool_name or pending.action,
            arguments=json.loads(pending.payload),
        )
        plan = ExecutionPlan(
            intent="confirm_action",
            route_reason="Confirmation associée à l'action persistée, sans reconstruction LLM.",
            steps=[step],
        )
        try:
            self.validate_plan(plan)
            await self._emit(
                on_progress,
                "calling_agent",
                label=f"{agent_registry.get_agent(step.agent_id).descriptor.name} est appelé…",
                agents=[step.agent_id],
            )
            result = await self._execute_step(
                session, conversation.id, step, on_progress=on_progress
            )
        except PlanValidationError as exc:
            result = ToolResult(tool_name=step.tool_name, status="error", error=str(exc))
        pending.consumed_at = datetime.now(UTC)
        pending.status = "approved" if result.status == "success" else "failed"
        trace = await self._create_trace(
            session,
            conversation.id,
            user_message.id,
            plan,
            result.status,
            [result],
            started,
            error=result.error,
        )
        response = self._confirmed_response(step.tool_name, result)
        await self._emit(on_progress, "responding", label="3M confirme le résultat…")
        return await self._save_response(
            session,
            conversation,
            response,
            provider="orchestrator",
            model="confirmation-v2",
            execution_id=trace.id,
            state="responding" if result.status == "success" else "error",
            agents_used=[step.agent_id],
            tools_used=[step.tool_name],
        )

    async def _plan_slot_follow_up(
        self, session: AsyncSession, context: ContextPackage, message: str
    ) -> ExecutionPlan | None:
        text = normalized(message)
        index = next((value for word, value in ORDINALS.items() if word in text), None)
        if index is None:
            return None
        slots = sorted(
            (
                item
                for item in context.referenced_entities
                if item.type == "calendar_slot" and item.status in {"active", "selected"}
            ),
            key=lambda item: item.position if item.position is not None else 999,
        )
        if index >= len(slots):
            return None
        selected = slots[index]
        await context_engine.select_entity(session, context.conversation_id, selected)
        slot = selected.data
        if "prefere" in text:
            starts_at = datetime.fromisoformat(slot["starts_at"]).astimezone(PARIS)
            ends_at = datetime.fromisoformat(slot["ends_at"]).astimezone(PARIS)
            return ExecutionPlan(
                intent="select_free_slot",
                route_reason="Référence structurée mémorisée dans le contexte de conversation.",
                context={
                    "response": (
                        f"J’ai retenu le créneau de {self._hour(starts_at)} à "
                        f"{self._hour(ends_at)}. Que souhaitez-vous y placer ?"
                    )
                },
                final_response_strategy="selection",
            )
        title = slot.get("event_title") or "Créneau personnel"
        return ExecutionPlan(
            intent="select_free_slot",
            route_reason=f"Référence conversationnelle résolue vers le créneau {index + 1}.",
            steps=[
                ExecutionStep(
                    id="step_1",
                    agent_id="calendar",
                    tool_name="calendar.create_event",
                    arguments={
                        "title": title,
                        "starts_at": slot["starts_at"],
                        "ends_at": slot["ends_at"],
                    },
                )
            ],
        )

    def _plan_selected_entity_action(
        self, context: ContextPackage, message: str
    ) -> ExecutionPlan | None:
        text = normalized(message)
        if not any(word in text for word in ("dessus", "mets", "place", "ajoute")):
            return None
        selected = next(
            (
                item
                for item in context.referenced_entities
                if item.type == "calendar_slot" and item.status == "selected"
            ),
            None,
        )
        if not selected:
            return None
        return ExecutionPlan(
            intent="create_event_from_context",
            route_reason="Créneau sélectionné restauré depuis le ContextEngine.",
            steps=[
                ExecutionStep(
                    id="step_1",
                    agent_id="calendar",
                    tool_name="calendar.create_event",
                    arguments={
                        "title": event_title_from_message(message),
                        "starts_at": selected.data["starts_at"],
                        "ends_at": selected.data["ends_at"],
                    },
                )
            ],
        )

    async def _store_pending_action(
        self,
        session: AsyncSession,
        conversation_id: str,
        agent_id: str,
        tool_name: str,
        arguments: dict,
    ) -> PendingAction:
        settings = get_settings()
        pending = PendingAction(
            action=tool_name,
            resource_id=conversation_id,
            conversation_id=conversation_id,
            agent_id=agent_id,
            tool_name=tool_name,
            payload=json.dumps(arguments, ensure_ascii=False),
            status="pending",
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.confirmation_ttl_minutes),
        )
        session.add(pending)
        await session.flush()
        return pending

    async def _get_pending_action(
        self, session: AsyncSession, conversation_id: str
    ) -> PendingAction | None:
        result = await session.execute(
            select(PendingAction)
            .where(
                PendingAction.conversation_id == conversation_id,
                PendingAction.status == "pending",
                PendingAction.consumed_at.is_(None),
            )
            .order_by(PendingAction.created_at.desc())
            .limit(1)
        )
        pending = result.scalar_one_or_none()
        if pending and pending.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            pending.status = "expired"
            return None
        return pending

    async def _create_trace(
        self,
        session: AsyncSession,
        conversation_id: str,
        message_id: str,
        plan: ExecutionPlan,
        status: str,
        results: list[ToolResult],
        started: float,
        error: str | None = None,
        context_build_ms: int = 0,
        routing_ms: int = 0,
        agent_execution_ms: int = 0,
        llm_ms: int = 0,
    ) -> ExecutionTrace:
        agents = sorted({step.agent_id for step in plan.steps if step.agent_id})
        tools = [step.tool_name for step in plan.steps if step.tool_name]
        trace = ExecutionTrace(
            conversation_id=conversation_id,
            message_id=message_id,
            intent=plan.intent,
            status=status,
            route_reason=plan.route_reason,
            plan_json=plan.model_dump_json(),
            results_json=json.dumps(
                [result.model_dump(mode="json") for result in results], ensure_ascii=False
            ),
            agents_used=json.dumps(agents),
            tools_used=json.dumps(tools),
            error=error,
            duration_ms=int((perf_counter() - started) * 1000),
            context_build_ms=context_build_ms,
            routing_ms=routing_ms,
            agent_execution_ms=agent_execution_ms,
            llm_ms=llm_ms,
        )
        session.add(trace)
        await session.flush()
        logger.info(
            "[3M] intent=%s route=%s tools=%s duration=%sms status=%s",
            plan.intent,
            ",".join(agents) or "llm",
            ",".join(tools) or "none",
            trace.duration_ms,
            status,
        )
        return trace

    async def _save_response(
        self,
        session: AsyncSession,
        conversation: Conversation,
        response: str,
        *,
        provider: str,
        model: str,
        execution_id: str | None = None,
        state: str = "responding",
        agents_used: list[str] | None = None,
        tools_used: list[str] | None = None,
        confirmation_id: str | None = None,
    ) -> ChatResponse:
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response,
            provider=provider,
            model=model,
            agent_used=(agents_used or [None])[0],
            tools_used=json.dumps(tools_used or []),
            execution_id=execution_id,
        )
        session.add(assistant_message)
        conversation.last_message_at = datetime.now(UTC)
        if conversation.title == "Nouvelle conversation":
            latest_user = await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation.id, Message.role == "user")
                .order_by(Message.created_at.asc())
                .limit(1)
            )
            if first := latest_user.scalar_one_or_none():
                conversation.title = self._conversation_title(first.content)
        await session.commit()
        await session.refresh(assistant_message)
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            response=response,
            provider=provider,
            model=model,
            execution_id=execution_id,
            state=state,
            agents_used=agents_used or [],
            tools_used=tools_used or [],
            confirmation_id=confirmation_id,
        )

    @staticmethod
    def _conversation_title(message: str) -> str:
        text = normalized(message)
        if "sport" in text:
            return "Organisation d’une séance de sport"
        if any(word in text for word in ("agenda", "calendrier", "creneau", "rendez-vous")):
            return "Organisation du calendrier"
        if any(word in text for word in ("tache", "todo", "a faire")):
            return "Gestion des tâches"
        compact = " ".join(message.strip().split())
        return compact[:57] + ("…" if len(compact) > 57 else "")

    async def _get_conversation(
        self, session: AsyncSession, conversation_id: str | None
    ) -> Conversation:
        if conversation_id:
            conversation = await session.get(Conversation, conversation_id)
            if conversation:
                return conversation
        conversation = Conversation()
        session.add(conversation)
        await session.flush()
        return conversation

    def _render_response(
        self, plan: ExecutionPlan, results: list[ToolResult], confirmation_id: str | None
    ) -> str:
        if confirmation_id:
            arguments = plan.steps[-1].arguments
            starts_at = datetime.fromisoformat(arguments["starts_at"]).astimezone(PARIS)
            ends_at = datetime.fromisoformat(arguments["ends_at"]).astimezone(PARIS)
            return (
                f"Je peux créer « {arguments['title']} » le {starts_at.strftime('%d/%m')} "
                f"de {self._hour(starts_at)} à {self._hour(ends_at)}. Je le fais ?"
            )
        if not results or any(result.status != "success" for result in results):
            error = next((result.error for result in results if result.error), "Erreur inconnue")
            return f"Je n’ai pas pu terminer cette action : {error}."
        if plan.intent in {"find_free_slots", "calendar_and_task"}:
            slots = results[0].output["items"]
            if not slots:
                slot_text = "Je n’ai trouvé aucun créneau compatible."
            else:
                labels = [
                    f"{index + 1}. "
                    f"{self._hour(datetime.fromisoformat(item['starts_at']).astimezone(PARIS))}–"
                    f"{self._hour(datetime.fromisoformat(item['ends_at']).astimezone(PARIS))}"
                    for index, item in enumerate(slots[:3])
                ]
                slot_text = "J’ai trouvé ces possibilités : " + ", ".join(labels) + "."
            if plan.intent == "calendar_and_task" and len(results) > 1:
                task_title = results[1].output["item"]["title"]
                return f"{slot_text} J’ai aussi créé la tâche « {task_title} »."
            return f"{slot_text} Dites-moi par exemple « la deuxième » pour la préparer."
        if plan.intent == "list_events":
            events = results[0].output["items"]
            if not events:
                return "Vous n’avez aucun événement prévu à cette date."
            labels = [
                f"{self._hour(datetime.fromisoformat(item['starts_at']).astimezone(PARIS))}"
                f" : {item['title']}"
                for item in events
            ]
            return "Voici vos événements : " + "; ".join(labels) + "."
        if plan.intent == "create_task":
            return f"La tâche « {results[0].output['item']['title']} » a été ajoutée."
        if plan.intent == "list_tasks":
            tasks = results[0].output["items"]
            return (
                "Vos tâches : " + "; ".join(item["title"] for item in tasks) + "."
                if tasks
                else "Vous n’avez aucune tâche."
            )
        return "Action terminée."

    def _confirmed_response(self, tool_name: str, result: ToolResult) -> str:
        if result.status != "success":
            return f"L’action confirmée a échoué : {result.error}."
        item = result.output.get("item", {})
        if tool_name == "calendar.create_event":
            starts_at = datetime.fromisoformat(item["starts_at"]).astimezone(PARIS)
            ends_at = datetime.fromisoformat(item["ends_at"]).astimezone(PARIS)
            return (
                f"C’est fait. « {item['title']} » a été ajouté de "
                f"{self._hour(starts_at)} à {self._hour(ends_at)}."
            )
        if tool_name.endswith("delete") or tool_name.endswith("delete_event"):
            return "C’est fait, l’élément a été supprimé."
        return "C’est fait, l’action confirmée a été exécutée."

    def _unsupported_response(self, plan: ExecutionPlan) -> str:
        if plan.intent == "unsupported_capability":
            return "Je n’ai pas encore de module permettant d’accéder à vos emails."
        if plan.intent == "missing_time_range":
            return "J’ai besoin d’un horaire précis, par exemple « demain de 10h à 12h »."
        if plan.intent == "missing_date":
            return "À quelle date souhaitez-vous planifier cette séance ?"
        return plan.route_reason

    def _validation_error_response(self, error: str) -> str:
        if "désactivé" in error:
            return f"Je ne peux pas effectuer cette action : {error}."
        return f"Le plan a été refusé par la politique de sécurité : {error}."

    def _capabilities_response(self, context: ContextPackage) -> str:
        if not context.capabilities.agents:
            return "Aucun agent n’est actuellement actif."
        labels = [
            f"{agent_id} : {', '.join(capabilities)}"
            for agent_id, capabilities in context.capabilities.agents.items()
        ]
        return "Mes capacités actives sont : " + "; ".join(labels) + "."

    @staticmethod
    def _asks_capabilities(message: str) -> bool:
        text = normalized(message)
        return any(
            phrase in text
            for phrase in (
                "que sais-tu faire",
                "que sais tu faire",
                "qu'est-ce que tu sais faire",
                "qu'est ce que tu sais faire",
                "tes capacites",
                "peux-tu faire",
            )
        )

    def _pending_update_response(self, payload: dict) -> str:
        starts_at = datetime.fromisoformat(payload["starts_at"]).astimezone(PARIS)
        ends_at = datetime.fromisoformat(payload["ends_at"]).astimezone(PARIS)
        return (
            f"D’accord, je propose maintenant « {payload['title']} » de "
            f"{self._hour(starts_at)} à {self._hour(ends_at)}. Je le fais ?"
        )

    @staticmethod
    def _hour(value: datetime) -> str:
        return value.strftime("%Hh%M").replace("h00", "h")

    @staticmethod
    async def _emit(sink: ProgressSink | None, state: str, **payload) -> None:
        if sink:
            await sink(state, {"state": state, **payload})


orchestrator = Orchestrator()
