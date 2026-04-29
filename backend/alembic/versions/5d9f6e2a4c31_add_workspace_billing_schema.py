"""add workspace-native billing schema

Revision ID: 5d9f6e2a4c31
Revises: b9f3a2c1d8e7
Create Date: 2026-04-23 07:30:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "5d9f6e2a4c31"
down_revision: Union[str, None] = "b9f3a2c1d8e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _uuid_type() -> sa.TypeEngine:
    try:
        bind = op.get_bind()
        if bind.dialect.name == "postgresql":
            return sa.dialects.postgresql.UUID(as_uuid=True)
    except Exception:
        pass
    return sa.String(36)


def upgrade() -> None:
    uuid_type = _uuid_type()

    op.create_table(
        "workspaces",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("active_plan_key", sa.String(length=64), nullable=False, server_default="free"),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )
    op.create_index("ix_workspaces_owner_user_id", "workspaces", ["owner_user_id"])

    op.create_table(
        "plans",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("price_monthly_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("price_yearly_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_plans_key"),
    )
    op.create_index("ix_plans_key", "plans", ["key"])

    op.create_table(
        "plan_features",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("plan_id", uuid_type, sa.ForeignKey("plans.id", ondelete="CASCADE"), nullable=False),
        sa.Column("feature_key", sa.String(length=120), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("limit_value", sa.Integer(), nullable=True),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.UniqueConstraint("plan_id", "feature_key", name="uq_plan_features_plan_feature"),
    )
    op.create_index("ix_plan_features_plan_id", "plan_features", ["plan_id"])

    op.create_table(
        "addons",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("addon_type", sa.String(length=32), nullable=False, server_default="one_time"),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("grants", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("key", name="uq_addons_key"),
        sa.UniqueConstraint("stripe_price_id", name="uq_addons_stripe_price_id"),
    )
    op.create_index("ix_addons_key", "addons", ["key"])

    op.create_table(
        "members",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False, server_default="member"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="invited"),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "email", name="uq_members_workspace_email"),
    )
    op.create_index("ix_members_workspace_id", "members", ["workspace_id"])
    op.create_index("ix_members_user_id", "members", ["user_id"])

    op.create_table(
        "billing_customers",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="stripe"),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", name="uq_billing_customers_workspace_id"),
        sa.UniqueConstraint("provider_customer_id", name="uq_billing_customers_provider_customer_id"),
    )
    op.create_index("ix_billing_customers_provider_customer_id", "billing_customers", ["provider_customer_id"])

    op.create_table(
        "payment_methods",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="stripe"),
        sa.Column("provider_payment_method_id", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=50), nullable=True),
        sa.Column("last4", sa.String(length=4), nullable=True),
        sa.Column("exp_month", sa.Integer(), nullable=True),
        sa.Column("exp_year", sa.Integer(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_payment_method_id", name="uq_payment_methods_provider_payment_method_id"),
    )
    op.create_index("ix_payment_methods_workspace_id", "payment_methods", ["workspace_id"])
    op.create_index("ix_payment_methods_provider_payment_method_id", "payment_methods", ["provider_payment_method_id"])

    op.create_table(
        "invoices",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", uuid_type, sa.ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider_invoice_id", sa.String(length=255), nullable=True),
        sa.Column("invoice_number", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_invoice_id", name="uq_invoices_provider_invoice_id"),
    )
    op.create_index("ix_invoices_workspace_id", "invoices", ["workspace_id"])
    op.create_index("ix_invoices_subscription_id", "invoices", ["subscription_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", uuid_type, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("request_id", sa.String(length=120), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=False, server_default="0"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("idempotency_key", name="uq_usage_events_idempotency_key"),
    )
    op.create_index("ix_usage_events_workspace_id", "usage_events", ["workspace_id"])
    op.create_index("ix_usage_events_actor_user_id", "usage_events", ["actor_user_id"])
    op.create_index("ix_usage_events_request_id", "usage_events", ["request_id"])
    op.create_index("ix_usage_events_event_type", "usage_events", ["event_type"])

    op.create_table(
        "credit_balances",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("workspace_id", uuid_type, sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", name="uq_credit_balances_workspace_id"),
    )


def downgrade() -> None:
    op.drop_table("credit_balances")

    op.drop_index("ix_usage_events_event_type", table_name="usage_events")
    op.drop_index("ix_usage_events_request_id", table_name="usage_events")
    op.drop_index("ix_usage_events_actor_user_id", table_name="usage_events")
    op.drop_index("ix_usage_events_workspace_id", table_name="usage_events")
    op.drop_table("usage_events")

    op.drop_index("ix_invoices_subscription_id", table_name="invoices")
    op.drop_index("ix_invoices_workspace_id", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index("ix_payment_methods_provider_payment_method_id", table_name="payment_methods")
    op.drop_index("ix_payment_methods_workspace_id", table_name="payment_methods")
    op.drop_table("payment_methods")

    op.drop_index("ix_billing_customers_provider_customer_id", table_name="billing_customers")
    op.drop_table("billing_customers")

    op.drop_index("ix_members_user_id", table_name="members")
    op.drop_index("ix_members_workspace_id", table_name="members")
    op.drop_table("members")

    op.drop_index("ix_addons_key", table_name="addons")
    op.drop_table("addons")

    op.drop_index("ix_plan_features_plan_id", table_name="plan_features")
    op.drop_table("plan_features")

    op.drop_index("ix_plans_key", table_name="plans")
    op.drop_table("plans")

    op.drop_index("ix_workspaces_owner_user_id", table_name="workspaces")
    op.drop_table("workspaces")
