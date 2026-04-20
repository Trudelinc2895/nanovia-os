"""
backend/api/models/user.py — User model (multi-tenant ready)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from datetime import timezone as _tz  # noqa: F401 (used below)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


class PlanTier(str, PyEnum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default=PlanTier.FREE, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    password_reset_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    password_reset_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Email verification
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_verification_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    email_verification_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Two-factor authentication (TOTP / RFC 6238)
    # String(512) to accommodate Fernet-encrypted base32 secret at rest
    totp_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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

    subscriptions: Mapped[list[Subscription]] = relationship(
        "Subscription", back_populates="user", lazy="noload"
    )
    conversations: Mapped[list[Conversation]] = relationship(
        "Conversation", back_populates="user", lazy="noload"
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="user", lazy="noload"
    )
    device_sessions: Mapped[list[DeviceSession]] = relationship(
        "DeviceSession", back_populates="user", lazy="noload"
    )
    notifications: Mapped[list[UserNotification]] = relationship(
        "UserNotification", back_populates="user", lazy="noload"
    )
    credit_ledger: Mapped[list[CreditLedger]] = relationship(
        "CreditLedger", back_populates="user", lazy="noload"
    )
    usage_records: Mapped[list[UsageRecord]] = relationship(
        "UsageRecord", back_populates="user", lazy="noload"
    )
    team_members: Mapped[list[TeamMember]] = relationship(
        "TeamMember", back_populates="owner", lazy="noload",
        foreign_keys="TeamMember.owner_id",
    )
    modules: Mapped[list[UserModule]] = relationship(
        "UserModule", back_populates="user", lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User {self.email} plan={self.plan}>"
