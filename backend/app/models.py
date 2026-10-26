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
        UniqueConstraint("dormitory_id", "number", name="uq_room_dorm_number"),
        CheckConstraint("capacity > 0", name="ck_room_capacity_positive"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    dormitory_id: Mapped[UUID] = mapped_column(ForeignKey("dormitories.id", ondelete="RESTRICT"), index=True)
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
    residence_periods: Mapped[list[ResidencePeriod]] = relationship(back_populates="resident", cascade="all, delete-orphan")
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
    old_charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    new_start_date: Mapped[date] = mapped_column(Date)
    new_end_date: Mapped[date] = mapped_column(Date)
    new_charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    change_type: Mapped[str] = mapped_column(String(32))
    reason: Mapped[str] = mapped_column(Text, default="")
    changed_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        CheckConstraint("method IN ('CASH', 'BANK', 'CLICK', 'PAYME', 'OTHER')", name="ck_payment_method"),
        UniqueConstraint("recorded_by", "idempotency_key", name="uq_payment_actor_idempotency"),
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
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resident: Mapped[Resident] = relationship(back_populates="payments")
    billing_period: Mapped[BillingPeriod | None] = relationship(back_populates="payments")
    adjustments: Mapped[list[PaymentAdjustment]] = relationship(back_populates="payment", cascade="all, delete-orphan")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        CheckConstraint("method IN ('CASH', 'BANK', 'CLICK', 'PAYME', 'OTHER')", name="ck_expense_method"),
        CheckConstraint("category IN ('UTILITIES', 'REPAIR', 'SUPPLIES', 'FOOD', 'SALARY', 'OTHER')", name="ck_expense_category"),
        UniqueConstraint("recorded_by", "idempotency_key", name="uq_expense_actor_idempotency"),
        Index("ix_expense_date_voided", "expense_date", "voided_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(16))
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    method: Mapped[str] = mapped_column(String(12))
    reference: Mapped[str] = mapped_column(String(120), default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recorded_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    void_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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


class Dormitory(Base):
    __tablename__ = "dormitories"
    __table_args__ = (UniqueConstraint("name", name="uq_dormitory_name"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str] = mapped_column(String(500), default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdmissionCampaign(Base):
    __tablename__ = "admission_campaigns"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'PAUSED', 'CLOSED')", name="ck_campaign_status"),
        Index("ix_admission_campaign_dorm_status", "dormitory_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160))
    dormitory_id: Mapped[UUID] = mapped_column(ForeignKey("dormitories.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    custom_fields: Mapped[list] = mapped_column(JSON, default=list)
    document_types: Mapped[list] = mapped_column(JSON, default=list)
    consent_version: Mapped[str] = mapped_column(String(40), default="2026-01")
    consent_text: Mapped[str] = mapped_column(Text, default="Shaxsiy ma’lumotlarimni ko‘rsatilgan maqsadlarda qayta ishlashga roziman.")
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AdmissionInvitation(Base):
    __tablename__ = "admission_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_invitation_token_hash"),
        CheckConstraint("max_submissions > 0", name="ck_invitation_max_submissions"),
        CheckConstraint("submission_count >= 0", name="ck_invitation_submission_count"),
        Index("ix_invitation_campaign_status", "campaign_id", "revoked_at", "paused_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64))
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("admission_campaigns.id", ondelete="RESTRICT"), index=True)
    dormitory_id: Mapped[UUID] = mapped_column(ForeignKey("dormitories.id", ondelete="RESTRICT"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_submissions: Mapped[int] = mapped_column(Integer)
    submission_count: Mapped[int] = mapped_column(Integer, default=0)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class StudentApplication(Base):
    __tablename__ = "student_applications"
    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'IN_REVIEW', 'NEEDS_INFO', 'APPROVED', 'REJECTED', 'CANCELLED', 'ARCHIVED')", name="ck_application_status"),
        Index("ix_application_queue", "status", "created_at"),
        Index("ix_application_campaign_dorm", "campaign_id", "dormitory_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    reference: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    invitation_id: Mapped[UUID] = mapped_column(ForeignKey("admission_invitations.id", ondelete="RESTRICT"), index=True)
    exchange_key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    campaign_id: Mapped[UUID] = mapped_column(ForeignKey("admission_campaigns.id", ondelete="RESTRICT"), index=True)
    dormitory_id: Mapped[UUID] = mapped_column(ForeignKey("dormitories.id", ondelete="RESTRICT"), index=True)
    resident_id: Mapped[UUID | None] = mapped_column(ForeignKey("residents.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    first_name_latin: Mapped[str] = mapped_column(String(80), default="")
    last_name_latin: Mapped[str] = mapped_column(String(100), default="")
    middle_name_latin: Mapped[str] = mapped_column(String(100), default="")
    first_name_cyrillic: Mapped[str] = mapped_column(String(80), default="")
    last_name_cyrillic: Mapped[str] = mapped_column(String(100), default="")
    middle_name_cyrillic: Mapped[str] = mapped_column(String(100), default="")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    nationality: Mapped[str] = mapped_column(String(100), default="")
    gender: Mapped[str | None] = mapped_column(String(24), nullable=True)
    phone: Mapped[str] = mapped_column(String(40), default="")
    email: Mapped[str] = mapped_column(String(320), default="")
    address: Mapped[str] = mapped_column(String(500), default="")
    emergency_name: Mapped[str] = mapped_column(String(160), default="")
    emergency_phone: Mapped[str] = mapped_column(String(40), default="")
    institution: Mapped[str] = mapped_column(String(200), default="")
    faculty: Mapped[str] = mapped_column(String(160), default="")
    course: Mapped[str] = mapped_column(String(40), default="")
    study_group: Mapped[str] = mapped_column(String(80), default="")
    study_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    study_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_move_in: Mapped[date | None] = mapped_column(Date, nullable=True)
    requested_move_out: Mapped[date | None] = mapped_column(Date, nullable=True)
    preferences: Mapped[str] = mapped_column(Text, default="")
    additional_data: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_fields: Mapped[list] = mapped_column(JSON, default=list)
    consent_version: Mapped[str] = mapped_column(String(40), default="")
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tracking_code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    assigned_to: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    review_reason: Mapped[str] = mapped_column(Text, default="")
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    approved_room_id: Mapped[UUID | None] = mapped_column(ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    approved_move_in: Mapped[date | None] = mapped_column(Date, nullable=True)
    approved_move_out: Mapped[date | None] = mapped_column(Date, nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    files: Mapped[list[ApplicationFile]] = relationship(back_populates="application", cascade="all, delete-orphan")
    events: Mapped[list[ApplicationStatusEvent]] = relationship(back_populates="application", cascade="all, delete-orphan", order_by="ApplicationStatusEvent.created_at")


class ApplicationStatusEvent(Base):
    __tablename__ = "application_status_events"
    __table_args__ = (Index("ix_application_event_created", "application_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("student_applications.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    from_status: Mapped[str] = mapped_column(String(16), default="")
    to_status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[StudentApplication] = relationship(back_populates="events")


class ApplicationAccessSession(Base):
    __tablename__ = "application_access_sessions"
    __table_args__ = (Index("ix_application_session_expiry", "expires_at"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("student_applications.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApplicationFile(Base):
    __tablename__ = "application_files"
    __table_args__ = (
        CheckConstraint("kind IN ('PHOTO', 'DOCUMENT')", name="ck_application_file_kind"),
        Index("ix_application_file_retention", "delete_after"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("student_applications.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(12))
    document_type: Mapped[str] = mapped_column(String(80), default="")
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    original_name: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    scan_status: Mapped[str] = mapped_column(String(20), default="NOT_CONFIGURED")
    ocr_status: Mapped[str] = mapped_column(String(20), default="NOT_CONFIGURED")
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    delete_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    application: Mapped[StudentApplication] = relationship(back_populates="files")


class ResidencePeriod(Base):
    __tablename__ = "residence_periods"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date > start_date", name="ck_residence_dates_ordered"),
        CheckConstraint("status IN ('PLANNED', 'ACTIVE', 'ENDED')", name="ck_residence_status"),
        Index("ix_residence_room_dates", "room_id", "start_date", "end_date"),
        Index("ix_residence_resident_dates", "resident_id", "start_date"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    resident_id: Mapped[UUID] = mapped_column(ForeignKey("residents.id", ondelete="CASCADE"), index=True)
    room_id: Mapped[UUID] = mapped_column(ForeignKey("rooms.id", ondelete="RESTRICT"), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    created_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resident: Mapped[Resident] = relationship(back_populates="residence_periods")


class PublicRateLimit(Base):
    __tablename__ = "public_rate_limits"

    bucket_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hits: Mapped[int] = mapped_column(Integer, default=1)
