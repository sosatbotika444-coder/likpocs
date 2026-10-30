"""add staff task board

Revision ID: 20261030_01
Revises: 20261028_01
Create Date: 2026-10-30
"""

from alembic import op
import sqlalchemy as sa


revision = "20261030_01"
down_revision = "20261028_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_tasks",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("priority", sa.String(length=12), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("assignee_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("room_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("resident_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED')", name="ck_staff_task_status"),
        sa.CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH', 'URGENT')", name="ck_staff_task_priority"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resident_id"], ["residents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_staff_tasks_assignee_id", "staff_tasks", ["assignee_id"], unique=False)
    op.create_index("ix_staff_tasks_created_by", "staff_tasks", ["created_by"], unique=False)
    op.create_index("ix_staff_task_status_due", "staff_tasks", ["status", "due_date"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_staff_task_status_due", table_name="staff_tasks")
    op.drop_index("ix_staff_tasks_created_by", table_name="staff_tasks")
    op.drop_index("ix_staff_tasks_assignee_id", table_name="staff_tasks")
    op.drop_table("staff_tasks")
