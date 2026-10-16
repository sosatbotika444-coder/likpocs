"""Create the initial DormFlow schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-16
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("number", sa.String(length=32), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capacity > 0", name="ck_room_capacity_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("number", name="uq_room_number"),
    )
    op.create_index("ix_rooms_number", "rooms", ["number"], unique=False)

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('OPERATOR', 'ADMIN')", name="ck_user_role"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "residents",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("first_name", sa.String(length=80), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=False),
        sa.Column("phone", sa.String(length=40), nullable=True),
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
        sa.Column("room_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("check_in_date", sa.Date(), nullable=True),
        sa.Column("payment_period_days", sa.Integer(), nullable=True),
        sa.Column("agreed_price", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("payment_period_days IS NULL OR payment_period_days > 0", name="ck_resident_period_positive"),
        sa.CheckConstraint("agreed_price IS NULL OR agreed_price >= 0", name="ck_resident_price_nonnegative"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_resident_name", "residents", ["last_name", "first_name"], unique=False)
    op.create_index("ix_residents_is_archived", "residents", ["is_archived"], unique=False)
    op.create_index("ix_residents_room_id", "residents", ["room_id"], unique=False)

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_action", "audit_events", ["action"], unique=False)
    op.create_index("ix_audit_events_actor_id", "audit_events", ["actor_id"], unique=False)
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"], unique=False)

    op.create_table(
        "notifications",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"], unique=False)
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"], unique=False)

    op.create_table(
        "billing_periods",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("resident_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False),
        sa.Column("charge_amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("end_date > start_date", name="ck_billing_dates_ordered"),
        sa.CheckConstraint("period_days > 0", name="ck_billing_period_positive"),
        sa.CheckConstraint("charge_amount >= 0", name="ck_billing_charge_nonnegative"),
        sa.CheckConstraint("status IN ('OPEN', 'PAID', 'CLOSED')", name="ck_billing_status"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_periods_end_date", "billing_periods", ["end_date"], unique=False)
    op.create_index("ix_billing_periods_resident_id", "billing_periods", ["resident_id"], unique=False)
    op.create_index("ix_billing_resident_status", "billing_periods", ["resident_id", "status"], unique=False)

    op.create_table(
        "billing_changes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("resident_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("billing_period_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("old_start_date", sa.Date(), nullable=False),
        sa.Column("old_end_date", sa.Date(), nullable=False),
        sa.Column("new_start_date", sa.Date(), nullable=False),
        sa.Column("new_end_date", sa.Date(), nullable=False),
        sa.Column("change_type", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("changed_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["billing_period_id"], ["billing_periods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["changed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_changes_billing_period_id", "billing_changes", ["billing_period_id"], unique=False)
    op.create_index("ix_billing_changes_resident_id", "billing_changes", ["resident_id"], unique=False)

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("resident_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("billing_period_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("covered_start", sa.Date(), nullable=True),
        sa.Column("covered_end", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("recorded_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
        sa.CheckConstraint("method IN ('CASH', 'BANK', 'CLICK', 'PAYME', 'OTHER')", name="ck_payment_method"),
        sa.ForeignKeyConstraint(["billing_period_id"], ["billing_periods.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payments_billing_period_id", "payments", ["billing_period_id"], unique=False)
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"], unique=False)
    op.create_index("ix_payments_resident_id", "payments", ["resident_id"], unique=False)

    op.create_table(
        "payment_adjustments",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("payment_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("amount_delta", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("adjusted_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount_delta != 0", name="ck_adjustment_nonzero"),
        sa.ForeignKeyConstraint(["adjusted_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_adjustments_payment_id", "payment_adjustments", ["payment_id"], unique=False)


def downgrade() -> None:
    op.drop_table("payment_adjustments")
    op.drop_table("payments")
    op.drop_table("billing_changes")
    op.drop_table("billing_periods")
    op.drop_table("notifications")
    op.drop_table("audit_events")
    op.drop_table("system_settings")
    op.drop_table("residents")
    op.drop_table("users")
    op.drop_table("rooms")
