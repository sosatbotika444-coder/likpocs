"""replace stored local OCR output with consent-gated AI field suggestions

Revision ID: 20261028_01
Revises: 20261027_01
Create Date: 2026-10-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20261028_01"
down_revision = "20261027_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "student_applications",
        sa.Column("ai_processing_consented_at", sa.DateTime(timezone=True), nullable=True),
    )
    with op.batch_alter_table("application_files") as batch_op:
        batch_op.add_column(sa.Column("ai_status", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("extracted_data", sa.JSON(), nullable=True))

    op.execute(sa.text("UPDATE application_files SET ai_status = 'NOT_CONFIGURED' WHERE ai_status IS NULL"))
    op.execute(sa.text("UPDATE application_files SET extracted_data = '{}' WHERE extracted_data IS NULL"))

    with op.batch_alter_table("application_files") as batch_op:
        batch_op.alter_column("ai_status", existing_type=sa.String(length=24), nullable=False)
        batch_op.alter_column("extracted_data", existing_type=sa.JSON(), nullable=False)
        # Removing this column also clears previously stored document text.
        batch_op.drop_column("ocr_truncated")
        batch_op.drop_column("ocr_text")
        batch_op.drop_column("ocr_status")


def downgrade() -> None:
    with op.batch_alter_table("application_files") as batch_op:
        batch_op.add_column(sa.Column("ocr_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("ocr_text", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("ocr_truncated", sa.Boolean(), nullable=True))
        batch_op.drop_column("extracted_data")
        batch_op.drop_column("ai_status")

    op.execute(sa.text("UPDATE application_files SET ocr_status = 'NOT_CONFIGURED' WHERE ocr_status IS NULL"))
    op.execute(sa.text("UPDATE application_files SET ocr_truncated = false WHERE ocr_truncated IS NULL"))

    with op.batch_alter_table("application_files") as batch_op:
        batch_op.alter_column("ocr_status", existing_type=sa.String(length=20), nullable=False)
        batch_op.alter_column("ocr_truncated", existing_type=sa.Boolean(), nullable=False)
    op.drop_column("student_applications", "ai_processing_consented_at")
