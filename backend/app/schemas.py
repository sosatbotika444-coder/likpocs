from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    full_name: str
    role: Literal["OPERATOR", "ADMIN"]
    is_active: bool
    is_primary: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)
    role: Literal["ADMIN"] = "ADMIN"


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=160)
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


class RoomBase(BaseModel):
    number: str = Field(min_length=1, max_length=32)
    dormitory_id: UUID | None = None
    floor: int = Field(default=1, ge=0, le=300)
    capacity: int = Field(ge=1, le=500)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str = Field(default="", max_length=2000)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=32)
    dormitory_id: UUID | None = None
    floor: int | None = Field(default=None, ge=0, le=300)
    capacity: int | None = Field(default=None, ge=1, le=500)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)


class RoomOut(ORMModel):
    id: UUID
    dormitory_id: UUID
    number: str
    floor: int
    capacity: int
    price: Decimal | None
    notes: str
    is_active: bool
    resident_count: int = 0
    available_beds: int = 0


class ResidentFields(BaseModel):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    telegram_username: str | None = Field(default=None, max_length=64)
    room_id: UUID | None = None
    check_in_date: date | None = None
    billing_start: date | None = None
    billing_end: date | None = None
    payment_period_days: int | None = Field(default=None, gt=0, le=365000)
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def validate_billing_range(self):
        if self.billing_end and not self.billing_start:
            raise ValueError("Davr tugash sanasini berish uchun boshlanish sanasini ham kiriting.")
        if self.billing_start and self.billing_end and self.billing_end <= self.billing_start:
            raise ValueError("Davr tugashi boshlanishidan keyin bo‘lishi kerak.")
        return self


class ResidentCreate(ResidentFields):
    pass


class ResidentUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=40)
    telegram_username: str | None = Field(default=None, max_length=64)
    room_id: UUID | None = None
    check_in_date: date | None = None
    billing_start: date | None = None
    billing_end: date | None = None
    payment_period_days: int | None = Field(default=None, gt=0, le=365000)
    agreed_price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_billing_range(self):
        if self.billing_start and self.billing_end and self.billing_end <= self.billing_start:
            raise ValueError("Davr tugashi boshlanishidan keyin bo‘lishi kerak.")
        return self


class BillingChangeOut(ORMModel):
    id: UUID
    billing_period_id: UUID
    old_start_date: date
    old_end_date: date
    old_charge_amount: Decimal | None = None
    new_start_date: date
    new_end_date: date
    new_charge_amount: Decimal | None = None
    change_type: str
    reason: str
    changed_by: UUID
    created_at: datetime


class BillingPeriodOut(ORMModel):
    id: UUID
    start_date: date
    end_date: date
    period_days: int
    charge_amount: Decimal
    paid_amount: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    status: str


class ResidentOut(ORMModel):
    id: UUID
    first_name: str
    last_name: str
    phone: str | None
    telegram_username: str | None
    room_id: UUID | None
    room_number: str | None = None
    check_in_date: date | None
    departed_on: date | None = None
    payment_period_days: int | None
    agreed_price: Decimal | None
    notes: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    billing_start: date | None = None
    billing_end: date | None = None
    billing_period_id: UUID | None = None
    billing_status: str = "NOT_CONFIGURED"
    paid_amount: Decimal = Decimal("0")
    balance: Decimal = Decimal("0")
    overdue_days: int = 0


class ResidentDetail(ResidentOut):
    billing_history: list[BillingPeriodOut] = Field(default_factory=list)
    changes: list[BillingChangeOut] = Field(default_factory=list)


class ExtendRequest(BaseModel):
    days: int | None = Field(default=None, gt=0, le=365000)
    end_date: date | None = None
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def require_one_method(self):
        if self.days is None and self.end_date is None:
            raise ValueError("Kunlar soni yoki yangi tugash sanasini kiriting.")
        return self


class CheckoutRequest(BaseModel):
    checkout_date: date
    reason: str = Field(default="Muddatidan oldin chiqish", max_length=1000)


PaymentMethod = Literal["CASH", "BANK", "CLICK", "PAYME", "OTHER"]


class PaymentCreate(BaseModel):
    resident_id: UUID
    billing_period_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_date: date
    method: PaymentMethod
    notes: str = Field(default="", max_length=2000)


ExpenseCategory = Literal["UTILITIES", "REPAIR", "SUPPLIES", "FOOD", "SALARY", "OTHER"]


class ExpenseCreate(BaseModel):
    expense_date: date
    category: ExpenseCategory
    description: str = Field(min_length=2, max_length=500)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    method: PaymentMethod
    reference: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def normalized_description_required(self):
        if len(self.description.strip()) < 2:
            raise ValueError("Xarajat tafsilotini kamida 2 ta belgi bilan kiriting.")
        return self


class ExpenseVoid(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)

    @model_validator(mode="after")
    def normalized_reason_required(self):
        if len(self.reason.strip()) < 5:
            raise ValueError("Bekor qilish sababini kamida 5 ta belgi bilan kiriting.")
        return self


class PaymentAdjustmentCreate(BaseModel):
    amount_delta: Decimal = Field(max_digits=14, decimal_places=2)
    reason: str = Field(min_length=5, max_length=2000)

    @model_validator(mode="after")
    def nonzero_amount(self):
        if self.amount_delta == 0:
            raise ValueError("Adjustment amount must be nonzero.")
        return self


class PaymentOut(ORMModel):
    id: UUID
    resident_id: UUID
    resident_name: str = ""
    billing_period_id: UUID | None
    amount: Decimal
    net_amount: Decimal = Decimal("0")
    payment_date: date
    method: str
    covered_start: date | None
    covered_end: date | None
    notes: str
    recorded_by: UUID
    recorded_by_name: str = ""
    created_at: datetime


class ExpenseOut(ORMModel):
    id: UUID
    expense_date: date
    category: ExpenseCategory
    description: str
    amount: Decimal
    method: str
    reference: str
    recorded_by: UUID
    recorded_by_name: str = ""
    voided_at: datetime | None
    voided_by: UUID | None
    void_reason: str
    created_at: datetime


class PaymentAdjustmentOut(ORMModel):
    id: UUID
    payment_id: UUID
    amount_delta: Decimal
    reason: str
    adjusted_by: UUID
    created_at: datetime


class PageInfo(BaseModel):
    items: list
    total: int
    skip: int
    limit: int


class DashboardOut(BaseModel):
    residents: int
    rooms: int
    occupancy_rate: float
    available_beds: int
    due_today: int
    due_soon: int
    overdue: int
    actual_revenue: Decimal
    actual_expenses: Decimal
    net_cash_flow: Decimal
    expected_payments: Decimal
    outstanding_debt: Decimal
    revenue_trend: list[dict]
    occupancy_by_room: list[dict]
    recent_payments: list[PaymentOut]
    recent_residents: list[ResidentOut]


class AdmissionSummaryOut(BaseModel):
    total_applications: int
    applications_this_month: int
    pending_applications: int
    approved_applications: int
    approved_this_month: int
    rejected_applications: int
    linked_residents: int
    expected_payments: Decimal
    outstanding_debt: Decimal
    actual_revenue_this_month: Decimal
    by_status: dict[str, int]


class NotificationOut(ORMModel):
    id: UUID
    title: str
    message: str
    kind: str
    entity_id: UUID | None
    read_at: datetime | None
    created_at: datetime


class SystemSettingsIn(BaseModel):
    dorm_name: str = Field(min_length=1, max_length=160)
    default_period_days: int = Field(gt=0, le=365000)
    currency: Literal["UZS"] = "UZS"


class SystemSettingsOut(SystemSettingsIn):
    updated_at: datetime | None = None
    billing_change_allowed: bool = False


class AuditEventOut(ORMModel):
    id: UUID
    actor_id: UUID | None
    actor_name: str = ""
    action: str
    entity_type: str
    entity_id: UUID | None
    details: dict
    created_at: datetime


class DormitoryOut(ORMModel):
    id: UUID
    name: str
    address: str
    is_default: bool
    is_active: bool


class DormitoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    address: str = Field(default="", max_length=500)


class DormitoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None


class CustomFieldDefinition(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,39}$")
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["text", "date", "select", "checkbox"]
    required: bool = False
    options: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_options(self):
        options = [item.strip() for item in self.options]
        if any(not item or len(item) > 120 for item in options) or len(options) != len(set(options)):
            raise ValueError("Tanlov variantlari bosh yoki takroriy bolmasligi kerak.")
        if self.kind == "select" and not options:
            raise ValueError("Tanlov maydoni uchun kamida bitta variant kiriting.")
        self.options = options
        return self


class CampaignCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dormitory_id: UUID
    custom_fields: list[CustomFieldDefinition] = Field(default_factory=list, max_length=30)
    document_types: list[str] = Field(default_factory=lambda: ["ID", "STUDY_PROOF"], max_length=20)
    consent_version: str = Field(default="2026-01", min_length=1, max_length=40)
    consent_text: str = Field(min_length=10, max_length=2000)


class CampaignOut(ORMModel):
    id: UUID
    name: str
    dormitory_id: UUID
    status: str
    custom_fields: list[dict]
    document_types: list[str]
    consent_version: str
    consent_text: str
    created_at: datetime


class PublicCampaignOut(BaseModel):
    name: str
    custom_fields: list[dict]
    document_types: list[str]
    consent_version: str
    consent_text: str


class PublicSessionOut(BaseModel):
    csrf_token: str
    campaign: PublicCampaignOut
    application: PublicApplicationOut


class InvitationExchangeIn(BaseModel):
    token: str = Field(min_length=24, max_length=128)
    draft_key: str = Field(min_length=16, max_length=128)


class PublicInviteOut(BaseModel):
    campaign: PublicCampaignOut
    csrf_token: str


class InvitationCreate(BaseModel):
    campaign_id: UUID
    expires_at: datetime
    max_submissions: int = Field(ge=1, le=10000)


class InvitationOut(ORMModel):
    id: UUID
    campaign_id: UUID
    dormitory_id: UUID
    expires_at: datetime
    max_submissions: int
    submission_count: int
    paused_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    status: str
    link: str | None = None


class ApplicationDraftIn(BaseModel):
    first_name_latin: str = Field(default="", max_length=80)
    last_name_latin: str = Field(default="", max_length=100)
    middle_name_latin: str = Field(default="", max_length=100)
    first_name_cyrillic: str = Field(default="", max_length=80)
    last_name_cyrillic: str = Field(default="", max_length=100)
    middle_name_cyrillic: str = Field(default="", max_length=100)
    birth_date: date | None = None
    nationality: str = Field(default="", max_length=100)
    gender: Literal["FEMALE", "MALE"] | None = None
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=320)
    address: str = Field(default="", max_length=500)
    emergency_name: str = Field(default="", max_length=160)
    emergency_phone: str = Field(default="", max_length=40)
    institution: str = Field(default="", max_length=200)
    faculty: str = Field(default="", max_length=160)
    course: str = Field(default="", max_length=40)
    study_group: str = Field(default="", max_length=80)
    study_start: date | None = None
    study_end: date | None = None
    requested_move_in: date | None = None
    requested_move_out: date | None = None
    preferences: str = Field(default="", max_length=2000)
    additional_data: dict[str, str | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def ordered_dates(self):
        if self.study_start and self.study_end and self.study_end <= self.study_start:
            raise ValueError("O‘qish tugash sanasi boshlanishidan keyin bo‘lishi kerak.")
        if self.requested_move_in and self.requested_move_out and self.requested_move_out <= self.requested_move_in:
            raise ValueError("Yashash tugash sanasi boshlanishidan keyin bo‘lishi kerak.")
        return self


class ApplicationSubmitIn(BaseModel):
    consent: bool


class PublicApplicationOut(ApplicationDraftIn):
    model_config = ConfigDict(from_attributes=True)

    reference: str
    status: str
    requested_fields: list[str]
    review_reason: str
    consent_version: str


class ApplicationFileOut(ORMModel):
    id: UUID
    kind: str
    document_type: str
    original_name: str
    content_type: str
    size_bytes: int
    scan_status: str
    ocr_status: str
    uploaded_at: datetime


class ApplicationFileStaffOut(ApplicationFileOut):
    ocr_text: str | None
    ocr_truncated: bool


class ApplicationStatusEventOut(ORMModel):
    from_status: str
    to_status: str
    reason: str
    created_at: datetime


class ApplicationOut(PublicApplicationOut):
    id: UUID
    invitation_id: UUID
    campaign_id: UUID
    dormitory_id: UUID
    resident_id: UUID | None
    assigned_to: UUID | None
    internal_notes: str
    files: list[ApplicationFileStaffOut] = Field(default_factory=list)
    events: list[ApplicationStatusEventOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ApplicationQueueOut(BaseModel):
    id: UUID
    reference: str
    status: str
    first_name_latin: str
    last_name_latin: str
    phone: str
    campaign_id: UUID
    dormitory_id: UUID
    assigned_to: UUID | None
    created_at: datetime


class ApplicationStatusIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ApplicationRequestInfoIn(ApplicationStatusIn):
    fields: list[str] = Field(min_length=1, max_length=30)


class ApplicationNoteIn(BaseModel):
    internal_notes: str = Field(max_length=10000)


class ApplicationApproveIn(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    room_id: UUID
    move_in: date
    move_out: date | None = None
    resident_id: UUID | None = None
    agreed_price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)
    payment_period_days: int | None = Field(default=None, gt=0, le=365000)

    @model_validator(mode="after")
    def ordered_stay(self):
        if self.move_out and self.move_out <= self.move_in:
            raise ValueError("Yashash tugash sanasi boshlanishidan keyin bo‘lishi kerak.")
        return self


class ApplicationRejectIn(ApplicationStatusIn):
    pass


class PublicStatusAccessIn(BaseModel):
    access_code: str = Field(min_length=12, max_length=80)


class PublicStatusOut(BaseModel):
    reference: str
    status: str
    requested_fields: list[str]
    review_reason: str


class PublicStatusAccessOut(BaseModel):
    csrf_token: str
    status: PublicStatusOut


class RetentionSettingsIn(BaseModel):
    retention_days: int = Field(ge=1, le=36500)
