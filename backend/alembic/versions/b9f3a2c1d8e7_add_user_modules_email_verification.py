"""add user_modules table, email verification fields, resize totp_secret

Revision ID: b9f3a2c1d8e7
Revises: 370e89b14c7c
Create Date: 2026-04-04 12:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "b9f3a2c1d8e7"
down_revision: Union[str, None] = "370e89b14c7c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create user_modules table ─────────────────────────────────────────
    op.create_table(
        "user_modules",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True) if _is_pg() else sa.String(36),
                  primary_key=True),
        sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True) if _is_pg() else sa.String(36),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("module_slug", sa.String(64), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "module_slug", name="uq_user_module"),
    )
    op.create_index("ix_user_modules_user_slug", "user_modules", ["user_id", "module_slug"])
    op.create_index("ix_user_modules_stripe_sub", "user_modules", ["stripe_subscription_id"])

    # ── 2. Add email verification fields to users ────────────────────────────
    op.add_column("users", sa.Column("email_verified", sa.Boolean(), nullable=False,
                                     server_default=sa.false()))
    op.add_column("users", sa.Column("email_verification_token", sa.String(128), nullable=True))
    op.add_column("users", sa.Column("email_verification_expires",
                                      sa.DateTime(timezone=True), nullable=True))

    # ── 3. Resize totp_secret (String 64 → 512) for Fernet-encrypted storage ─
    # SQLite ignores length constraints so this is a no-op there; important for PG
    try:
        op.alter_column("users", "totp_secret",
                         existing_type=sa.String(64),
                         type_=sa.String(512),
                         existing_nullable=True)
    except Exception:
        # SQLite does not support ALTER COLUMN type change — safe to skip
        pass

    # ── 4. Index for fast email_verification_token lookup ────────────────────
    op.create_index("ix_users_email_verification_token", "users", ["email_verification_token"])


def downgrade() -> None:
    op.drop_index("ix_users_email_verification_token", table_name="users")
    try:
        op.alter_column("users", "totp_secret",
                         existing_type=sa.String(512),
                         type_=sa.String(64),
                         existing_nullable=True)
    except Exception:
        pass
    op.drop_column("users", "email_verification_expires")
    op.drop_column("users", "email_verification_token")
    op.drop_column("users", "email_verified")
    op.drop_index("ix_user_modules_stripe_sub", table_name="user_modules")
    op.drop_index("ix_user_modules_user_slug", table_name="user_modules")
    op.drop_table("user_modules")


def _is_pg() -> bool:
    """Detect if we're running against PostgreSQL."""
    try:
        bind = op.get_bind()
        return bind.dialect.name == "postgresql"
    except Exception:
        return False
