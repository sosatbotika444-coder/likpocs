"""store private OCR review results on application files

Revision ID: 20261026_02
Revises: 20261026_01
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20261026_02"
down_revision = "20261026_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("application_files") as batch_op:
        batch_op.add_column(sa.Column("ocr_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("ocr_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("ocr_truncated", sa.Boolean(), nullable=True))

    op.execute(sa.text("UPDATE application_files SET ocr_status = 'NOT_CONFIGURED' WHERE ocr_status IS NULL"))
    op.execute(sa.text("UPDATE application_files SET ocr_truncated = false WHERE ocr_truncated IS NULL"))

    with op.batch_alter_table("application_files") as batch_op:
        batch_op.alter_column("ocr_status", existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column("ocr_truncated", existing_type=sa.Boolean(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("application_files") as batch_op:
        batch_op.drop_column("ocr_truncated")
        batch_op.drop_column("ocr_text")
        batch_op.drop_column("ocr_status")
