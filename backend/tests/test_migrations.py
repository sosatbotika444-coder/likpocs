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
    financial = load_revision(root / "alembic" / "versions" / "20261026_01_financial_controls_and_expenses.py")
    ocr = load_revision(root / "alembic" / "versions" / "20261026_02_application_file_ocr.py")
    file_blobs = load_revision(root / "alembic" / "versions" / "20261026_03_postgres_application_file_blobs.py")
    departures = load_revision(root / "alembic" / "versions" / "20261027_01_resident_departures.py")
    ai_extraction = load_revision(root / "alembic" / "versions" / "20261028_01_openrouter_document_extraction.py")
    engine = create_engine("sqlite://")
    room_id, resident_id = uuid4(), uuid4()
    application_id, application_file_id = uuid4(), uuid4()
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
        ops.bulk_insert(
            table(
                "application_files",
                column("id", Uuid()), column("application_id", Uuid()), column("kind", String()),
                column("document_type", String()), column("object_key", String()), column("original_name", String()),
                column("content_type", String()), column("size_bytes", Integer()), column("scan_status", String()),
                column("delete_after", DateTime(timezone=True)), column("deleted_at", DateTime(timezone=True)),
                column("uploaded_at", DateTime(timezone=True)),
            ),
            [{
                "id": application_file_id, "application_id": application_id, "kind": "DOCUMENT",
                "document_type": "ID", "object_key": "admissions/legacy/id.png", "original_name": "id.png",
                "content_type": "image/png", "size_bytes": 1, "scan_status": "NOT_CONFIGURED",
                "delete_after": None, "deleted_at": None, "uploaded_at": created,
            }],
        )
        financial.op = ops
        financial.upgrade()
        ocr.op = ops
        ocr.upgrade()
        file_blobs.op = ops
        file_blobs.upgrade()
        departures.op = ops
        departures.upgrade()
        ai_extraction.op = ops
        ai_extraction.upgrade()
        inspector = inspect(connection)
        expected = {"users", "rooms", "residents", "billing_periods", "billing_changes", "payments", "payment_adjustments", "audit_events", "notifications", "system_settings", "dormitories", "admission_campaigns", "admission_invitations", "student_applications", "application_files", "application_file_blobs", "application_status_events", "application_access_sessions", "residence_periods", "public_rate_limits", "expenses"}
        assert expected <= set(inspector.get_table_names())
        file_columns = {column["name"] for column in inspector.get_columns("application_files")}
        assert {"ai_status", "extracted_data"} <= file_columns
        assert not {"ocr_status", "ocr_text", "ocr_truncated"} & file_columns
        ai_backfill = connection.exec_driver_sql(
            "SELECT ai_status, extracted_data FROM application_files WHERE id = ?",
            (application_file_id.hex,),
        ).first()
        assert ai_backfill == ("NOT_CONFIGURED", "{}")
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        dormitory_id = connection.exec_driver_sql("SELECT dormitory_id FROM rooms WHERE number = '101'").scalar_one()
        dormitory_name = connection.exec_driver_sql("SELECT name FROM dormitories WHERE id = ?", (str(dormitory_id),)).scalar_one()
        assert dormitory_name == "Legacy Hall"
        period = connection.exec_driver_sql("SELECT resident_id, room_id, start_date, end_date, status FROM residence_periods").first()
        assert period is not None
        assert period[0] == resident_id.hex
        assert period[2] == "2026-01-10"
        assert period[3] is None
        ai_extraction.downgrade()
        departures.downgrade()
        file_blobs.downgrade()
        ocr.downgrade()
        financial.downgrade()
        current.downgrade()
        initial.downgrade()
        assert not (expected & set(inspect(connection).get_table_names()))
    engine.dispose()
