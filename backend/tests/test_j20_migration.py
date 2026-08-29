"""Isolated upgrade/downgrade coverage for the J20 Pilot migration."""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError


REVISION = "c7e4a91f2b60"
PARENT_REVISIONS = ("5d9f6e2a4c31", "a1b2c3d4e5f6")


def _load_migration():
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / f"{REVISION}_add_pilot_requests_and_payments.py"
    )
    spec = importlib.util.spec_from_file_location("j20_pilot_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _payment_values(
    *,
    session_id: str,
    payment_intent_id: str | None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "pilot_request_id": None,
        "stripe_checkout_session_id": session_id,
        "stripe_payment_intent_id": payment_intent_id,
        "stripe_event_id": f"evt_{session_id}",
        "stripe_payment_link_id": "plink_pilot",
        "stripe_price_id": "price_pilot",
        "customer_email": None,
        "currency": "cad",
        "amount_subtotal": 29700,
        "payment_status": "paid",
        "status": "paid",
        "livemode": False,
    }


def test_j20_migration_uuid_type_propagates_bind_failures(monkeypatch):
    migration = _load_migration()

    class BrokenOperations:
        @staticmethod
        def get_bind():
            raise RuntimeError("migration bind unavailable")

    monkeypatch.setattr(migration, "op", BrokenOperations())

    with pytest.raises(RuntimeError, match="migration bind unavailable"):
        migration._uuid_type()


def test_j20_migration_upgrade_and_downgrade_are_reversible(tmp_path):
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(Path(__file__).parents[1] / "alembic"),
    )
    script = ScriptDirectory.from_config(alembic_config)
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert tuple(revision._versioned_down_revisions) == PARENT_REVISIONS
    assert script.get_heads() == [REVISION]

    migration = _load_migration()
    assert migration.down_revision == PARENT_REVISIONS

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'j20_migration.db'}")
    metadata = sa.MetaData()
    webhook_events = sa.Table(
        "webhook_events",
        metadata,
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("stripe_event_id", sa.String(255), nullable=False, unique=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            webhook_events.insert().values(
                id=str(uuid.uuid4()),
                stripe_event_id="evt_existing",
                event_type="checkout.session.completed",
                processed_at=sa.func.now(),
                status="failed",
                error="prior failure",
            )
        )

        original_op = migration.op
        migration.op = Operations(MigrationContext.configure(connection))
        try:
            migration.upgrade()

            inspector = sa.inspect(connection)
            assert {"pilot_requests", "pilot_payments"}.issubset(
                set(inspector.get_table_names())
            )
            webhook_columns = {
                column["name"]: column
                for column in inspector.get_columns("webhook_events")
            }
            assert webhook_columns["attempt_count"]["nullable"] is False
            assert str(webhook_columns["attempt_count"]["default"]).strip("()'\"") == "1"
            assert connection.scalar(
                sa.text(
                    "SELECT attempt_count FROM webhook_events "
                    "WHERE stripe_event_id = 'evt_existing'"
                )
            ) == 1

            checkout_constraints = {
                constraint["name"]
                for constraint in inspector.get_unique_constraints("pilot_payments")
            }
            assert "uq_pilot_payments_checkout_session" in checkout_constraints
            payment_intent_indexes = {
                index["name"]: index
                for index in inspector.get_indexes("pilot_payments")
            }
            partial_index = payment_intent_indexes[
                "uq_pilot_payments_payment_intent_not_null"
            ]
            assert partial_index["unique"] == 1
            index_sql = connection.scalar(
                sa.text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'index' "
                    "AND name = 'uq_pilot_payments_payment_intent_not_null'"
                )
            )
            assert "WHERE stripe_payment_intent_id IS NOT NULL" in index_sql

            pilot_payments = sa.Table(
                "pilot_payments",
                sa.MetaData(),
                autoload_with=connection,
            )
            connection.execute(
                pilot_payments.insert(),
                [
                    _payment_values(session_id="cs_null_1", payment_intent_id=None),
                    _payment_values(session_id="cs_null_2", payment_intent_id=None),
                    _payment_values(
                        session_id="cs_unique_1",
                        payment_intent_id="pi_unique",
                    ),
                ],
            )
            with pytest.raises(IntegrityError):
                with connection.begin_nested():
                    connection.execute(
                        pilot_payments.insert().values(
                            **_payment_values(
                                session_id="cs_unique_2",
                                payment_intent_id="pi_unique",
                            )
                        )
                    )

            migration.downgrade()

            downgraded_inspector = sa.inspect(connection)
            assert "pilot_requests" not in downgraded_inspector.get_table_names()
            assert "pilot_payments" not in downgraded_inspector.get_table_names()
            downgraded_webhook_columns = {
                column["name"]: column
                for column in downgraded_inspector.get_columns("webhook_events")
            }
            assert "attempt_count" not in downgraded_webhook_columns
            assert downgraded_webhook_columns["status"]["type"].length == 20
        finally:
            migration.op = original_op

    engine.dispose()
