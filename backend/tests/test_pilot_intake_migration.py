import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError


REVISION = "d8f5b4c3a210"
PARENT_REVISION = "c7e4a91f2b60"


def _load_migration():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / f"{REVISION}_add_pilot_intake_operations.py"
    )
    spec = importlib.util.spec_from_file_location("pilot_intake_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pilot_intake_migration_is_reversible_and_preserves_existing_requests(tmp_path):
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(Path(__file__).parents[1] / "alembic"),
    )
    script = ScriptDirectory.from_config(alembic_config)
    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert tuple(revision._versioned_down_revisions) == (PARENT_REVISION,)

    migration = _load_migration()
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'pilot_intake_migration.db'}")
    metadata = sa.MetaData()
    pilot_requests = sa.Table(
        "pilot_requests",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("notification_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(engine)
    existing_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    with engine.begin() as connection:
        connection.execute(
            pilot_requests.insert().values(
                id=existing_id,
                name="Existing Pilot",
                email="existing@example.com",
                subject="demo",
                message="Existing request",
                status="pending",
                notification_status="pending",
                created_at=now,
                updated_at=now,
            )
        )

        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()
            inspector = sa.inspect(connection)
            columns = {column["name"] for column in inspector.get_columns("pilot_requests")}
            assert {
                "company",
                "business_type",
                "repetitive_task",
                "examples",
                "goal",
                "urgency",
                "consented_at",
                "routed_to",
                "fulfillment_status",
                "client_notification_status",
                "payment_notification_status",
                "notification_attempts",
                "payment_notification_attempts",
                "last_notification_error",
                "last_contacted_at",
            }.issubset(columns)
            assert "ix_pilot_requests_fulfillment_status" in {
                index["name"] for index in inspector.get_indexes("pilot_requests")
            }

            upgraded = sa.Table("pilot_requests", sa.MetaData(), autoload_with=connection)
            row = connection.execute(
                sa.select(upgraded).where(upgraded.c.id == existing_id)
            ).mappings().one()
            assert row["fulfillment_status"] == "new"
            assert row["client_notification_status"] == "pending"
            assert row["payment_notification_status"] == "pending"
            assert row["notification_attempts"] == 0
            assert row["payment_notification_attempts"] == 0

            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        upgraded.update()
                        .where(upgraded.c.id == existing_id)
                        .values(fulfillment_status="unauthorized")
                    )

            migration.downgrade()
            downgraded_columns = {
                column["name"]
                for column in sa.inspect(connection).get_columns("pilot_requests")
            }
            assert "fulfillment_status" not in downgraded_columns
            assert "company" not in downgraded_columns
            assert connection.execute(
                sa.select(sa.func.count()).select_from(
                    sa.Table("pilot_requests", sa.MetaData(), autoload_with=connection)
                )
            ).scalar_one() == 1
        finally:
            migration.op = original_op
