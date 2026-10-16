from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from os.path import exists
from typing import Literal
from uuid import UUID, NAMESPACE_URL, uuid5

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.audit import audit, notify
from app.billing import (
    create_initial_period,
    current_period,
    extend_period,
    mark_paid_and_advance,
    period_balance,
    period_paid,
    set_period_dates,
)
from app.config import settings
from app.db import get_db
from app.dependencies import get_current_user, require_billing_permission, require_operator
from app.models import (
    AuditEvent,
    BillingChange,
    BillingPeriod,
    Notification,
    Payment,
    PaymentAdjustment,
    Resident,
    Room,
    SystemSetting,
    User,
)
from app.schemas import (
    AuditEventOut,
    BillingPeriodOut,
    DashboardOut,
    ExtendRequest,
    LoginRequest,
    NotificationOut,
    PageInfo,
    PaymentAdjustmentCreate,
    PaymentAdjustmentOut,
    PaymentCreate,
    PaymentOut,
    RefreshRequest,
    ResidentCreate,
    ResidentDetail,
    ResidentOut,
    ResidentUpdate,
    RoomCreate,
    RoomOut,
    RoomUpdate,
    SystemSettingsIn,
    SystemSettingsOut,
    TokenPair,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.security import create_token_pair, hash_password, verify_password
from app.services import audit_out, notification_out, payment_out, resident_detail, resident_out, room_out, today_local

router = APIRouter(prefix="/api")
UZ_MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"]
METHOD_UZ = {"CASH": "Naqd pul", "BANK": "Bank o‘tkazmasi", "CLICK": "Click", "PAYME": "Payme", "OTHER": "Boshqa"}
STATUS_UZ = {
    "PAID": "To‘langan", "CURRENT": "Amalda", "DUE_SOON": "Yaqinlashmoqda",
    "DUE_TODAY": "Bugun to‘lanadi", "OVERDUE": "Muddati o‘tgan",
    "NOT_CONFIGURED": "Davr belgilanmagan",
}


def page_result(items: list, total: int, skip: int, limit: int) -> PageInfo:
    return PageInfo(items=items, total=total, skip=skip, limit=limit)


def verify_room_capacity(db: Session, room_id: UUID | None, resident_id: UUID | None = None) -> Room | None:
    if room_id is None:
        return None
    room = db.scalar(select(Room).where(Room.id == room_id).with_for_update())
    if not room or not room.is_active:
        raise HTTPException(status_code=422, detail="Tanlangan xona topilmadi yoki faol emas.")
    query = select(func.count(Resident.id)).where(Resident.room_id == room_id, Resident.is_archived.is_(False))
    if resident_id:
        query = query.where(Resident.id != resident_id)
    occupants = db.scalar(query) or 0
    if occupants >= room.capacity:
        raise HTTPException(status_code=409, detail="Xonada bo‘sh o‘rin qolmagan.")
    return room


def net_payment(db: Session, payment: Payment) -> Decimal:
    adjustments = db.scalars(select(PaymentAdjustment).where(PaymentAdjustment.payment_id == payment.id)).all()
    return max(Decimal("0"), payment.amount + sum((item.amount_delta for item in adjustments), Decimal("0")))


def get_report_rows(
    db: Session,
    kind: str,
    date_from: date | None = None,
    date_to: date | None = None,
    interval: Literal["day", "week", "month"] = "month",
) -> tuple[list[str], list[list[object]]]:
    if kind == "residents":
        headers = ["Ism", "Familiya", "Telefon", "Telegram", "Xona", "Ko‘chib kirgan sana", "Davr (kun)", "Keyingi muddat", "Kelishilgan narx (so‘m)", "Qarzdorlik (so‘m)", "Holat"]
        residents = db.scalars(select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(False)).order_by(Resident.last_name, Resident.first_name)).all()
        rows = []
        for resident in residents:
            item = resident_out(db, resident)
            rows.append([item.first_name, item.last_name, item.phone or "", item.telegram_username or "", item.room_number or "", item.check_in_date or "", item.payment_period_days or "", item.billing_end or "", item.agreed_price or 0, item.balance, STATUS_UZ[item.billing_status]])
        return headers, rows
    if kind == "rooms":
        headers = ["Xona", "Qavat", "Sig‘im", "Band", "Bo‘sh o‘rin", "Narx (so‘m)", "Izoh"]
        rooms = db.scalars(select(Room).where(Room.is_active.is_(True)).order_by(Room.number)).all()
        rows = []
        for room in rooms:
            item = room_out(db, room)
            rows.append([room.number, room.floor, room.capacity, item.resident_count, item.available_beds, room.price or "", room.notes])
        return headers, rows
    if kind in {"payments", "debts", "overdue", "revenue"}:
        start = date_from or date.min
        end = date_to or date.max
        payments = db.scalars(
            select(Payment).options(joinedload(Payment.resident)).where(Payment.payment_date.between(start, end)).order_by(Payment.payment_date.desc(), Payment.created_at.desc())
        ).all()
        if kind == "payments":
            headers = ["Yashovchi", "Summa (so‘m)", "Sana", "To‘lov usuli", "Davr boshlanishi", "Davr tugashi", "Qayd etdi", "Izoh"]
            rows = [[f"{p.resident.first_name} {p.resident.last_name}", net_payment(db, p), p.payment_date, METHOD_UZ[p.method], p.covered_start or "", p.covered_end or "", db.get(User, p.recorded_by).full_name if db.get(User, p.recorded_by) else "", p.notes] for p in payments]
            return headers, rows
        if kind == "revenue":
            headers = ["Davr boshlanishi", "Haqiqiy tushum (so‘m)"]
            buckets: dict[date, Decimal] = {}
            for payment in payments:
                if interval == "day":
                    bucket = payment.payment_date
                elif interval == "week":
                    bucket = payment.payment_date - timedelta(days=payment.payment_date.weekday())
                else:
                    bucket = payment.payment_date.replace(day=1)
                buckets[bucket] = buckets.get(bucket, Decimal("0")) + net_payment(db, payment)
            rows = [[bucket, amount] for bucket, amount in sorted(buckets.items())]
            return headers, rows
    if kind in {"debts", "overdue"}:
        headers = ["Yashovchi", "Xona", "Muddat", "Qarzdorlik (so‘m)", "Kechikish (kun)", "Holat"]
        residents = db.scalars(select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(False)).order_by(Resident.last_name, Resident.first_name)).all()
        rows = []
        for resident in residents:
            item = resident_out(db, resident)
            if item.balance <= 0 or (kind == "overdue" and item.billing_status != "OVERDUE"):
                continue
            rows.append([f"{item.first_name} {item.last_name}", item.room_number or "", item.billing_end or "", item.balance, item.overdue_days, STATUS_UZ[item.billing_status]])
        return headers, rows
    raise HTTPException(status_code=404, detail="Hisobot turi topilmadi.")


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(1))
    return {"status": "ok"}


@router.post("/auth/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    user = db.scalar(select(User).where(User.email == str(payload.email).lower()))
    if not user or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Elektron pochta yoki parol noto‘g‘ri.")
    audit(db, user, "LOGIN", "User", user.id)
    db.commit()
    return TokenPair(**create_token_pair(user.id))


@router.post("/auth/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    try:
        token_payload = jwt.decode(payload.refresh_token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if token_payload.get("type") != "refresh":
            raise ValueError("wrong token type")
        user_id = UUID(token_payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Sessiyani yangilab bo‘lmadi. Qayta kiring.") from None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Foydalanuvchi faol emas.")
    return TokenPair(**create_token_pair(user.id))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_operator)) -> list[User]:
    return db.scalars(select(User).order_by(User.created_at)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> User:
    user = User(email=str(payload.email).lower(), full_name=payload.full_name.strip(), password_hash=hash_password(payload.password), role="ADMIN", is_active=True, is_primary=False)
    db.add(user)
    db.flush()
    audit(db, actor, "USER_CREATED", "User", user.id, {"email": user.email, "role": user.role})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu elektron pochta allaqachon ro‘yxatdan o‘tgan.") from None
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: UUID, payload: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> User:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Foydalanuvchi topilmadi.")
    values = payload.model_dump(exclude_unset=True)
    if user.is_primary and values.get("is_active") is False:
        raise HTTPException(status_code=409, detail="Asosiy operatorni faolsizlantirib bo‘lmaydi.")
    if "full_name" in values and values["full_name"] is not None:
        user.full_name = values["full_name"].strip()
    if values.get("password"):
        user.password_hash = hash_password(values["password"])
    if "is_active" in values and values["is_active"] is not None:
        user.is_active = values["is_active"]
    audit(db, actor, "USER_UPDATED", "User", user.id, {"changed_fields": sorted(k for k in values if k != "password")})
    db.commit()
    db.refresh(user)
    return user


@router.get("/rooms", response_model=PageInfo)
def list_rooms(
    status_filter: Literal["all", "available", "full"] = Query(default="all", alias="status"),
    skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
) -> PageInfo:
    rooms = db.scalars(select(Room).where(Room.is_active.is_(True)).order_by(Room.number)).all()
    items = [room_out(db, room) for room in rooms]
    if status_filter == "available":
        items = [room for room in items if room.available_beds > 0]
    elif status_filter == "full":
        items = [room for room in items if room.available_beds == 0]
    return page_result(items[skip:skip + limit], len(items), skip, limit)


@router.post("/rooms", response_model=RoomOut, status_code=201)
def create_room(payload: RoomCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> RoomOut:
    room = Room(number=payload.number.strip(), floor=payload.floor, capacity=payload.capacity, price=payload.price, notes=payload.notes.strip())
    db.add(room)
    db.flush()
    audit(db, actor, "ROOM_CREATED", "Room", room.id, {"number": room.number})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu xona raqami mavjud.") from None
    db.refresh(room)
    return room_out(db, room)


@router.patch("/rooms/{room_id}", response_model=RoomOut)
def update_room(room_id: UUID, payload: RoomUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> RoomOut:
    room = db.get(Room, room_id)
    if not room or not room.is_active:
        raise HTTPException(status_code=404, detail="Xona topilmadi.")
    values = payload.model_dump(exclude_unset=True)
    occupant_count = db.scalar(select(func.count(Resident.id)).where(Resident.room_id == room.id, Resident.is_archived.is_(False))) or 0
    if values.get("capacity", room.capacity) < occupant_count:
        raise HTTPException(status_code=409, detail=f"Xonada {occupant_count} nafar yashovchi bor. Sig‘imni kamaytirib bo‘lmaydi.")
    for key, value in values.items():
        setattr(room, key, value.strip() if key in {"number", "notes"} and isinstance(value, str) else value)
    audit(db, actor, "ROOM_UPDATED", "Room", room.id, {"changed_fields": sorted(values)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bu xona raqami mavjud.") from None
    db.refresh(room)
    return room_out(db, room)


@router.delete("/rooms/{room_id}", status_code=204)
def archive_room(room_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> Response:
    room = db.get(Room, room_id)
    if not room or not room.is_active:
        raise HTTPException(status_code=404, detail="Xona topilmadi.")
    occupants = db.scalar(select(func.count(Resident.id)).where(Resident.room_id == room.id, Resident.is_archived.is_(False))) or 0
    if occupants:
        raise HTTPException(status_code=409, detail="Yashovchilari bor xonani arxivlashdan oldin ularni boshqa xonaga o‘tkazing.")
    room.is_active = False
    audit(db, actor, "ROOM_ARCHIVED", "Room", room.id, {"number": room.number})
    db.commit()
    return Response(status_code=204)


@router.get("/residents", response_model=PageInfo)
def list_residents(
    q: str = "", room_id: UUID | None = None, payment_status: str = "all", archived: bool = False,
    sort: str = "last_name", direction: Literal["asc", "desc"] = "asc",
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
) -> PageInfo:
    query = select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(archived))
    if room_id:
        query = query.where(Resident.room_id == room_id)
    if q.strip():
        term = f"%{q.strip()}%"
        query = query.outerjoin(Room, Resident.room_id == Room.id).where(
            or_(Resident.first_name.ilike(term), Resident.last_name.ilike(term), Resident.phone.ilike(term), Resident.telegram_username.ilike(term), Room.number.ilike(term))
        )
    order_col = {"first_name": Resident.first_name, "created_at": Resident.created_at}.get(sort, Resident.last_name)
    query = query.order_by(order_col.desc() if direction == "desc" else order_col.asc())
    records = db.scalars(query).unique().all()
    items = [resident_out(db, resident) for resident in records]
    if payment_status != "all":
        items = [item for item in items if item.billing_status == payment_status.upper()]
    total = len(items)
    return page_result(items[skip:skip + limit], total, skip, limit)


@router.post("/residents", response_model=ResidentOut, status_code=201)
def create_resident(payload: ResidentCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> ResidentOut:
    verify_room_capacity(db, payload.room_id)
    resident = Resident(
        first_name=payload.first_name.strip(), last_name=payload.last_name.strip(),
        phone=payload.phone.strip() if payload.phone else None,
        telegram_username=payload.telegram_username.strip().removeprefix("@") if payload.telegram_username else None,
        room_id=payload.room_id, check_in_date=payload.check_in_date,
        payment_period_days=payload.payment_period_days, agreed_price=payload.agreed_price,
        notes=payload.notes.strip(),
    )
    db.add(resident)
    db.flush()
    start = payload.billing_start or ((payload.check_in_date or today_local()) if payload.payment_period_days and payload.agreed_price else None)
    end = payload.billing_end
    days = payload.payment_period_days
    if start and days and not end:
        end = start + timedelta(days=days)
    if start and end:
        if not days:
            days = (end - start).days
            resident.payment_period_days = days
        if resident.agreed_price is None:
            raise HTTPException(status_code=422, detail="To‘lov davrini belgilash uchun kelishilgan narxni kiriting.")
        create_initial_period(db, resident, start, end, actor)
    audit(db, actor, "RESIDENT_CREATED", "Resident", resident.id, {"name": f"{resident.first_name} {resident.last_name}"})
    notify(db, "Yangi yashovchi", f"{resident.first_name} {resident.last_name} ro‘yxatga qo‘shildi.", "RESIDENT", resident.id)
    db.commit()
    db.refresh(resident)
    return resident_out(db, resident)


@router.get("/residents/{resident_id}", response_model=ResidentDetail)
def get_resident(resident_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> ResidentDetail:
    resident = db.scalar(select(Resident).options(joinedload(Resident.room)).where(Resident.id == resident_id))
    if not resident:
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    return resident_detail(db, resident)


@router.patch("/residents/{resident_id}", response_model=ResidentOut)
def update_resident(resident_id: UUID, payload: ResidentUpdate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> ResidentOut:
    resident = db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    values = payload.model_dump(exclude_unset=True)
    billing_keys = {"billing_start", "billing_end", "payment_period_days", "agreed_price"}
    if billing_keys.intersection(values) and actor.role != "OPERATOR" and not settings.admins_can_adjust_billing:
        raise HTTPException(status_code=403, detail="To‘lov davrini faqat operator o‘zgartira oladi.")
    next_room = values.get("room_id", resident.room_id)
    if "room_id" in values:
        verify_room_capacity(db, next_room, resident.id)
    old_billing = current_period(db, resident.id)
    old_start = old_billing.start_date if old_billing else None
    old_end = old_billing.end_date if old_billing else None
    old_days = resident.payment_period_days
    for key, value in values.items():
        if key in {"first_name", "last_name", "notes"} and isinstance(value, str):
            value = value.strip()
        if key == "phone" and isinstance(value, str):
            value = value.strip() or None
        if key == "telegram_username" and isinstance(value, str):
            value = value.strip().removeprefix("@") or None
        setattr(resident, key, value)
    billing_changed = bool(billing_keys.intersection(values))
    if billing_changed:
        start = values.get("billing_start", old_start)
        days = values.get("payment_period_days", old_days)
        if start is None and old_billing is None and days and resident.agreed_price and resident.agreed_price > 0:
            start = resident.check_in_date or today_local()
        if "billing_end" in values:
            end = values["billing_end"]
        elif "billing_start" in values or "payment_period_days" in values:
            end = start + timedelta(days=days) if start is not None and days else old_end
        else:
            end = old_end
        if start is not None and end is not None:
            days = days or (end - start).days
            set_period_dates(db, resident, actor, start, end, days)
        elif old_billing:
            raise HTTPException(status_code=409, detail="To‘lov qaydi bor davrni o‘chirib bo‘lmaydi. Yangi sanalarni belgilang.")
        if "agreed_price" in values and old_billing and resident.agreed_price is not None:
            old_billing.charge_amount = resident.agreed_price
    audit(db, actor, "RESIDENT_UPDATED", "Resident", resident.id, {"changed_fields": sorted(values)})
    db.commit()
    db.refresh(resident)
    return resident_out(db, resident)


@router.post("/residents/{resident_id}/archive", response_model=ResidentOut)
def archive_resident(resident_id: UUID, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> ResidentOut:
    resident = db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    if not resident.is_archived:
        resident.is_archived = True
        resident.archived_at = datetime.now(UTC)
        audit(db, actor, "RESIDENT_ARCHIVED", "Resident", resident.id)
        db.commit()
    return resident_out(db, resident)


@router.post("/residents/{resident_id}/restore", response_model=ResidentOut)
def restore_resident(resident_id: UUID, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> ResidentOut:
    resident = db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    verify_room_capacity(db, resident.room_id, resident.id)
    resident.is_archived = False
    resident.archived_at = None
    audit(db, actor, "RESIDENT_RESTORED", "Resident", resident.id)
    db.commit()
    return resident_out(db, resident)


@router.post("/residents/{resident_id}/extend", response_model=BillingPeriodOut)
def extend_resident(resident_id: UUID, payload: ExtendRequest, db: Session = Depends(get_db), actor: User = Depends(require_billing_permission)) -> BillingPeriodOut:
    resident = db.get(Resident, resident_id)
    if not resident:
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    period = extend_period(db, resident, actor, payload.days, payload.end_date, payload.reason)
    notify(db, "Yashash muddati uzaytirildi", f"{resident.first_name} {resident.last_name} uchun muddat yangilandi. To‘lov alohida qayd etiladi.", "BILLING", resident.id)
    db.commit()
    db.refresh(period)
    return BillingPeriodOut(**{
        "id": period.id, "start_date": period.start_date, "end_date": period.end_date,
        "period_days": period.period_days, "charge_amount": period.charge_amount,
        "paid_amount": period_paid(db, period.id), "balance": period_balance(db, period), "status": period.status,
    })


@router.get("/residents/{resident_id}/payments", response_model=list[PaymentOut])
def resident_payments(resident_id: UUID, db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[PaymentOut]:
    if not db.get(Resident, resident_id):
        raise HTTPException(status_code=404, detail="Yashovchi topilmadi.")
    rows = db.scalars(select(Payment).options(joinedload(Payment.resident)).where(Payment.resident_id == resident_id).order_by(Payment.payment_date.desc(), Payment.created_at.desc())).all()
    return [payment_out(db, row) for row in rows]


@router.get("/payments", response_model=PageInfo)
def list_payments(
    resident_id: UUID | None = None, date_from: date | None = None, date_to: date | None = None,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
) -> PageInfo:
    query = select(Payment).options(joinedload(Payment.resident)).order_by(Payment.payment_date.desc(), Payment.created_at.desc())
    if resident_id:
        query = query.where(Payment.resident_id == resident_id)
    if date_from:
        query = query.where(Payment.payment_date >= date_from)
    if date_to:
        query = query.where(Payment.payment_date <= date_to)
    rows = db.scalars(query).unique().all()
    total = len(rows)
    return page_result([payment_out(db, item) for item in rows[skip:skip + limit]], total, skip, limit)


@router.post("/payments", response_model=PaymentOut, status_code=201)
def create_payment(payload: PaymentCreate, db: Session = Depends(get_db), actor: User = Depends(get_current_user)) -> PaymentOut:
    if payload.payment_date > today_local():
        raise HTTPException(status_code=422, detail="To‘lov sanasi kelajakda bo‘lishi mumkin emas.")
    resident = db.get(Resident, payload.resident_id)
    if not resident or resident.is_archived:
        raise HTTPException(status_code=404, detail="Faol yashovchi topilmadi.")
    period_id = payload.billing_period_id
    period = db.scalar(select(BillingPeriod).where(BillingPeriod.id == period_id).with_for_update()) if period_id else current_period(db, resident.id)
    if not period or period.resident_id != resident.id or period.status != "OPEN":
        raise HTTPException(status_code=409, detail="Yashovchi uchun ochiq to‘lov davri topilmadi.")
    balance = period_balance(db, period)
    if balance <= 0:
        raise HTTPException(status_code=409, detail="Bu davr uchun qarzdorlik qolmagan.")
    if payload.amount > balance:
        raise HTTPException(status_code=422, detail="To‘lov summasi davr qoldig‘idan oshmasligi kerak.")
    payment = Payment(
        resident_id=resident.id,
        billing_period_id=period.id,
        amount=payload.amount,
        payment_date=payload.payment_date,
        method=payload.method,
        covered_start=period.start_date,
        covered_end=period.end_date,
        notes=payload.notes.strip(),
        recorded_by=actor.id,
    )
    db.add(payment)
    db.flush()
    audit(db, actor, "PAYMENT_RECORDED", "Payment", payment.id, {"resident_id": str(resident.id), "amount": str(payment.amount), "method": payment.method})
    notify(db, "Yangi to‘lov qayd etildi", f"{resident.first_name} {resident.last_name} uchun {payment.amount} so‘m qabul qilindi.", "PAYMENT", resident.id)
    mark_paid_and_advance(db, period, actor)
    db.commit()
    db.refresh(payment)
    return payment_out(db, payment)


@router.post("/payments/{payment_id}/adjustments", response_model=PaymentAdjustmentOut, status_code=201)
def adjust_payment(payment_id: UUID, payload: PaymentAdjustmentCreate, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> PaymentAdjustmentOut:
    payment = db.scalar(select(Payment).options(joinedload(Payment.adjustments)).where(Payment.id == payment_id).with_for_update())
    if not payment:
        raise HTTPException(status_code=404, detail="To‘lov topilmadi.")
    current_net = payment.amount + sum((item.amount_delta for item in payment.adjustments), Decimal("0"))
    if current_net + payload.amount_delta < 0:
        raise HTTPException(status_code=422, detail="Tuzatish to‘lov qoldig‘ini manfiy qilmasligi kerak.")
    adjustment = PaymentAdjustment(payment_id=payment.id, amount_delta=payload.amount_delta, reason=payload.reason.strip(), adjusted_by=actor.id)
    db.add(adjustment)
    db.flush()
    period = db.get(BillingPeriod, payment.billing_period_id) if payment.billing_period_id else None
    if period:
        paid = period_paid(db, period.id)
        if paid < period.charge_amount:
            period.status = "OPEN"
            newer_open = db.scalars(select(BillingPeriod).where(BillingPeriod.resident_id == period.resident_id, BillingPeriod.status == "OPEN", BillingPeriod.start_date > period.start_date)).all()
            for later in newer_open:
                later.status = "CLOSED"
        else:
            period.status = "PAID"
            mark_paid_and_advance(db, period, actor)
    audit(db, actor, "PAYMENT_ADJUSTED", "Payment", payment.id, {"adjustment_id": str(adjustment.id), "amount_delta": str(payload.amount_delta), "reason": payload.reason.strip()})
    db.commit()
    db.refresh(adjustment)
    return adjustment


@router.get("/payments/{payment_id}/adjustments", response_model=list[PaymentAdjustmentOut])
def list_adjustments(payment_id: UUID, db: Session = Depends(get_db), _: User = Depends(require_operator)) -> list[PaymentAdjustment]:
    if not db.get(Payment, payment_id):
        raise HTTPException(status_code=404, detail="To‘lov topilmadi.")
    return db.scalars(select(PaymentAdjustment).where(PaymentAdjustment.payment_id == payment_id).order_by(PaymentAdjustment.created_at)).all()


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> DashboardOut:
    today = today_local()
    residents = db.scalars(select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(False))).all()
    active_rooms = db.scalars(select(Room).where(Room.is_active.is_(True)).order_by(Room.number)).all()
    items = [resident_out(db, item, today) for item in residents]
    capacity = sum(room.capacity for room in active_rooms)
    assigned = sum(1 for item in residents if item.room_id is not None)
    room_stats = [room_out(db, room) for room in active_rooms]
    month_start = today.replace(day=1)
    first_trend_index = month_start.year * 12 + month_start.month - 1 - 5
    first_trend_month = date(first_trend_index // 12, first_trend_index % 12 + 1, 1)
    payments = db.scalars(select(Payment).options(joinedload(Payment.resident)).where(Payment.payment_date >= first_trend_month).order_by(Payment.payment_date)).all()
    month_income = sum((net_payment(db, item) for item in payments if item.payment_date >= month_start), Decimal("0"))
    open_periods = db.scalars(
        select(BillingPeriod).join(Resident, BillingPeriod.resident_id == Resident.id).where(
            BillingPeriod.status == "OPEN", Resident.is_archived.is_(False)
        )
    ).all()
    expected = sum((item.charge_amount for item in open_periods), Decimal("0"))
    outstanding = sum((period_balance(db, item) for item in open_periods), Decimal("0"))
    trend = []
    for offset in range(5, -1, -1):
        month_index = month_start.year * 12 + month_start.month - 1 - offset
        month = date(month_index // 12, month_index % 12 + 1, 1)
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        amount = sum((net_payment(db, item) for item in payments if month <= item.payment_date < next_month), Decimal("0"))
        trend.append({"month": f"{UZ_MONTHS[month.month - 1]} {month.year}", "amount": amount})
    recent = db.scalars(select(Payment).options(joinedload(Payment.resident)).order_by(Payment.payment_date.desc(), Payment.created_at.desc()).limit(6)).all()
    new_residents = db.scalars(select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(False)).order_by(Resident.created_at.desc()).limit(5)).all()
    return DashboardOut(
        residents=len(residents), rooms=len(active_rooms), occupancy_rate=round(assigned / capacity * 100, 1) if capacity else 0,
        available_beds=max(0, capacity - assigned), due_today=sum(x.billing_status == "DUE_TODAY" for x in items),
        due_soon=sum(x.billing_status == "DUE_SOON" for x in items), overdue=sum(x.billing_status == "OVERDUE" for x in items),
        actual_revenue=month_income, expected_payments=expected, outstanding_debt=outstanding,
        revenue_trend=trend,
        occupancy_by_room=[{"room": item.number, "occupied": item.resident_count, "available": item.available_beds} for item in room_stats],
        recent_payments=[payment_out(db, item) for item in recent],
        recent_residents=[resident_out(db, item, today) for item in new_residents],
    )


@router.get("/notifications", response_model=list[NotificationOut])
def list_notifications(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> list[NotificationOut]:
    today = today_local()
    residents = db.scalars(select(Resident).options(joinedload(Resident.room)).where(Resident.is_archived.is_(False))).all()
    now = datetime.now(UTC)
    created = False
    for resident in residents:
        state = resident_out(db, resident, today)
        if state.billing_status not in {"DUE_TODAY", "DUE_SOON", "OVERDUE"}:
            continue
        title = {"DUE_TODAY": "To‘lov bugun", "DUE_SOON": "To‘lov muddati yaqin", "OVERDUE": "To‘lov muddati o‘tgan"}[state.billing_status]
        delta = state.overdue_days if state.billing_status == "OVERDUE" else ((state.billing_end - today).days if state.billing_end else 0)
        msg = f"{state.first_name} {state.last_name} · {state.room_number or 'Xona yo‘q'}-xona · {state.balance} so‘m"
        if state.billing_status == "OVERDUE":
            msg += f" · {delta} kun kechikdi"
        nid = uuid5(NAMESPACE_URL, f"dormflow:due:{today.isoformat()}:{resident.id}")
        if not db.get(Notification, nid):
            db.add(Notification(id=nid, title=title, message=msg, kind=state.billing_status, entity_id=resident.id, read_at=None, created_at=now))
            created = True
    if created:
        db.commit()
    stored = db.scalars(select(Notification).where(Notification.read_at.is_(None)).order_by(Notification.created_at.desc()).limit(50)).all()
    return [notification_out(item) for item in stored]


@router.post("/notifications/read-all", status_code=204)
def mark_notifications_read(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> Response:
    rows = db.scalars(select(Notification).where(Notification.read_at.is_(None))).all()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
    db.commit()
    return Response(status_code=204)


@router.get("/settings", response_model=SystemSettingsOut)
def get_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)) -> SystemSettingsOut:
    record = db.get(SystemSetting, "general")
    value = record.value if record else {"dorm_name": "DormFlow", "default_period_days": 30, "currency": "UZS"}
    return SystemSettingsOut(**value, updated_at=record.updated_at if record else None, billing_change_allowed=settings.admins_can_adjust_billing)


@router.put("/settings", response_model=SystemSettingsOut)
def update_settings(payload: SystemSettingsIn, db: Session = Depends(get_db), actor: User = Depends(require_operator)) -> SystemSettingsOut:
    record = db.get(SystemSetting, "general")
    if not record:
        record = SystemSetting(key="general", value=payload.model_dump(), updated_by=actor.id)
        db.add(record)
    else:
        record.value = payload.model_dump()
        record.updated_by = actor.id
    audit(db, actor, "SETTINGS_UPDATED", "SystemSetting", details={"dorm_name": payload.dorm_name})
    db.commit()
    db.refresh(record)
    return SystemSettingsOut(**record.value, updated_at=record.updated_at, billing_change_allowed=settings.admins_can_adjust_billing)


@router.get("/audit", response_model=PageInfo)
def list_audit(
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(require_operator),
) -> PageInfo:
    total = db.scalar(select(func.count(AuditEvent.id))) or 0
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.created_at.desc()).offset(skip).limit(limit)).all()
    return page_result([audit_out(db, item) for item in rows], total, skip, limit)


def xlsx_file(headers: list[str], rows: list[list[object]], sheet_name: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = sheet_name[:31]
    sheet.append(headers)
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="255744")
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append([str(value) if isinstance(value, (date, datetime)) else value for value in row])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column in sheet.columns:
        width = min(42, max(12, max((len(str(cell.value or "")) for cell in column), default=10) + 2))
        sheet.column_dimensions[column[0].column_letter].width = width
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


def pdf_file(headers: list[str], rows: list[list[object]], title: str) -> bytes:
    out = io.BytesIO()
    document = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=26, rightMargin=26, topMargin=28, bottomMargin=28)
    styles = getSampleStyleSheet()
    font_paths = ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    try:
        font_path = next(path for path in font_paths if exists(path))
        pdfmetrics.registerFont(TTFont("DormFlow", font_path))
        styles["Normal"].fontName = "DormFlow"
        styles["Title"].fontName = "DormFlow"
    except Exception:
        pass
    content = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    data = [[str(item) for item in headers]]
    data.extend([[str(item) for item in row] for row in rows[:2500]])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#255744")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, -1), "DormFlow" if "DormFlow" in pdfmetrics.getRegisteredFontNames() else "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDE4DD")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F4F7F3")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    content.append(table)
    document.build(content)
    return out.getvalue()


@router.get("/reports/{kind}.{file_format}")
def export_report(
    kind: Literal["residents", "rooms", "payments", "debts", "overdue", "revenue"],
    file_format: Literal["csv", "xlsx", "pdf"],
    date_from: date | None = None, date_to: date | None = None,
    interval: Literal["day", "week", "month"] = "month",
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
) -> Response:
    if date_from and date_to and date_to < date_from:
        raise HTTPException(status_code=422, detail="Yakuniy sana boshlang‘ich sanadan oldin bo‘lishi mumkin emas.")
    headers, rows = get_report_rows(db, kind, date_from, date_to, interval)
    name = f"dormflow-{kind}-{today_local().isoformat()}"
    if file_format == "csv":
        text_stream = io.StringIO(newline="")
        writer = csv.writer(text_stream)
        writer.writerow(headers)
        writer.writerows(rows)
        content = ("\ufeff" + text_stream.getvalue()).encode("utf-8")
        return Response(content, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    if file_format == "xlsx":
        sheet_names = {"residents": "Yashovchilar", "rooms": "Xonalar", "payments": "To‘lovlar", "debts": "Qarzdorlik", "overdue": "Muddati o‘tgan", "revenue": "Tushum"}
        content = xlsx_file(headers, rows, sheet_names[kind])
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        pdf_titles = {"residents": "Yashovchilar", "rooms": "Xonalar bandligi", "payments": "To‘lovlar tarixi", "debts": "Qarzdorliklar", "overdue": "Muddati o‘tgan to‘lovlar", "revenue": "Haqiqiy tushum"}
        content = pdf_file(headers, rows, f"DormFlow — {pdf_titles[kind]}")
        media = "application/pdf"
    extension = "xlsx" if file_format == "xlsx" else "pdf"
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{name}.{extension}"'})
