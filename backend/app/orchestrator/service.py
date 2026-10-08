from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.core.config import get_personality, get_settings
from backend.app.models.entities import Conversation, Message
from backend.app.models.schemas import ChatRequest, ChatResponse
from backend.app.providers.llm import LLMMessage, llm_registry


class Orchestrator:
    async def chat(self, request: ChatRequest, session: AsyncSession) -> ChatResponse:
        settings = get_settings()
        personality = get_personality()
        provider_id = request.provider or settings.default_llm_provider
        model = request.model or settings.default_llm_model

        conversation = await self._get_conversation(session, request.conversation_id)
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content=request.message,
        )
        session.add(user_message)
        await session.flush()

        history_result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation.id)
            .order_by(Message.created_at.asc())
        )
        history = [
            LLMMessage(role=item.role, content=item.content) for item in history_result.scalars()
        ]
        system = (
            f"Tu es {personality.name}. Langue principale : {personality.language}. "
            f"{personality.response_style}\n{personality.system_instructions}"
        )
        response_text = await llm_registry.get(provider_id).complete(history[-30:], model, system)
        assistant_message = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response_text,
            provider=provider_id,
            model=model,
        )
        session.add(assistant_message)
        if conversation.title == "Nouvelle conversation":
            conversation.title = request.message.strip()[:80]
        await session.commit()
        await session.refresh(assistant_message)
        return ChatResponse(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            response=response_text,
            provider=provider_id,
            model=model,
        )

    async def _get_conversation(
        self, session: AsyncSession, conversation_id: str | None
    ) -> Conversation:
        if conversation_id:
            result = await session.execute(
                select(Conversation)
                .options(selectinload(Conversation.messages))
                .where(Conversation.id == conversation_id)
            )
            if conversation := result.scalar_one_or_none():
                return conversation
        conversation = Conversation()
        session.add(conversation)
        await session.flush()
        return conversation


orchestrator = Orchestrator()
