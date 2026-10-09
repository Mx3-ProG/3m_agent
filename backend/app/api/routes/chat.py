import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import SessionLocal, get_session
from backend.app.models.entities import Conversation, Message
from backend.app.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationRead,
    ConversationUpdate,
    MessageRead,
)
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


@router.post("", response_model=ConversationRead, status_code=201)
async def create_conversation(
    payload: ConversationCreate, session: AsyncSession = Depends(get_session)
) -> Conversation:
    conversation = Conversation(title=payload.title or "Nouvelle conversation")
    session.add(conversation)
    await session.commit()
    await session.refresh(conversation)
    return conversation


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[tuple[str, dict] | None] = asyncio.Queue()

        async def progress(event: str, payload: dict) -> None:
            await queue.put((event, payload))

        async def run() -> None:
            async with SessionLocal() as session:
                try:
                    response = await orchestrator.chat(request, session, on_progress=progress)
                    await queue.put(("result", response.model_dump(mode="json")))
                except ProviderConfigurationError as exc:
                    await session.rollback()
                    await queue.put(("error", {"state": "error", "detail": str(exc)}))
                except Exception:
                    await session.rollback()
                    await queue.put(
                        (
                            "error",
                            {"state": "error", "detail": "Erreur interne de l’orchestrateur"},
                        )
                    )
                finally:
                    await queue.put(None)

        task = asyncio.create_task(run())
        yield ":" + (" " * 2048) + "\n\n"
        try:
            while item := await queue.get():
                event, payload = item
                yield f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=list[ConversationRead])
async def list_conversations(
    status: str = "active",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.status == status)
        .order_by(Conversation.last_message_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars())


@router.get("/{conversation_id}", response_model=ConversationRead)
async def get_conversation(
    conversation_id: str, session: AsyncSession = Depends(get_session)
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationRead)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    session: AsyncSession = Depends(get_session),
) -> Conversation:
    conversation = await session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(conversation, key, value)
    await session.commit()
    await session.refresh(conversation)
    return conversation


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


@router.post("/{conversation_id}/messages", response_model=ChatResponse)
async def add_message(
    conversation_id: str,
    request: ChatRequest,
    session: AsyncSession = Depends(get_session),
) -> ChatResponse:
    if not await session.get(Conversation, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    return await orchestrator.chat(
        request.model_copy(update={"conversation_id": conversation_id}), session
    )
