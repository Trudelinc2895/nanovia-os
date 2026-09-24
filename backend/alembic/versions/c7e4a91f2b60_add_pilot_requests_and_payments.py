"""add Pilot requests, payments, and retryable webhook attempts

Revision ID: c7e4a91f2b60
Revises: 5d9f6e2a4c31, a1b2c3d4e5f6
Create Date: 2026-07-24 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7e4a91f2b60"
down_revision: Union[str, Sequence[str], None] = (
    "5d9f6e2a4c31",
    "a1b2c3d4e5f6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type() -> sa.TypeEngine:
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.String(36)


def upgrade() -> None:
    uuid_type = _uuid_type()
    pilot_states = "'pending','paid','processing','failed','manual_review'"

    op.create_table(
        "pilot_requests",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column(
            "notification_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"status IN ({pilot_states})", name="ck_pilot_requests_status"
        ),
        sa.CheckConstraint(
            "notification_status IN ('pending','sent','failed')",
            name="ck_pilot_requests_notification_status",
        ),
    )
    op.create_index("ix_pilot_requests_email", "pilot_requests", ["email"])
    op.create_index("ix_pilot_requests_status", "pilot_requests", ["status"])
    op.create_index("ix_pilot_requests_created_at", "pilot_requests", ["created_at"])

    op.create_table(
        "pilot_payments",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "pilot_request_id",
            uuid_type,
            sa.ForeignKey("pilot_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_payment_link_id", sa.String(length=255), nullable=False),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=False),
        sa.Column("customer_email", sa.String(length=255), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount_subtotal", sa.Integer(), nullable=True),
        sa.Column("payment_status", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"status IN ({pilot_states})", name="ck_pilot_payments_status"
        ),
        sa.UniqueConstraint(
            "stripe_checkout_session_id", name="uq_pilot_payments_checkout_session"
        ),
    )
    op.create_index(
        "ix_pilot_payments_pilot_request_id",
        "pilot_payments",
        ["pilot_request_id"],
    )
    op.create_index("ix_pilot_payments_status", "pilot_payments", ["status"])
    payment_intent_present = sa.text("stripe_payment_intent_id IS NOT NULL")
    op.create_index(
        "uq_pilot_payments_payment_intent_not_null",
        "pilot_payments",
        ["stripe_payment_intent_id"],
        unique=True,
        postgresql_where=payment_intent_present,
        sqlite_where=payment_intent_present,
    )

    with op.batch_alter_table("webhook_events") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column(
                "attempt_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("1"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("webhook_events") as batch_op:
        batch_op.drop_column("attempt_count")
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=32),
            type_=sa.String(length=20),
            existing_nullable=False,
        )

    op.drop_index(
        "uq_pilot_payments_payment_intent_not_null",
        table_name="pilot_payments",
    )
    op.drop_index("ix_pilot_payments_status", table_name="pilot_payments")
    op.drop_index("ix_pilot_payments_pilot_request_id", table_name="pilot_payments")
    op.drop_table("pilot_payments")
    op.drop_index("ix_pilot_requests_created_at", table_name="pilot_requests")
    op.drop_index("ix_pilot_requests_status", table_name="pilot_requests")
    op.drop_index("ix_pilot_requests_email", table_name="pilot_requests")
    op.drop_table("pilot_requests")
