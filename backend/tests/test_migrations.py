import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect

from app.db import Base
from app import models  # noqa: F401


def test_initial_migration_builds_and_drops_the_full_schema():
    revision_path = Path(__file__).parents[1] / "alembic" / "versions" / "0001_initial.py"
    spec = importlib.util.spec_from_file_location("dormflow_initial_migration", revision_path)
    assert spec and spec.loader
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = create_engine("sqlite://")
    required = {"users", "rooms", "residents", "billing_periods", "billing_changes", "payments", "payment_adjustments", "audit_events", "notifications", "system_settings"}
    with engine.begin() as connection:
        ops = Operations(MigrationContext.configure(connection))
        revision.op = ops
        revision.upgrade()
        assert required <= set(inspect(connection).get_table_names())
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
        revision.downgrade()
        assert not (required & set(inspect(connection).get_table_names()))
    engine.dispose()
