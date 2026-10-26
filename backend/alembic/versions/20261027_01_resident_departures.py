"""track resident departures separately from archived profiles

Revision ID: 20261027_01
Revises: 20261026_03
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20261027_01"
down_revision = "20261026_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("residents", sa.Column("departed_on", sa.Date(), nullable=True))
    op.create_index("ix_residents_departed_on", "residents", ["departed_on"])


def downgrade() -> None:
    op.drop_index("ix_residents_departed_on", table_name="residents")
    op.drop_column("residents", "departed_on")
