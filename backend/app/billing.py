from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
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
    if resident.departed_on is not None or not resident.payment_period_days:
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
    old_start, old_end, old_charge = period.start_date, period.end_date, period.charge_amount
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
        old_charge_amount=old_charge,
        new_start_date=period.start_date,
        new_end_date=new_end,
        new_charge_amount=period.charge_amount,
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
        old_start, old_end, old_charge = period.start_date, period.end_date, period.charge_amount
        new_charge = resident.agreed_price or ZERO
        if period_paid(db, period.id) > 0 and start < old_start:
            raise HTTPException(status_code=409, detail="To'lov qayd etilgan davrning boshlanishini oldingi sanaga surib bo'lmaydi.")
        dates_changed = old_start != start or old_end != end
        amount_changed = old_charge != new_charge
        period.start_date = start
        period.end_date = end
        period.period_days = (end - start).days
        period.charge_amount = new_charge
        if dates_changed or amount_changed:
            is_price_only = amount_changed and not dates_changed
            db.add(BillingChange(
                resident_id=resident.id,
                billing_period_id=period.id,
                old_start_date=old_start,
                old_end_date=old_end,
                old_charge_amount=old_charge,
                new_start_date=start,
                new_end_date=end,
                new_charge_amount=new_charge,
                change_type="PRICE_CHANGE" if is_price_only else "SCHEDULE_CHANGE",
                reason="Kelishilgan narx o'zgartirildi" if is_price_only else "To'lov jadvali tahrirlandi",
                changed_by=actor.id,
            ))
            action = "BILLING_PRICE_CHANGED" if is_price_only else "BILLING_SCHEDULE_CHANGED"
            audit(db, actor, action, "BillingPeriod", period.id, {
                "old_start": old_start.isoformat(), "old_end": old_end.isoformat(),
                "new_start": start.isoformat(), "new_end": end.isoformat(),
                "old_amount": str(old_charge), "new_amount": str(new_charge),
            })
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


def close_unpaid_future_periods_for_departure(
    db: Session, resident: Resident, actor: User, checkout_date: date, reason: str
) -> list[UUID]:
    """Close only unstarted, unpaid billing periods after a resident leaves."""
    periods = db.scalars(
        select(BillingPeriod)
        .where(
            BillingPeriod.resident_id == resident.id,
            BillingPeriod.status == "OPEN",
            BillingPeriod.start_date >= checkout_date,
        )
        .order_by(BillingPeriod.start_date)
        .with_for_update()
    ).all()
    closed_ids: list[UUID] = []
    for period in periods:
        if period_paid(db, period.id) > ZERO:
            continue
        period.status = "CLOSED"
        db.add(BillingChange(
            resident_id=resident.id,
            billing_period_id=period.id,
            old_start_date=period.start_date,
            old_end_date=period.end_date,
            old_charge_amount=period.charge_amount,
            new_start_date=period.start_date,
            new_end_date=period.end_date,
            new_charge_amount=period.charge_amount,
            change_type="EARLY_CHECKOUT_CLOSED",
            reason=reason,
            changed_by=actor.id,
        ))
        audit(db, actor, "FUTURE_BILLING_CLOSED", "BillingPeriod", period.id, {
            "resident_id": str(resident.id), "checkout_date": checkout_date.isoformat(),
            "charge_amount": str(period.charge_amount),
        })
        closed_ids.append(period.id)
    return closed_ids


def prorate_current_period_for_checkout(
    db: Session, resident: Resident, actor: User, checkout_date: date, reason: str,
) -> tuple[BillingPeriod | None, Decimal]:
    """Close the active billing period at departure and preserve any refund as adjustments.

    Billing intervals are [start_date, end_date): a checkout on day 18 after
    moving in on day 1 is 17 occupied days. Posted payments are never edited;
    if a resident paid more than the recalculated charge, negative
    ``PaymentAdjustment`` rows record the credit/refund amount.
    """
    period = db.scalar(
        select(BillingPeriod)
        .where(
            BillingPeriod.resident_id == resident.id,
            BillingPeriod.status.in_(("OPEN", "PAID")),
            BillingPeriod.start_date < checkout_date,
            BillingPeriod.end_date > checkout_date,
        )
        .order_by(BillingPeriod.start_date.desc())
        .with_for_update()
    )
    if period is None:
        return None, ZERO

    old_start, old_end, old_charge = period.start_date, period.end_date, period.charge_amount
    used_days = (checkout_date - old_start).days
    original_days = (old_end - old_start).days
    new_charge = (old_charge * Decimal(used_days) / Decimal(original_days)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    paid_before = period_paid(db, period.id)

    period.end_date = checkout_date
    period.period_days = used_days
    period.charge_amount = new_charge
    period.status = "CLOSED"
    db.add(BillingChange(
        resident_id=resident.id, billing_period_id=period.id,
        old_start_date=old_start, old_end_date=old_end, old_charge_amount=old_charge,
        new_start_date=old_start, new_end_date=checkout_date, new_charge_amount=new_charge,
        change_type="EARLY_CHECKOUT_PRORATED", reason=reason, changed_by=actor.id,
    ))

    credit = max(ZERO, paid_before - new_charge)
    if credit:
        remaining = credit
        payments = db.scalars(
            select(Payment).where(Payment.billing_period_id == period.id)
            .order_by(Payment.payment_date.desc(), Payment.created_at.desc()).with_for_update()
        ).all()
        adjustments = db.scalars(
            select(PaymentAdjustment).where(PaymentAdjustment.payment_id.in_([item.id for item in payments]))
        ).all() if payments else []
        net_by_payment = {item.id: item.amount for item in payments}
        for adjustment in adjustments:
            net_by_payment[adjustment.payment_id] = net_by_payment.get(adjustment.payment_id, ZERO) + adjustment.amount_delta
        for payment in payments:
            amount = min(remaining, max(ZERO, net_by_payment[payment.id]))
            if amount:
                db.add(PaymentAdjustment(
                    payment_id=payment.id, amount_delta=-amount,
                    reason=f"Muddatidan oldin chiqish qayta hisobi: {reason}", adjusted_by=actor.id,
                ))
                remaining -= amount
            if remaining == ZERO:
                break
        if remaining:
            raise RuntimeError("To'lov tuzatmasi uchun yetarli mablag' topilmadi.")

    audit(db, actor, "BILLING_EARLY_CHECKOUT_PRORATED", "BillingPeriod", period.id, {
        "resident_id": str(resident.id), "checkout_date": checkout_date.isoformat(),
        "old_end_date": old_end.isoformat(), "new_end_date": checkout_date.isoformat(),
        "old_charge_amount": str(old_charge), "new_charge_amount": str(new_charge),
        "credit_or_refund": str(credit),
    })
    return period, credit
