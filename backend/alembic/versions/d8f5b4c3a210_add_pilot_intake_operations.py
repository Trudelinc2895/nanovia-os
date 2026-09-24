"""add structured Pilot intake and operational notification state

Revision ID: d8f5b4c3a210
Revises: c7e4a91f2b60
Create Date: 2026-09-15 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "d8f5b4c3a210"
down_revision: Union[str, Sequence[str], None] = "c7e4a91f2b60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pilot_requests", sa.Column("company", sa.String(100), nullable=True))
    op.add_column("pilot_requests", sa.Column("business_type", sa.String(120), nullable=True))
    op.add_column("pilot_requests", sa.Column("repetitive_task", sa.Text(), nullable=True))
    op.add_column("pilot_requests", sa.Column("examples", sa.Text(), nullable=True))
    op.add_column("pilot_requests", sa.Column("goal", sa.Text(), nullable=True))
    op.add_column("pilot_requests", sa.Column("urgency", sa.String(16), nullable=True))
    op.add_column("pilot_requests", sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("pilot_requests", sa.Column("routed_to", sa.String(255), nullable=True))
    op.add_column(
        "pilot_requests",
        sa.Column("fulfillment_status", sa.String(32), nullable=False, server_default="new"),
    )
    op.add_column(
        "pilot_requests",
        sa.Column("client_notification_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "pilot_requests",
        sa.Column("payment_notification_status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "pilot_requests",
        sa.Column("notification_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "pilot_requests",
        sa.Column("payment_notification_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("pilot_requests", sa.Column("last_notification_error", sa.Text(), nullable=True))
    op.add_column("pilot_requests", sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("pilot_requests") as batch_op:
        batch_op.create_check_constraint(
            "ck_pilot_requests_fulfillment_status",
            "fulfillment_status IN ('new','qualified','in_progress','waiting_client','delivered','closed','rejected')",
        )
        batch_op.create_check_constraint(
            "ck_pilot_requests_client_notification_status",
            "client_notification_status IN ('pending','sent','failed')",
        )
        batch_op.create_check_constraint(
            "ck_pilot_requests_payment_notification_status",
            "payment_notification_status IN ('pending','sent','failed')",
        )
        batch_op.create_check_constraint(
            "ck_pilot_requests_urgency",
            "urgency IS NULL OR urgency IN ('faible','moyen','eleve','urgent')",
        )

    op.create_index(
        "ix_pilot_requests_fulfillment_status",
        "pilot_requests",
        ["fulfillment_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_pilot_requests_fulfillment_status", table_name="pilot_requests")
    with op.batch_alter_table("pilot_requests") as batch_op:
        batch_op.drop_constraint("ck_pilot_requests_urgency", type_="check")
        batch_op.drop_constraint("ck_pilot_requests_payment_notification_status", type_="check")
        batch_op.drop_constraint("ck_pilot_requests_client_notification_status", type_="check")
        batch_op.drop_constraint("ck_pilot_requests_fulfillment_status", type_="check")
        batch_op.drop_column("last_contacted_at")
        batch_op.drop_column("last_notification_error")
        batch_op.drop_column("payment_notification_attempts")
        batch_op.drop_column("notification_attempts")
        batch_op.drop_column("payment_notification_status")
        batch_op.drop_column("client_notification_status")
        batch_op.drop_column("fulfillment_status")
        batch_op.drop_column("routed_to")
        batch_op.drop_column("consented_at")
        batch_op.drop_column("urgency")
        batch_op.drop_column("goal")
        batch_op.drop_column("examples")
        batch_op.drop_column("repetitive_task")
        batch_op.drop_column("business_type")
        batch_op.drop_column("company")
