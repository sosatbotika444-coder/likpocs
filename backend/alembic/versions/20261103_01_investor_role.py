"""allow the aggregate-only INVESTOR staff role

Revision ID: 20261103_01
Revises: 20261030_01
Create Date: 2026-11-03
"""

from alembic import op


revision = "20261103_01"
down_revision = "20261030_01"
branch_labels = None
depends_on = None


def _replace_role_check(allowed: str) -> None:
    # batch_alter_table keeps SQLite support while Alembic emits the normal
    # named-constraint operation for PostgreSQL.
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("ck_user_role", type_="check")
        batch.create_check_constraint("ck_user_role", allowed)


def upgrade() -> None:
    _replace_role_check("role IN ('OPERATOR', 'ADMIN', 'INVESTOR')")


def downgrade() -> None:
    _replace_role_check("role IN ('OPERATOR', 'ADMIN')")
