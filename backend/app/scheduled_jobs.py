"""Scheduled billing rollover and per-user reminder creation.

Run daily with ``python -m app.scheduled_jobs`` after migrations have been applied.
"""

from datetime import UTC, date, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import ensure_due_periods
from app.db import SessionLocal
from app.models import BillingPeriod, Notification, Resident, User
from app.services import resident_out, today_local


def run_daily_jobs(db: Session, as_of: date | None = None) -> dict[str, int]:
    today = as_of or today_local()
    operator = db.scalar(select(User).where(User.is_primary.is_(True), User.is_active.is_(True)))
    if not operator:
        raise RuntimeError("Faol asosiy operator topilmadi; rejalashtirilgan ishlar bajarilmadi.")

    residents = db.scalars(select(Resident).where(Resident.is_archived.is_(False))).all()
    before_count = db.scalar(select(func.count(BillingPeriod.id))) or 0
    ensure_due_periods(db, residents, operator)
    after_count = db.scalar(select(func.count(BillingPeriod.id))) or 0
    created_periods = max(0, after_count - before_count)

    users = db.scalars(select(User).where(User.is_active.is_(True))).all()
    created_reminders = 0
    for resident in residents:
        state = resident_out(db, resident, today)
        if state.billing_status not in {"DUE_TODAY", "DUE_SOON", "OVERDUE"}:
            continue
        title = {
            "DUE_TODAY": "To'lov bugun",
            "DUE_SOON": "To'lov muddati yaqin",
            "OVERDUE": "To'lov muddati o'tgan",
        }[state.billing_status]
        delta = state.overdue_days if state.billing_status == "OVERDUE" else ((state.billing_end - today).days if state.billing_end else 0)
        message = f"{state.first_name} {state.last_name} · {state.room_number or 'Xona yo\u0027q'}-xona · {state.balance} so'm"
        if state.billing_status == "OVERDUE":
            message += f" · {delta} kun kechikdi"
        for user in users:
            notification_id = uuid5(NAMESPACE_URL, f"rs-best-hostel:due:{today.isoformat()}:{user.id}:{resident.id}")
            if db.get(Notification, notification_id):
                continue
            db.add(Notification(
                id=notification_id, user_id=user.id, title=title, message=message,
                kind=state.billing_status, entity_id=resident.id, read_at=None,
                created_at=datetime.now(UTC),
            ))
            created_reminders += 1
    db.commit()
    return {"billing_periods_created": created_periods, "reminders_created": created_reminders}


def main() -> None:
    with SessionLocal() as db:
        result = run_daily_jobs(db)
    print(f"Yaratilgan to'lov davrlari: {result['billing_periods_created']}; bildirishnomalar: {result['reminders_created']}")


if __name__ == "__main__":
    main()
