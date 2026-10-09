import re
import unicodedata
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from backend.app.context.temporal import date_resolver
from backend.app.orchestrator.models import ExecutionPlan, ExecutionStep
from backend.app.providers.llm import LLMMessage, LLMProvider
from backend.app.tools.registry import tool_registry

PARIS = ZoneInfo("Europe/Paris")


class SemanticRouteProposal(BaseModel):
    intent: str
    agent_id: str | None = None
    tool_name: str | None = None
    reason: str = ""


def normalized(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def target_date_from_message(message: str) -> date:
    temporal = date_resolver.resolve(message)
    return date.fromisoformat(temporal.resolved_date or temporal.today)


def duration_from_message(message: str) -> int:
    text = normalized(message)
    word_hours = {"une": 1, "deux": 2, "trois": 3, "quatre": 4}
    for word, hours in word_hours.items():
        if re.search(rf"\b{word}\s+heures?\b", text):
            return hours * 60
    if match := re.search(r"\b(\d+)\s*(?:h|heures?)\b", text):
        return int(match.group(1)) * 60
    if match := re.search(r"\b(\d+)\s*(?:min|minutes?)\b", text):
        return int(match.group(1))
    return 60


def event_title_from_message(message: str) -> str:
    text = normalized(message)
    if "sport" in text:
        return "Sport"
    match = re.search(r"pour\s+(?:le\s+|la\s+|l['’])?(.+?)(?:[.?!]|$)", message, re.I)
    if match:
        return match.group(1).strip().capitalize()
    return "Créneau personnel"


def task_title_from_message(message: str) -> str:
    match = re.search(
        r"(?:ajoute|cr[eé]e)\s+(.+?)(?:\s+(?:à|a)\s+(?:mes\s+)?t[aâ]ches?|[.?!]|$)",
        message,
        re.I,
    )
    if match:
        return match.group(1).strip()
    text = normalized(message)
    if "preparation" in text:
        return "Préparation"
    return "Nouvelle tâche"


def explicit_agent_from_message(message: str) -> str | None:
    text = normalized(message)
    if re.search(r"utilise\s+(?:le\s+)?calendaragent", text):
        return "calendar"
    if re.search(r"utilise\s+(?:le\s+)?taskagent", text):
        return "tasks"
    return None


def parse_time_range(message: str, target_date) -> tuple[datetime, datetime] | None:
    text = normalized(message)
    match = re.search(r"\b(\d{1,2})(?:h(?:(\d{2}))?)?\s*(?:-|a|à)\s*(\d{1,2})h?(\d{2})?\b", text)
    if not match:
        return None
    start_hour, start_minute, end_hour, end_minute = match.groups()
    starts_at = datetime.combine(target_date, time(int(start_hour), int(start_minute or 0)), PARIS)
    ends_at = datetime.combine(target_date, time(int(end_hour), int(end_minute or 0)), PARIS)
    return starts_at, ends_at


class IntentRouter:
    """Deterministic semantic router backed by declared agent capabilities.

    The LLM is deliberately not trusted to name tools. New intents are mapped to
    registered capabilities here, then validated again by the orchestrator.
    """

    def plan(
        self,
        message: str,
        preferred_agent: str | None = None,
        contextual_date: str | None = None,
    ) -> ExecutionPlan:
        text = normalized(message)
        explicit = preferred_agent or explicit_agent_from_message(message)
        temporal = date_resolver.resolve(message)
        effective_date = temporal.resolved_date or contextual_date
        target_date = date.fromisoformat(effective_date or temporal.today)
        wants_calendar = any(
            phrase in text
            for phrase in (
                "agenda",
                "calendrier",
                "rendez-vous",
                "rendez vous",
                "disponibil",
                "libre",
                "creneau",
                "trouve",
                "reserve",
                "evenement",
            )
        )
        if re.search(r"qu(?:e|')est.ce que .*faire", text) and target_date_from_message(message):
            wants_calendar = True
        wants_tasks = any(phrase in text for phrase in ("tache", "todo", "a faire"))

        if explicit and explicit not in {"calendar", "tasks"}:
            return ExecutionPlan(
                intent="invalid_preferred_agent",
                route_reason=f"Agent explicite inconnu : {explicit}",
                final_response_strategy="unsupported",
            )
        if explicit == "calendar" and wants_tasks and not wants_calendar:
            return ExecutionPlan(
                intent="agent_capability_mismatch",
                route_reason="CalendarAgent ne possède pas la capacité tâches.",
                final_response_strategy="unsupported",
            )
        if explicit == "tasks" and wants_calendar and not wants_tasks:
            return ExecutionPlan(
                intent="agent_capability_mismatch",
                route_reason="TaskAgent ne possède pas la capacité calendrier.",
                final_response_strategy="unsupported",
            )

        if wants_calendar and wants_tasks:
            return ExecutionPlan(
                intent="calendar_and_task",
                route_reason="Deux domaines déclarés détectés : calendrier puis tâches.",
                steps=[
                    ExecutionStep(
                        id="step_1",
                        agent_id="calendar",
                        tool_name="calendar.find_free_slots",
                        arguments={
                            "date": target_date.isoformat(),
                            "duration_minutes": duration_from_message(message),
                        },
                    ),
                    ExecutionStep(
                        id="step_2",
                        agent_id="tasks",
                        tool_name="tasks.create",
                        arguments={"title": task_title_from_message(message)},
                        depends_on=["step_1"],
                    ),
                ],
            )

        if wants_calendar or explicit == "calendar":
            if any(phrase in text for phrase in ("libre", "disponibil", "creneau", "trouve")):
                return ExecutionPlan(
                    intent="find_free_slots",
                    route_reason="Capacité find_free_slots du CalendarAgent sélectionnée.",
                    context={"event_title": event_title_from_message(message)},
                    steps=[
                        ExecutionStep(
                            id="step_1",
                            agent_id="calendar",
                            tool_name="calendar.find_free_slots",
                            arguments={
                                "date": target_date.isoformat(),
                                "duration_minutes": duration_from_message(message),
                            },
                        )
                    ],
                )
            if any(phrase in text for phrase in ("reserve", "cree", "ajoute", "planifie")):
                if not effective_date:
                    return ExecutionPlan(
                        intent="missing_date",
                        route_reason=(
                            "Création calendrier demandée sans date explicite ou contextuelle."
                        ),
                        final_response_strategy="unsupported",
                    )
                time_range = parse_time_range(message, target_date)
                if not time_range:
                    return ExecutionPlan(
                        intent="missing_time_range",
                        route_reason="Création calendrier demandée sans horaire exploitable.",
                        final_response_strategy="unsupported",
                    )
                starts_at, ends_at = time_range
                return ExecutionPlan(
                    intent="create_event",
                    route_reason="Capacité create_event du CalendarAgent sélectionnée.",
                    steps=[
                        ExecutionStep(
                            id="step_1",
                            agent_id="calendar",
                            tool_name="calendar.create_event",
                            arguments={
                                "title": event_title_from_message(message),
                                "starts_at": starts_at.isoformat(),
                                "ends_at": ends_at.isoformat(),
                            },
                        )
                    ],
                )
            return ExecutionPlan(
                intent="list_events",
                route_reason="Capacité list_events du CalendarAgent sélectionnée.",
                steps=[
                    ExecutionStep(
                        id="step_1",
                        agent_id="calendar",
                        tool_name="calendar.list_events",
                        arguments={"date": target_date.isoformat()},
                    )
                ],
            )

        if wants_tasks or explicit == "tasks":
            if any(phrase in text for phrase in ("ajoute", "cree", "note")):
                return ExecutionPlan(
                    intent="create_task",
                    route_reason="Capacité create_task du TaskAgent sélectionnée.",
                    steps=[
                        ExecutionStep(
                            id="step_1",
                            agent_id="tasks",
                            tool_name="tasks.create",
                            arguments={"title": task_title_from_message(message)},
                        )
                    ],
                )
            return ExecutionPlan(
                intent="list_tasks",
                route_reason="Capacité list_tasks du TaskAgent sélectionnée.",
                steps=[
                    ExecutionStep(
                        id="step_1", agent_id="tasks", tool_name="tasks.list", arguments={}
                    )
                ],
            )

        if any(phrase in text for phrase in ("email", "gmail", "boite mail", "boîte mail")):
            return ExecutionPlan(
                intent="unsupported_capability",
                route_reason="Aucun agent enregistré ne déclare une capacité email.",
                final_response_strategy="unsupported",
            )
        return ExecutionPlan(
            intent="general_conversation",
            route_reason="Aucune capacité outil requise ; conversation LLM normale.",
            final_response_strategy="llm",
        )

    async def semantic_plan(
        self, message: str, provider: LLMProvider, model: str
    ) -> ExecutionPlan | None:
        """Ask the LLM only for a route; code owns arguments and validation."""
        catalog = [
            {
                "agent_id": definition.agent_id,
                "tool_name": definition.name,
                "description": definition.description,
            }
            for definition in tool_registry.list()
            if definition.enabled
        ]
        system = (
            "Tu es le classifieur de routage de 3M. Choisis une capacité uniquement si la demande "
            "l'exige réellement. Réponds en JSON strict avec intent, agent_id, tool_name, reason. "
            "Pour une conversation ordinaire, utilise intent=general_conversation et des valeurs "
            "nulles. Pour une capacité absente, utilise intent=unsupported_capability. Catalogue: "
            + str(catalog)
        )
        raw = await provider.complete([LLMMessage(role="user", content=message)], model, system)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        proposal = SemanticRouteProposal.model_validate_json(match.group(0))
        if proposal.intent == "general_conversation":
            return None
        if proposal.intent == "unsupported_capability":
            return ExecutionPlan(
                intent=proposal.intent,
                route_reason=proposal.reason or "Capacité absente selon le catalogue actif.",
                final_response_strategy="unsupported",
            )
        if not proposal.agent_id or not proposal.tool_name:
            return None
        arguments = self._arguments_for_tool(proposal.tool_name, message)
        if arguments is None:
            return ExecutionPlan(
                intent="missing_tool_arguments",
                route_reason="La route sémantique nécessite des précisions avant exécution.",
                final_response_strategy="unsupported",
            )
        intent_by_tool = {
            "calendar.list_events": "list_events",
            "calendar.find_free_slots": "find_free_slots",
            "calendar.create_event": "create_event",
            "tasks.list": "list_tasks",
            "tasks.create": "create_task",
        }
        return ExecutionPlan(
            intent=intent_by_tool.get(proposal.tool_name, proposal.intent),
            route_reason=(
                "Route sémantique proposée par le LLM puis soumise aux registres et politiques : "
                + (proposal.reason or proposal.tool_name)
            ),
            context={"event_title": event_title_from_message(message)},
            steps=[
                ExecutionStep(
                    id="step_1",
                    agent_id=proposal.agent_id,
                    tool_name=proposal.tool_name,
                    arguments=arguments,
                )
            ],
        )

    def _arguments_for_tool(self, tool_name: str, message: str) -> dict | None:
        target_date = target_date_from_message(message)
        if tool_name == "calendar.list_events":
            return {"date": target_date.isoformat()}
        if tool_name == "calendar.find_free_slots":
            return {
                "date": target_date.isoformat(),
                "duration_minutes": duration_from_message(message),
            }
        if tool_name == "calendar.create_event":
            time_range = parse_time_range(message, target_date)
            if not time_range:
                return None
            starts_at, ends_at = time_range
            return {
                "title": event_title_from_message(message),
                "starts_at": starts_at.isoformat(),
                "ends_at": ends_at.isoformat(),
            }
        if tool_name == "tasks.list":
            return {}
        if tool_name == "tasks.create":
            return {"title": task_title_from_message(message)}
        return {}


intent_router = IntentRouter()
