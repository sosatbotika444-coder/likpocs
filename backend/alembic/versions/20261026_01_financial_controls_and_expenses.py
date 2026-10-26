"""add auditable expense ledger and payment idempotency

Revision ID: 20261026_01
Revises: 16f28cfa0755
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20261026_01"
down_revision = "16f28cfa0755"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("billing_changes") as batch_op:
        batch_op.add_column(sa.Column("old_charge_amount", sa.Numeric(precision=14, scale=2), nullable=True))
        batch_op.add_column(sa.Column("new_charge_amount", sa.Numeric(precision=14, scale=2), nullable=True))

    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch_op.create_unique_constraint("uq_payment_actor_idempotency", ["recorded_by", "idempotency_key"])

    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("recorded_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("void_reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
        sa.CheckConstraint("method IN ('CASH', 'BANK', 'CLICK', 'PAYME', 'OTHER')", name="ck_expense_method"),
        sa.CheckConstraint("category IN ('UTILITIES', 'REPAIR', 'SUPPLIES', 'FOOD', 'SALARY', 'OTHER')", name="ck_expense_category"),
        sa.ForeignKeyConstraint(["recorded_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["voided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recorded_by", "idempotency_key", name="uq_expense_actor_idempotency"),
    )
    op.create_index("ix_expenses_expense_date", "expenses", ["expense_date"], unique=False)
    op.create_index("ix_expenses_recorded_by", "expenses", ["recorded_by"], unique=False)
    op.create_index("ix_expense_date_voided", "expenses", ["expense_date", "voided_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_expense_date_voided", table_name="expenses")
    op.drop_index("ix_expenses_recorded_by", table_name="expenses")
    op.drop_index("ix_expenses_expense_date", table_name="expenses")
    op.drop_table("expenses")
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("uq_payment_actor_idempotency", type_="unique")
        batch_op.drop_column("idempotency_key")
    with op.batch_alter_table("billing_changes") as batch_op:
        batch_op.drop_column("new_charge_amount")
        batch_op.drop_column("old_charge_amount")
