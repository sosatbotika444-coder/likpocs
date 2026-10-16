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
    floor: int = Field(default=1, ge=0, le=300)
    capacity: int = Field(ge=1, le=500)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str = Field(default="", max_length=2000)


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=32)
    floor: int | None = Field(default=None, ge=0, le=300)
    capacity: int | None = Field(default=None, ge=1, le=500)
    price: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    notes: str | None = Field(default=None, max_length=2000)


class RoomOut(ORMModel):
    id: UUID
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
    new_start_date: date
    new_end_date: date
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


PaymentMethod = Literal["CASH", "BANK", "CLICK", "PAYME", "OTHER"]


class PaymentCreate(BaseModel):
    resident_id: UUID
    billing_period_id: UUID | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    payment_date: date
    method: PaymentMethod
    notes: str = Field(default="", max_length=2000)


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
    expected_payments: Decimal
    outstanding_debt: Decimal
    revenue_trend: list[dict]
    occupancy_by_room: list[dict]
    recent_payments: list[PaymentOut]
    recent_residents: list[ResidentOut]


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
