"""Staff task board (Kanban) API.

Authorization (server-side):
- Any active staff member (OPERATOR or ADMIN) can read the board and create tasks.
- OPERATOR can assign tasks to anyone and edit any task.
- ADMIN can only assign tasks to themself (or leave them unassigned) and can only edit
  tasks they created or that are assigned to them.
- Tasks are never hard-deleted; they are moved to ``CANCELLED`` and every change is audited.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.audit import audit, notify
from app.db import get_db
from app.dependencies import get_current_user
from app.models import Resident, Room, StaffTask, User
from app.schemas import StaffTaskCreate, StaffTaskOut, StaffTaskUpdate, TaskAssigneeOut
from app.services import today_local

router = APIRouter(prefix="/api")

PRIORITY_RANK = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
OPEN_STATUSES = ("TODO", "IN_PROGRESS")
PRIORITY_UZ = {"URGENT": "Shoshilinch", "HIGH": "Yuqori", "NORMAL": "Oddiy", "LOW": "Past"}


def _can_edit(task: StaffTask, actor: User) -> bool:
    return actor.role == "OPERATOR" or task.created_by == actor.id or task.assignee_id == actor.id


def _check_assignee(db: Session, actor: User, assignee_id: UUID | None) -> User | None:
    if assignee_id is None:
        return None
    if actor.role != "OPERATOR" and assignee_id != actor.id:
        raise HTTPException(status_code=403, detail="Vazifani boshqa xodimga faqat operator biriktira oladi.")
    assignee = db.get(User, assignee_id)
    if not assignee or not assignee.is_active:
        raise HTTPException(status_code=422, detail="Mas’ul xodim topilmadi yoki faol emas.")
    return assignee


def _check_links(db: Session, room_id: UUID | None, resident_id: UUID | None) -> None:
    if room_id is not None and not db.get(Room, room_id):
        raise HTTPException(status_code=422, detail="Bog‘langan xona topilmadi.")
    if resident_id is not None and not db.get(Resident, resident_id):
        raise HTTPException(status_code=422, detail="Bog‘langan yashovchi topilmadi.")


def task_out(db: Session, task: StaffTask, actor: User) -> StaffTaskOut:
    assignee = db.get(User, task.assignee_id) if task.assignee_id else None
    creator = db.get(User, task.created_by)
    room = db.get(Room, task.room_id) if task.room_id else None
    resident = db.get(Resident, task.resident_id) if task.resident_id else None
    return StaffTaskOut(
        id=task.id, title=task.title, description=task.description, status=task.status, priority=task.priority,
        due_date=task.due_date, assignee_id=task.assignee_id, assignee_name=assignee.full_name if assignee else None,
        created_by=task.created_by, created_by_name=creator.full_name if creator else "",
        room_id=task.room_id, room_number=room.number if room else None,
        resident_id=task.resident_id, resident_name=f"{resident.first_name} {resident.last_name}" if resident else None,
        completed_at=task.completed_at, created_at=task.created_at, updated_at=task.updated_at,
        is_overdue=bool(task.due_date and task.status in OPEN_STATUSES and task.due_date < today_local()),
        can_edit=_can_edit(task, actor),
    )


def _audit_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


@router.get("/tasks", response_model=list[StaffTaskOut])
def list_tasks(
    scope: Literal["all", "mine", "created"] = "all",
    priority: Literal["LOW", "NORMAL", "HIGH", "URGENT"] | None = None,
    q: str = Query(default="", max_length=120),
    include_cancelled: bool = False,
    db: Session = Depends(get_db), actor: User = Depends(get_current_user),
) -> list[StaffTaskOut]:
    query = select(StaffTask)
    if not include_cancelled:
        query = query.where(StaffTask.status != "CANCELLED")
    if scope == "mine":
        query = query.where(StaffTask.assignee_id == actor.id)
    elif scope == "created":
        query = query.where(StaffTask.created_by == actor.id)
    if priority:
        query = query.where(StaffTask.priority == priority)
    if q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(or_(StaffTask.title.ilike(pattern), StaffTask.description.ilike(pattern)))
    rows = db.scalars(query.order_by(StaffTask.created_at.desc()).limit(500)).all()
    today = today_local()
    rows = sorted(rows, key=lambda t: (PRIORITY_RANK.get(t.priority, 9), t.due_date is None, t.due_date or today))
    return [task_out(db, row, actor) for row in rows]


@router.get("/tasks/summary")
def task_summary(db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> dict[str, int]:
    today = today_local()
    counts = {status: count for status, count in db.execute(select(StaffTask.status, func.count(StaffTask.id)).group_by(StaffTask.status)).all()}
    overdue = db.scalar(select(func.count(StaffTask.id)).where(StaffTask.status.in_(OPEN_STATUSES), StaffTask.due_date < today)) or 0
    mine = db.scalar(select(func.count(StaffTask.id)).where(StaffTask.status.in_(OPEN_STATUSES), StaffTask.assignee_id == actor.id)) or 0
    return {
        "todo": counts.get("TODO", 0), "in_progress": counts.get("IN_PROGRESS", 0),
        "done": counts.get("DONE", 0), "cancelled": counts.get("CANCELLED", 0),
        "overdue": overdue, "mine_open": mine,
    }


@router.get("/tasks/assignees", response_model=list[TaskAssigneeOut])
def task_assignees(db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> list[TaskAssigneeOut]:
    """Active staff names for the assignee picker; emails and account details are not exposed."""
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    if actor.role != "OPERATOR":
        users = [item for item in users if item.id == actor.id]
    return [TaskAssigneeOut(id=item.id, full_name=item.full_name, role=item.role) for item in users]


@router.post("/tasks", response_model=StaffTaskOut, status_code=201)
def create_task(payload: StaffTaskCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> StaffTaskOut:
    assignee = _check_assignee(db, actor, payload.assignee_id)
    _check_links(db, payload.room_id, payload.resident_id)
    task = StaffTask(
        title=payload.title.strip(), description=payload.description.strip(), status="TODO", priority=payload.priority,
        due_date=payload.due_date, assignee_id=payload.assignee_id, created_by=actor.id,
        room_id=payload.room_id, resident_id=payload.resident_id,
    )
    db.add(task)
    db.flush()
    audit(db, actor, "TASK_CREATED", "StaffTask", task.id, {"title": task.title, "priority": task.priority, "assignee_id": _audit_value(task.assignee_id)})
    if assignee and assignee.id != actor.id:
        notify(db, "Sizga yangi vazifa", f"{task.title} · {PRIORITY_UZ[task.priority]}", kind="TASK", entity_id=task.id, user_id=assignee.id)
    db.commit()
    db.refresh(task)
    return task_out(db, task, actor)


@router.patch("/tasks/{task_id}", response_model=StaffTaskOut)
def update_task(task_id: UUID, payload: StaffTaskUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> StaffTaskOut:
    task = db.scalar(select(StaffTask).where(StaffTask.id == task_id).with_for_update())
    if not task:
        raise HTTPException(status_code=404, detail="Vazifa topilmadi.")
    if not _can_edit(task, actor):
        raise HTTPException(status_code=403, detail="Bu vazifani faqat muallif, mas’ul xodim yoki operator o‘zgartira oladi.")
    values = payload.model_dump(exclude_unset=True)
    for key in ("title", "status", "priority", "description"):
        if key in values and values[key] is None:
            raise HTTPException(status_code=422, detail="Majburiy maydonni bo‘sh qoldirib bo‘lmaydi.")
    new_assignee = None
    if "assignee_id" in values and values["assignee_id"] != task.assignee_id:
        new_assignee = _check_assignee(db, actor, values["assignee_id"])
    _check_links(db, values.get("room_id"), values.get("resident_id"))

    changes: dict[str, dict[str, object]] = {}
    for key, value in values.items():
        if isinstance(value, str):
            value = value.strip()
        old = getattr(task, key)
        if old != value:
            changes[key] = {"old": _audit_value(old), "new": _audit_value(value)}
            setattr(task, key, value)
    if not changes:
        return task_out(db, task, actor)
    if "status" in changes:
        task.completed_at = datetime.now(UTC) if task.status == "DONE" else None
    audit(db, actor, "TASK_UPDATED", "StaffTask", task.id, {"title": task.title, "changes": changes})
    if new_assignee and new_assignee.id != actor.id:
        notify(db, "Sizga vazifa biriktirildi", f"{task.title} · {PRIORITY_UZ[task.priority]}", kind="TASK", entity_id=task.id, user_id=new_assignee.id)
    if changes.get("status", {}).get("new") == "DONE" and task.created_by != actor.id:
        notify(db, "Vazifa bajarildi", f"{task.title} · {actor.full_name}", kind="TASK_DONE", entity_id=task.id, user_id=task.created_by)
    db.commit()
    db.refresh(task)
    return task_out(db, task, actor)

