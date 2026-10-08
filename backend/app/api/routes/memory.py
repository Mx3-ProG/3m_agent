from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.models.entities import AuditLog, MemoryItem
from backend.app.models.schemas import MemoryCreate, MemoryRead
from backend.app.security.auth import require_api_token

router = APIRouter(prefix="/memory", tags=["memory"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[MemoryRead])
async def list_memory(session: AsyncSession = Depends(get_session)) -> list[MemoryItem]:
    result = await session.execute(select(MemoryItem).order_by(MemoryItem.created_at.desc()))
    return list(result.scalars())


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def remember(
    payload: MemoryCreate, session: AsyncSession = Depends(get_session)
) -> MemoryItem:
    if payload.sensitive:
        raise HTTPException(
            status_code=422,
            detail="3M refuse l’enregistrement durable d’une donnée marquée sensible.",
        )
    item = MemoryItem(**payload.model_dump())
    session.add_all([item, AuditLog(action="memory.create", target=item.id, outcome="success")])
    await session.commit()
    await session.refresh(item)
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def forget(item_id: str, session: AsyncSession = Depends(get_session)) -> Response:
    item = await session.get(MemoryItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Souvenir introuvable")
    await session.delete(item)
    session.add(AuditLog(action="memory.delete", target=item_id, outcome="success"))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
