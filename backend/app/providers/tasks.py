from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.entities import Task


def task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority,
        "status": task.status,
        "due_at": task.due_at.isoformat() if task.due_at else None,
    }


class TaskProvider:
    async def list_tasks(self, session: AsyncSession) -> list[dict]:
        result = await session.execute(select(Task).order_by(Task.created_at.desc()))
        return [task_dict(task) for task in result.scalars()]

    async def create_task(self, session: AsyncSession, values: dict) -> dict:
        task = Task(**values)
        session.add(task)
        await session.flush()
        return task_dict(task)

    async def update_task(self, session: AsyncSession, task_id: str, values: dict) -> dict:
        task = await session.get(Task, task_id)
        if not task:
            raise ValueError("Tâche introuvable")
        for key, value in values.items():
            if value is not None:
                setattr(task, key, value)
        await session.flush()
        return task_dict(task)

    async def complete_task(self, session: AsyncSession, task_id: str) -> dict:
        return await self.update_task(session, task_id, {"status": "done"})

    async def delete_task(self, session: AsyncSession, task_id: str) -> dict:
        task = await session.get(Task, task_id)
        if not task:
            raise ValueError("Tâche introuvable")
        snapshot = task_dict(task)
        await session.delete(task)
        await session.flush()
        return snapshot


task_provider = TaskProvider()
