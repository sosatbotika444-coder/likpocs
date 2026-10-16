from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import audit
from app.config import settings
from app.models import BillingChange, BillingPeriod, Payment, PaymentAdjustment, Resident, User

ZERO = Decimal("0.00")


def period_paid(db: Session, period_id: UUID) -> Decimal:
    payments = db.scalars(select(Payment).where(Payment.billing_period_id == period_id)).all()
    total = sum((payment.amount for payment in payments), ZERO)
    if payments:
        adjustments = db.scalars(
            select(PaymentAdjustment).where(PaymentAdjustment.payment_id.in_([p.id for p in payments]))
        ).all()
        total += sum((entry.amount_delta for entry in adjustments), ZERO)
    return max(ZERO, total)


def period_balance(db: Session, period: BillingPeriod) -> Decimal:
    return max(ZERO, period.charge_amount - period_paid(db, period.id))


def current_period(db: Session, resident_id: UUID) -> BillingPeriod | None:
    return db.scalar(
        select(BillingPeriod)
        .where(BillingPeriod.resident_id == resident_id, BillingPeriod.status == "OPEN")
        .order_by(BillingPeriod.start_date.desc(), BillingPeriod.created_at.desc())
    )


def ensure_period(db: Session, resident: Resident, actor: User | None, as_of: date | None = None) -> BillingPeriod | None:
    if not resident.payment_period_days:
        return None
    open_period = current_period(db, resident.id)
    if open_period:
        return open_period
    latest = db.scalar(
        select(BillingPeriod)
        .where(BillingPeriod.resident_id == resident.id, BillingPeriod.status != "CLOSED")
        .order_by(BillingPeriod.end_date.desc(), BillingPeriod.created_at.desc())
    )
    if not latest or latest.status != "PAID":
        return None
    effective_date = as_of or datetime.now(ZoneInfo(settings.timezone)).date()
    # A settled period does not create new debt before the next stay period starts.
    # This keeps an early full payment visibly paid until its end date.
    if latest.end_date > effective_date:
        return None
    start = latest.end_date
    period = BillingPeriod(
        resident_id=resident.id,
        start_date=start,
        end_date=start + timedelta(days=resident.payment_period_days),
        period_days=resident.payment_period_days,
        charge_amount=resident.agreed_price or ZERO,
        status="OPEN",
        created_by=actor.id if actor else None,
    )
    db.add(period)
    db.flush()
    audit(db, actor, "BILLING_CYCLE_CREATED", "BillingPeriod", period.id, {"resident_id": str(resident.id)})
    return period


def create_initial_period(db: Session, resident: Resident, start: date, end: date, actor: User) -> BillingPeriod:
    if end <= start:
        raise HTTPException(status_code=422, detail="Davr tugashi boshlanishidan keyin bo‘lishi kerak.")
    period = BillingPeriod(
        resident_id=resident.id,
        start_date=start,
        end_date=end,
        period_days=(end - start).days,
        charge_amount=resident.agreed_price or ZERO,
        status="OPEN",
        created_by=actor.id,
    )
    db.add(period)
    db.flush()
    return period


def extend_period(
    db: Session,
    resident: Resident,
    actor: User,
    days: int | None = None,
    end_date: date | None = None,
    reason: str = "",
) -> BillingPeriod:
    period = current_period(db, resident.id)
    if not period:
        raise HTTPException(status_code=409, detail="Yashovchida ochiq to‘lov davri yo‘q.")
    old_start, old_end = period.start_date, period.end_date
    if end_date is not None:
        new_end = end_date
        added_days = (new_end - old_end).days
    elif days is not None:
        if days < 1:
            raise HTTPException(status_code=422, detail="Kunlar soni musbat butun son bo‘lishi kerak.")
        new_end = old_end + timedelta(days=days)
        added_days = days
    else:
        raise HTTPException(status_code=422, detail="Kunlar soni yoki yangi tugash sanasini kiriting.")
    if new_end <= old_end:
        raise HTTPException(status_code=422, detail="Yangi muddat joriy muddatdan keyin bo‘lishi kerak.")
    period.end_date = new_end
    period.period_days = (new_end - period.start_date).days
    resident.updated_at = datetime.now(UTC)
    change = BillingChange(
        resident_id=resident.id,
        billing_period_id=period.id,
        old_start_date=old_start,
        old_end_date=old_end,
        new_start_date=period.start_date,
        new_end_date=new_end,
        change_type="EXTENSION",
        reason=reason,
        changed_by=actor.id,
    )
    db.add(change)
    db.flush()
    audit(db, actor, "BILLING_EXTENDED", "BillingPeriod", period.id, {"days_added": added_days, "new_end": new_end.isoformat()})
    return period


def set_period_dates(
    db: Session, resident: Resident, actor: User, start: date, end: date, days: int
) -> BillingPeriod:
    if end <= start:
        raise HTTPException(status_code=422, detail="Davr tugashi boshlanishidan keyin bo‘lishi kerak.")
    period = current_period(db, resident.id)
    if period:
        old_start, old_end = period.start_date, period.end_date
        if period_paid(db, period.id) > 0 and start < old_start:
            raise HTTPException(status_code=409, detail="To‘lov qayd etilgan davrning boshlanishini oldingi sanaga surib bo‘lmaydi.")
        period.start_date = start
        period.end_date = end
        period.period_days = (end - start).days
        period.charge_amount = resident.agreed_price or ZERO
        db.add(BillingChange(
            resident_id=resident.id,
            billing_period_id=period.id,
            old_start_date=old_start,
            old_end_date=old_end,
            new_start_date=start,
            new_end_date=end,
            change_type="SCHEDULE_CHANGE",
            reason="To‘lov jadvali tahrirlandi",
            changed_by=actor.id,
        ))
        audit(db, actor, "BILLING_SCHEDULE_CHANGED", "BillingPeriod", period.id, {"old_end": old_end.isoformat(), "new_end": end.isoformat()})
    else:
        period = create_initial_period(db, resident, start, end, actor)
        audit(db, actor, "BILLING_PERIOD_CREATED", "BillingPeriod", period.id)
    resident.payment_period_days = days
    db.flush()
    return period


def mark_paid_and_advance(db: Session, period: BillingPeriod, actor: User) -> BillingPeriod | None:
    if period_balance(db, period) > 0:
        return None
    period.status = "PAID"
    db.flush()
    return ensure_period(db, period.resident, actor)
