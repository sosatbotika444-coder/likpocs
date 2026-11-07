"""preserve contract document and operator signature snapshots

Revision ID: 20261107_01
Revises: 20261104_01
Create Date: 2026-11-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20261107_01"
down_revision = "20261104_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("student_applications") as batch:
        batch.add_column(sa.Column("contract_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.add_column(sa.Column("contract_operator_signature_name", sa.String(length=200), nullable=False, server_default=""))
        batch.add_column(sa.Column("contract_operator_signed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("student_applications") as batch:
        batch.drop_column("contract_operator_signed_at")
        batch.drop_column("contract_operator_signature_name")
        batch.drop_column("contract_snapshot")
