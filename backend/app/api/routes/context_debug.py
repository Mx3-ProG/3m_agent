from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.context.engine import context_engine
from backend.app.core.config import get_settings
from backend.app.core.database import get_session
from backend.app.models.entities import Conversation
from backend.app.security.auth import require_api_token

router = APIRouter(prefix="/debug", tags=["debug"], dependencies=[Depends(require_api_token)])


@router.get("/conversations/{conversation_id}/context")
async def debug_context(conversation_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    if get_settings().env != "development":
        raise HTTPException(status_code=404, detail="Endpoint indisponible")
    conversation = await session.get(Conversation, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation introuvable")
    package = await context_engine.build(session, conversation, "")
    return package.model_dump(mode="json")
