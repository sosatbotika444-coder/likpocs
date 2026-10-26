"""add private PostgreSQL-backed application file storage

Revision ID: 20261026_03
Revises: 20261026_02
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20261026_03"
down_revision = "20261026_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "application_file_blobs",
        sa.Column(
            "object_key",
            sa.String(length=500),
            sa.ForeignKey("application_files.object_key", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("application_file_blobs")
