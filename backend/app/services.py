from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.billing import current_period, period_balance, period_paid
from app.config import settings
from app.models import AuditEvent, BillingChange, BillingPeriod, Notification, Payment, PaymentAdjustment, Resident, Room, User
from app.schemas import AuditEventOut, BillingChangeOut, BillingPeriodOut, NotificationOut, PaymentOut, ResidentDetail, ResidentOut, RoomOut


def today_local() -> date:
    return datetime.now(ZoneInfo(settings.timezone)).date()


def room_out(db: Session, room: Room) -> RoomOut:
    residents = db.scalars(select(Resident).where(Resident.room_id == room.id, Resident.is_archived.is_(False))).all()
    resident_count = len(residents)
    return RoomOut(
        id=room.id,
        number=room.number,
        floor=room.floor,
        capacity=room.capacity,
        price=room.price,
        notes=room.notes,
        is_active=room.is_active,
        resident_count=resident_count,
        available_beds=max(0, room.capacity - resident_count),
    )


def period_out(db: Session, period: BillingPeriod) -> BillingPeriodOut:
    paid = period_paid(db, period.id)
    return BillingPeriodOut(
        id=period.id,
        start_date=period.start_date,
        end_date=period.end_date,
        period_days=period.period_days,
        charge_amount=period.charge_amount,
        paid_amount=paid,
        balance=period_balance(db, period),
        status=period.status,
    )


def resident_out(db: Session, resident: Resident, as_of: date | None = None) -> ResidentOut:
    today = as_of or today_local()
    period = current_period(db, resident.id)
    if period is None:
        period = db.scalar(
            select(BillingPeriod)
            .where(BillingPeriod.resident_id == resident.id, BillingPeriod.status == "PAID")
            .order_by(BillingPeriod.end_date.desc(), BillingPeriod.created_at.desc())
        )
    paid = period_paid(db, period.id) if period else Decimal("0")
    balance = period_balance(db, period) if period else Decimal("0")
    configured = bool(
        period
        and period.start_date
        and period.end_date
        and period.period_days > 0
        and resident.agreed_price is not None
        and resident.agreed_price > 0
    )
    if not configured:
        state = "NOT_CONFIGURED"
        overdue_days = 0
    elif balance == 0:
        state = "PAID"
        overdue_days = 0
    else:
        delta = (period.end_date - today).days
        if delta < 0:
            state = "OVERDUE"
            overdue_days = -delta
        elif delta == 0:
            state = "DUE_TODAY"
            overdue_days = 0
        elif delta <= 7:
            state = "DUE_SOON"
            overdue_days = 0
        else:
            state = "CURRENT"
            overdue_days = 0
    return ResidentOut(
        id=resident.id,
        first_name=resident.first_name,
        last_name=resident.last_name,
        phone=resident.phone,
        telegram_username=resident.telegram_username,
        room_id=resident.room_id,
        room_number=resident.room.number if resident.room else None,
        check_in_date=resident.check_in_date,
        payment_period_days=resident.payment_period_days,
        agreed_price=resident.agreed_price,
        notes=resident.notes,
        is_archived=resident.is_archived,
        created_at=resident.created_at,
        updated_at=resident.updated_at,
        billing_start=period.start_date if period else None,
        billing_end=period.end_date if period else None,
        billing_period_id=period.id if period else None,
        billing_status=state,
        paid_amount=paid,
        balance=balance,
        overdue_days=overdue_days,
    )


def resident_detail(db: Session, resident: Resident) -> ResidentDetail:
    basic = resident_out(db, resident).model_dump()
    periods = db.scalars(
        select(BillingPeriod)
        .where(BillingPeriod.resident_id == resident.id)
        .order_by(BillingPeriod.start_date.desc(), BillingPeriod.created_at.desc())
    ).all()
    changes = db.scalars(
        select(BillingChange)
        .where(BillingChange.resident_id == resident.id)
        .order_by(BillingChange.created_at.desc())
    ).all()
    return ResidentDetail(
        **basic,
        billing_history=[period_out(db, item) for item in periods],
        changes=[BillingChangeOut.model_validate(item) for item in changes],
    )


def payment_out(db: Session, payment: Payment) -> PaymentOut:
    adjustments = db.scalars(select(PaymentAdjustment).where(PaymentAdjustment.payment_id == payment.id)).all()
    net = payment.amount + sum((item.amount_delta for item in adjustments), Decimal("0"))
    recorder = db.get(User, payment.recorded_by)
    return PaymentOut(
        id=payment.id,
        resident_id=payment.resident_id,
        resident_name=f"{payment.resident.first_name} {payment.resident.last_name}",
        billing_period_id=payment.billing_period_id,
        amount=payment.amount,
        net_amount=max(Decimal("0"), net),
        payment_date=payment.payment_date,
        method=payment.method,
        covered_start=payment.covered_start,
        covered_end=payment.covered_end,
        notes=payment.notes,
        recorded_by=payment.recorded_by,
        recorded_by_name=recorder.full_name if recorder else "",
        created_at=payment.created_at,
    )


def notification_out(item: Notification) -> NotificationOut:
    return NotificationOut.model_validate(item)


def audit_out(db: Session, event: AuditEvent) -> AuditEventOut:
    actor = db.get(User, event.actor_id) if event.actor_id else None
    return AuditEventOut(
        id=event.id,
        actor_id=event.actor_id,
        actor_name=actor.full_name if actor else "Noma’lum foydalanuvchi",
        action=event.action,
        entity_type=event.entity_type,
        entity_id=event.entity_id,
        details=event.details or {},
        created_at=event.created_at,
    )
