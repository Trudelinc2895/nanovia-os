"""
backend/api/models/user_module.py

Tracks individual module purchases (à-la-carte subscriptions).
A user can own modules via:
  1. Plan inclusion (no row needed — determined by plan tier)
  2. Individual purchase (row in this table with status=active)

Never modify directly — always go through billing webhook or admin ops.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class UserModule(Base):
    __tablename__ = "user_modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # e.g. "operator", "ghost", "content" — must match MODULES_CONFIG keys
    module_slug: Mapped[str] = mapped_column(String(64), nullable=False)

    # Stripe info for lifecycle management
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # "active" | "cancelled" | "past_due" | "trialing"
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)

    activated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One active subscription per user per module (enforced at app layer too)
    __table_args__ = (
        UniqueConstraint("user_id", "module_slug", name="uq_user_module"),
        Index("ix_user_modules_user_slug", "user_id", "module_slug"),
    )

    user: Mapped["User"] = relationship("User", back_populates="modules")  # type: ignore[name-defined]

    def is_active(self) -> bool:
        """Return True if this module access is currently valid."""
        if self.status not in ("active", "trialing"):
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True

    def __repr__(self) -> str:
        return f"<UserModule user={self.user_id} slug={self.module_slug} status={self.status}>"
