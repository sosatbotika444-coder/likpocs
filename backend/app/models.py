from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, JSON, Numeric, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('OPERATOR', 'ADMIN')", name="ck_user_role"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="ADMIN")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        UniqueConstraint("number", name="uq_room_number"),
        CheckConstraint("capacity > 0", name="ck_room_capacity_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    number: Mapped[str] = mapped_column(String(32), index=True)
    floor: Mapped[int] = mapped_column(Integer, default=1)
    capacity: Mapped[int] = mapped_column(Integer)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    residents: Mapped[list[Resident]] = relationship(back_populates="room")


class Resident(Base):
    __tablename__ = "residents"
    __table_args__ = (
        CheckConstraint("payment_period_days IS NULL OR payment_period_days > 0", name="ck_resident_period_positive"),
        CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="ck_resident_price_nonnegative"),
        Index("ix_resident_name", "last_name", "first_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    first_name: Mapped[str] = mapped_column(String(80))
    last_name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    room_id: Mapped[UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), nullable=True, index=True)
    check_in_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    payment_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agreed_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    room: Mapped[Room | None] = relationship(back_populates="residents")
    billing_periods: Mapped[list[BillingPeriod]] = relationship(back_populates="resident", cascade="all, delete-orphan")
    payments: Mapped[list[Payment]] = relationship(back_populates="resident")


class BillingPeriod(Base):
    __tablename__ = "billing_periods"
    __table_args__ = (
        CheckConstraint("end_date > start_date", name="ck_billing_dates_ordered"),
        CheckConstraint("period_days > 0", name="ck_billing_period_positive"),
        CheckConstraint("charge_amount >= 0", name="ck_billing_charge_nonnegative"),
        CheckConstraint("status IN ('OPEN', 'PAID', 'CLOSED')", name="ck_billing_status"),
        Index("ix_billing_resident_status", "resident_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    resident_id: Mapped[UUID] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    period_days: Mapped[int] = mapped_column(Integer)
    charge_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(12), default="OPEN")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resident: Mapped[Resident] = relationship(back_populates="billing_periods")
    payments: Mapped[list[Payment]] = relationship(back_populates="billing_period")


class BillingChange(Base):
    __tablename__ = "billing_changes"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    resident_id: Mapped[UUID] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), index=True)
    billing_period_id: Mapped[UUID] = mapped_column(ForeignKey("billing_periods.id", ondelete="CASCADE"), index=True)
    old_start_date: Mapped[date] = mapped_column(Date)
    old_end_date: Mapped[date] = mapped_column(Date)
    new_start_date: Mapped[date] = mapped_column(Date)
    new_end_date: Mapped[date] = mapped_column(Date)
    change_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint("method IN ('CASH', 'BANK', 'CLICK', 'PAYME', 'OTHER')", name="ck_payment_method"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    resident_id: Mapped[UUID] = mapped_column(ForeignKey("residents.id", ondelete="RESTRICT"), index=True)
    billing_period_id: Mapped[UUID | None] = mapped_column(ForeignKey("billing_periods.id", ondelete="SET NULL"), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    method: Mapped[str] = mapped_column(String(12))
    covered_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    covered_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resident: Mapped[Resident] = relationship(back_populates="payments")
    billing_period: Mapped[BillingPeriod | None] = relationship(back_populates="payments")
    adjustments: Mapped[list[PaymentAdjustment]] = relationship(back_populates="payment", cascade="all, delete-orphan")


class PaymentAdjustment(Base):
    __tablename__ = "payment_adjustments"
    __table_args__ = (
        CheckConstraint("amount_delta != 0", name="ck_adjustment_nonzero"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    payment_id: Mapped[UUID] = mapped_column(ForeignKey("payments.id", ondelete="RESTRICT"), index=True)
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(Text)
    adjusted_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    payment: Mapped[Payment] = relationship(back_populates="adjustments")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default="INFO")
    entity_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
