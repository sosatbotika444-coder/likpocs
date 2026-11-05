"""Staff/investor read models and actions for the Telegram bot (aiogram-free, unit-testable).

Role policy, mirroring the API:
- OPERATOR: everything ADMIN can do plus finance totals.
- ADMIN: operational data only (no money, no balances, no prices).
- INVESTOR: aggregate finance only, no names/rooms/ids.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import admissions_api as adm
from app.audit import audit
from app.models import (
    Notification, Resident, Room, StaffTask, StudentApplication, TelegramAccount, User, utcnow,
)
from app.services import room_out, today_local
from app.telegram import consume_link_code
from app.telegram_apply import upsert_account

OPEN_STATUSES = ("SUBMITTED", "IN_REVIEW", "NEEDS_INFO")
STATUS_UZ = {
    "DRAFT": "Qoralama", "SUBMITTED": "Yuborildi", "IN_REVIEW": "Tekshiruvda", "NEEDS_INFO": "Aniqlik kerak",
    "APPROVED": "Tasdiqlandi", "REJECTED": "Rad etildi", "CANCELLED": "Bekor qilindi", "ARCHIVED": "Arxiv",
}
ROLE_UZ = {"OPERATOR": "Operator", "ADMIN": "Administrator", "INVESTOR": "Investor"}


def money(value: Decimal | int | float | str) -> str:
    return f"{Decimal(str(value)):,.2f}".replace(",", " ") + " so'm"


def get_account(db: Session, chat_id: int) -> TelegramAccount | None:
    return db.scalar(select(TelegramAccount).where(TelegramAccount.chat_id == chat_id, TelegramAccount.is_active.is_(True)))


def staff_user(db: Session, chat_id: int) -> User | None:
    account = get_account(db, chat_id)
    if not account or not account.user_id:
        return None
    user = db.get(User, account.user_id)
    return user if user and user.is_active else None


def link_staff(db: Session, chat_id: int, tg_user_id: int | None, username: str, full_name: str, code: str) -> User | None:
    """Bind a chat to the user who generated ``code``; at most one active chat per user."""
    user = consume_link_code(db, code)
    if user is None:
        db.rollback()
        return None
    for other in db.scalars(select(TelegramAccount).where(TelegramAccount.user_id == user.id, TelegramAccount.is_active.is_(True))).all():
        other.is_active = False
    account = upsert_account(db, chat_id, tg_user_id, username, full_name)
    account.user_id, account.application_id = user.id, None
    audit(db, user, "TELEGRAM_LINKED", "User", user.id)
    db.commit()
    return user


def allowed_commands(user: User) -> list[str]:
    if user.role == "INVESTOR":
        return ["/summary"]
    commands = ["/applications", "/rooms", "/residents", "/tasks", "/tasknew", "/taskstart", "/taskdone", "/notifications", "/stats"]
    if user.role == "OPERATOR":
        commands.append("/summary")
    return commands


def queue_summary(db: Session, user: User) -> str:
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo‘lim faqat xodimlar uchun.")
    rows = dict(db.execute(select(StudentApplication.status, func.count()).group_by(StudentApplication.status)).all())
    lines = [f"{STATUS_UZ[key]}: {rows.get(key, 0)}" for key in ("SUBMITTED", "IN_REVIEW", "NEEDS_INFO", "APPROVED", "REJECTED")]
    return "Arizalar holati\n" + "\n".join(lines)


def open_applications(db: Session, user: User, limit: int = 8) -> list[StudentApplication]:
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo‘lim faqat xodimlar uchun.")
    return list(db.scalars(
        select(StudentApplication).where(StudentApplication.status.in_(OPEN_STATUSES))
        .order_by(StudentApplication.created_at.desc()).limit(limit)
    ).all())


def application_card(application: StudentApplication) -> str:
    name = f"{application.last_name_latin} {application.first_name_latin}".strip() or "—"
    signed = "imzolangan" if application.contract_accepted_at else "imzolanmagan"
    return f"{application.reference} · {STATUS_UZ.get(application.status, application.status)}\n{name} · {application.phone or '—'}\nShartnoma: {signed}"


def decide_application(db: Session, user: User, application_id: UUID, action: str) -> str:
    """Start review or reject (with a fixed reason) from the bot; approval needs room/tariff, so it stays on the web."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu amal faqat xodimlar uchun.")
    application = db.scalar(select(StudentApplication).where(StudentApplication.id == application_id).with_for_update())
    if not application:
        raise LookupError("Ariza topilmadi.")
    if action == "review":
        if application.status == "IN_REVIEW":
            return "Ariza allaqachon tekshiruvda."
        if application.status != "SUBMITTED":
            raise ValueError("Tekshiruv faqat yuborilgan arizadan boshlanadi.")
        application.assigned_to = user.id
        adm._event(db, application, "IN_REVIEW", user)
        audit(db, user, "APPLICATION_REVIEW_STARTED", "StudentApplication", application.id, {"via": "TELEGRAM"})
        db.commit()
        return "Tekshiruv boshlandi."
    if action == "reject":
        if application.status not in OPEN_STATUSES:
            raise ValueError("Ushbu arizani rad etib bo‘lmaydi.")
        reason = "Telegram orqali xodim tomonidan rad etildi."
        application.review_reason = reason
        application.terminal_at = utcnow()
        adm._event(db, application, "REJECTED", user, reason)
        audit(db, user, "APPLICATION_REJECTED", "StudentApplication", application.id, {"via": "TELEGRAM"})
        db.commit()
        return "Ariza rad etildi."
    raise ValueError("Noma’lum amal.")


def rooms_overview(db: Session, user: User) -> str:
    """Occupancy only: never prices or balances, for any staff role."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo‘lim faqat xodimlar uchun.")
    from app.api import natural_room_key

    rooms = sorted(db.scalars(select(Room).where(Room.is_active.is_(True))).all(), key=lambda room: natural_room_key(room.number))
    if not rooms:
        return "Xonalar topilmadi."
    lines, free = [], 0
    for room in rooms:
        info = room_out(db, room)
        free += info.available_beds
        lines.append(f"{info.number}-xona: {info.resident_count}/{info.capacity} · bo‘sh {info.available_beds}")
    return f"Bo‘sh o‘rinlar: {free}\n" + "\n".join(lines[:40])


def residents_overview(db: Session, user: User, query: str = "", limit: int = 12) -> str:
    """Operational resident lookup without money fields for either staff role."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo'lim faqat xodimlar uchun.")
    statement = select(Resident, Room.number).outerjoin(Room, Resident.room_id == Room.id).where(
        Resident.is_archived.is_(False), Resident.departed_on.is_(None),
    )
    term = query.strip()
    if term:
        like = f"%{term}%"
        statement = statement.where(
            Resident.first_name.ilike(like) | Resident.last_name.ilike(like) |
            Resident.phone.ilike(like) | Room.number.ilike(like)
        )
    rows = db.execute(statement.order_by(Resident.last_name, Resident.first_name).limit(limit)).all()
    if not rows:
        return "Yashovchilar topilmadi."
    return "\n".join(
        f"• {resident.first_name} {resident.last_name} · {number or 'xona belgilanmagan'}-xona"
        + (f" · {resident.phone}" if resident.phone else "")
        for resident, number in rows
    )


def open_tasks(db: Session, user: User, limit: int = 10) -> str:
    """The user's own open tasks (assigned to or created by them)."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo‘lim faqat xodimlar uchun.")
    rows = db.scalars(
        select(StaffTask).where(
            StaffTask.status.in_(("TODO", "IN_PROGRESS")),
            (StaffTask.assignee_id == user.id) | (StaffTask.created_by == user.id),
        ).order_by(StaffTask.due_date.is_(None), StaffTask.due_date).limit(limit)
    ).all()
    if not rows:
        return "Ochiq vazifalar yo‘q."
    today = today_local()
    return "\n".join(
        f"• [{str(task.id)[:8]}] {task.title} · {task.priority}" + (f" · muddat {task.due_date:%d.%m.%Y}" + (" (o‘tgan)" if task.due_date < today else "") if task.due_date else "")
        for task in rows
    )


def create_quick_task(db: Session, user: User, title: str) -> str:
    """Create a self-assigned task from Telegram with an audit event."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu amal faqat xodimlar uchun.")
    clean_title = title.strip()
    if not clean_title or len(clean_title) > 160:
        raise ValueError("Vazifa nomini 1-160 belgi qilib yozing.")
    task = StaffTask(title=clean_title, created_by=user.id, assignee_id=user.id, status="TODO", priority="NORMAL")
    db.add(task)
    db.flush()
    audit(db, user, "TASK_CREATED", "StaffTask", task.id, {"title": task.title, "priority": task.priority, "via": "TELEGRAM"})
    db.commit()
    return f"Vazifa yaratildi: [{str(task.id)[:8]}] {task.title}"


def change_task_status(db: Session, user: User, task_prefix: str, status: str) -> str:
    """Move a task only when the linked staff user is allowed to edit it."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu amal faqat xodimlar uchun.")
    prefix = task_prefix.strip().lower()
    matches = [task for task in db.scalars(select(StaffTask)).all() if str(task.id).lower().startswith(prefix)]
    if len(matches) != 1:
        raise ValueError("Vazifa kodi topilmadi yoki bir nechta mos keldi. /tasks orqali kodni tekshiring.")
    task = matches[0]
    if user.role != "OPERATOR" and task.created_by != user.id and task.assignee_id != user.id:
        raise PermissionError("Bu vazifani o'zgartirishga ruxsat yo'q.")
    if task.status == status:
        return "Vazifa holati allaqachon shu holatda."
    old_status = task.status
    task.status = status
    task.completed_at = utcnow() if status == "DONE" else None
    audit(db, user, "TASK_UPDATED", "StaffTask", task.id, {"title": task.title, "changes": {"status": {"old": old_status, "new": status}}, "via": "TELEGRAM"})
    db.commit()
    return f"Vazifa yangilandi: {task.title} · {status}"


def unread_notifications(db: Session, user: User) -> str:
    """Own unread notifications; ADMIN never sees financial kinds, INVESTOR gets none."""
    if user.role not in ("OPERATOR", "ADMIN"):
        raise PermissionError("Bu bo‘lim faqat xodimlar uchun.")
    from app.telegram import FINANCIAL_KINDS

    rows = db.scalars(
        select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .order_by(Notification.created_at.desc()).limit(20)
    ).all()
    rows = [item for item in rows if user.role == "OPERATOR" or item.kind not in FINANCIAL_KINDS][:10]
    if not rows:
        return "Yangi bildirishnoma yo‘q."
    return "\n\n".join(f"{item.title}\n{item.message}" for item in rows)


def finance_summary(db: Session, user: User) -> str:
    """Aggregate finance for OPERATOR/INVESTOR through the same function the website calls."""
    if user.role not in ("OPERATOR", "INVESTOR"):
        raise PermissionError("Moliyaviy ko‘rinish uchun ruxsat yo‘q.")
    from app.api import investor_summary

    today = today_local()
    start = today.replace(day=1)
    data = investor_summary(date_from=start, date_to=today, group_by="month", include_occupancy=True, db=db, _=user)
    lines = [
        f"Moliyaviy yakun ({start:%d.%m.%Y} – {today:%d.%m.%Y})",
        f"Tushum: {money(data.revenue)}",
        f"Xarajatlar: {money(data.expenses)}",
        f"Sof foyda: {money(data.net_profit)}",
        f"Umumiy qarzdorlik: {money(data.outstanding_debt)}",
    ]
    if data.occupancy_rate is not None:
        lines.append(f"Bandlik: {data.occupancy_rate}%")
    return "\n".join(lines)

