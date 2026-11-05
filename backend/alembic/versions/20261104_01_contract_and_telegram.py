"""lease agreement acceptance and Telegram bot tables

Revision ID: 20261104_01
Revises: 20261103_01
Create Date: 2026-11-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20261104_01"
down_revision = "20261103_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_applications") as batch:
        batch.add_column(sa.Column("contract_version", sa.String(length=40), nullable=False, server_default=""))
        batch.add_column(sa.Column("contract_hash", sa.String(length=64), nullable=False, server_default=""))
        batch.add_column(sa.Column("contract_accepted_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("contract_signature_name", sa.String(length=200), nullable=False, server_default=""))
        batch.add_column(sa.Column("contract_signed_via", sa.String(length=12), nullable=False, server_default=""))
    op.create_table(
        "telegram_accounts",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("application_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("user_id IS NULL OR application_id IS NULL", name="ck_telegram_single_identity"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["application_id"], ["student_applications.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", name="uq_telegram_chat"),
    )
    op.create_index("ix_telegram_accounts_user_id", "telegram_accounts", ["user_id"], unique=False)
    op.create_index("ix_telegram_accounts_application_id", "telegram_accounts", ["application_id"], unique=False)
    op.create_table(
        "telegram_link_codes",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_hash", name="uq_telegram_link_code_hash"),
    )
    op.create_index("ix_telegram_link_codes_user_id", "telegram_link_codes", ["user_id"], unique=False)
    op.create_table(
        "telegram_outbox",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_telegram_outbox_pending", "telegram_outbox", ["sent_at", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_telegram_outbox_pending", table_name="telegram_outbox")
    op.drop_table("telegram_outbox")
    op.drop_index("ix_telegram_link_codes_user_id", table_name="telegram_link_codes")
    op.drop_table("telegram_link_codes")
    op.drop_index("ix_telegram_accounts_application_id", table_name="telegram_accounts")
    op.drop_index("ix_telegram_accounts_user_id", table_name="telegram_accounts")
    op.drop_table("telegram_accounts")
    with op.batch_alter_table("student_applications") as batch:
        batch.drop_column("contract_signed_via")
        batch.drop_column("contract_signature_name")
        batch.drop_column("contract_accepted_at")
        batch.drop_column("contract_hash")
        batch.drop_column("contract_version")
