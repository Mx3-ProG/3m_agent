from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.models.entities import Conversation, Message
from backend.app.models.schemas import ChatRequest, ChatResponse, ConversationRead, MessageRead
from backend.app.orchestrator.service import orchestrator
from backend.app.providers.llm import ProviderConfigurationError
from backend.app.security.auth import require_api_token

router = APIRouter(
    prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_api_token)]
)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, session: AsyncSession = Depends(get_session)) -> ChatResponse:
    try:
        return await orchestrator.chat(request, session)
    except ProviderConfigurationError as exc:
        await session.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[ConversationRead])
async def list_conversations(session: AsyncSession = Depends(get_session)) -> list[Conversation]:
    result = await session.execute(
        select(Conversation).order_by(Conversation.updated_at.desc()).limit(50)
    )
    return list(result.scalars())


@router.get("/{conversation_id}/messages", response_model=list[MessageRead])
async def list_messages(
    conversation_id: str, session: AsyncSession = Depends(get_session)
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars())
