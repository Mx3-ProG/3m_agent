from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_session
from backend.app.models.entities import AuditLog, Task
from backend.app.models.schemas import ConfirmationRequest, TaskCreate, TaskRead, TaskUpdate
from backend.app.security.auth import require_api_token
from backend.app.services.confirmations import consume_confirmation, create_confirmation

router = APIRouter(prefix="/tasks", tags=["tasks"], dependencies=[Depends(require_api_token)])


@router.get("", response_model=list[TaskRead])
async def list_tasks(session: AsyncSession = Depends(get_session)) -> list[Task]:
    result = await session.execute(select(Task).order_by(Task.created_at.desc()))
    return list(result.scalars())


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, session: AsyncSession = Depends(get_session)) -> Task:
    task = Task(**payload.model_dump())
    session.add_all([task, AuditLog(action="task.create", target=task.id, outcome="success")])
    await session.commit()
    await session.refresh(task)
    return task


@router.patch("/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str, payload: TaskUpdate, session: AsyncSession = Depends(get_session)
) -> Task:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    session.add(AuditLog(action="task.update", target=task.id, outcome="success"))
    await session.commit()
    await session.refresh(task)
    return task


@router.post("/{task_id}/delete-request")
async def request_delete(task_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    if not await session.get(Task, task_id):
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    confirmation = await create_confirmation(session, "task.delete", task_id)
    return {"confirmation_id": confirmation.id, "expires_at": confirmation.expires_at}


@router.post("/{task_id}/delete-confirm", status_code=status.HTTP_204_NO_CONTENT)
async def confirm_delete(
    task_id: str,
    payload: ConfirmationRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    task = await session.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Tâche introuvable")
    if not await consume_confirmation(session, payload.confirmation_id, "task.delete", task_id):
        raise HTTPException(status_code=409, detail="Confirmation invalide ou expirée")
    await session.delete(task)
    session.add(AuditLog(action="task.delete", target=task_id, outcome="success"))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
