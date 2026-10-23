import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, table, column, Uuid, String, Integer, Boolean, Date, DateTime, Numeric, Text, JSON

from app import models  # noqa: F401
from app.db import Base


def load_revision(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    return revision


def test_migrations_build_and_drop_the_full_schema_and_backfill_rooms():
    root = Path(__file__).parents[1]
    initial = load_revision(root / "alembic" / "versions" / "0001_initial.py")
    current = load_revision(root / "alembic" / "versions" / "16f28cfa0755_admission_and_residency_workflow.py")
    engine = create_engine("sqlite://")
    room_id, resident_id = uuid4(), uuid4()
    created = datetime.now(UTC)
    with engine.begin() as connection:
        ops = Operations(MigrationContext.configure(connection))
        initial.op = ops
        initial.upgrade()
        ops.bulk_insert(
            table("system_settings", column("key", String()), column("value", JSON()), column("updated_by", Uuid()), column("updated_at", DateTime(timezone=True))),
            [{"key": "general", "value": {"dorm_name": "Legacy Hall", "default_period_days": 30, "currency": "UZS"}, "updated_by": None, "updated_at": created}],
        )
        ops.bulk_insert(
            table("rooms", column("id", Uuid()), column("number", String()), column("floor", Integer()), column("capacity", Integer()), column("price", Numeric(14, 2)), column("notes", Text()), column("is_active", Boolean()), column("created_at", DateTime(timezone=True)), column("updated_at", DateTime(timezone=True))),
            [{"id": room_id, "number": "101", "floor": 1, "capacity": 2, "price": None, "notes": "", "is_active": True, "created_at": created, "updated_at": created}],
        )
        ops.bulk_insert(
            table("residents", column("id", Uuid()), column("first_name", String()), column("last_name", String()), column("phone", String()), column("telegram_username", String()), column("room_id", Uuid()), column("check_in_date", Date()), column("payment_period_days", Integer()), column("agreed_price", Numeric(14, 2)), column("notes", Text()), column("is_archived", Boolean()), column("archived_at", DateTime(timezone=True)), column("created_at", DateTime(timezone=True)), column("updated_at", DateTime(timezone=True))),
            [{"id": resident_id, "first_name": "Test", "last_name": "Resident", "phone": None, "telegram_username": None, "room_id": room_id, "check_in_date": date(2026, 1, 10), "payment_period_days": None, "agreed_price": None, "notes": "", "is_archived": False, "archived_at": None, "created_at": created, "updated_at": created}],
        )
        current.op = ops
        current.upgrade()
        inspector = inspect(connection)
        expected = {"users", "rooms", "residents", "billing_periods", "billing_changes", "payments", "payment_adjustments", "audit_events", "notifications", "system_settings", "dormitories", "admission_campaigns", "admission_invitations", "student_applications", "application_files", "application_status_events", "application_access_sessions", "residence_periods", "public_rate_limits"}
        assert expected <= set(inspector.get_table_names())
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        dormitory_id = connection.exec_driver_sql("SELECT dormitory_id FROM rooms WHERE number = '101'").scalar_one()
        dormitory_name = connection.exec_driver_sql("SELECT name FROM dormitories WHERE id = ?", (str(dormitory_id),)).scalar_one()
        assert dormitory_name == "Legacy Hall"
        period = connection.exec_driver_sql("SELECT resident_id, room_id, start_date, end_date, status FROM residence_periods").first()
        assert period is not None
        assert period[0] == resident_id.hex
        assert period[2] == "2026-01-10"
        assert period[3] is None
        current.downgrade()
        initial.downgrade()
        assert not (expected & set(inspect(connection).get_table_names()))
    engine.dispose()
