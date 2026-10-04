"""Persistent Nanovia Pro Pilot requests and Stripe payments."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base


PILOT_STATES = ("pending", "paid", "processing", "failed", "manual_review")


class PilotRequest(Base):
    __tablename__ = "pilot_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(String(100), nullable=True)
    business_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    repetitive_task: Mapped[str | None] = mapped_column(Text, nullable=True)
    examples: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal: Mapped[str | None] = mapped_column(Text, nullable=True)
    urgency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    consented_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    routed_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    fulfillment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="new", index=True
    )
    notification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    client_notification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    payment_notification_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )
    notification_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    payment_notification_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    last_notification_error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    payments: Mapped[list["PilotPayment"]] = relationship(
        back_populates="pilot_request"
    )


class PilotPayment(Base):
    __tablename__ = "pilot_payments"
    __table_args__ = (
        UniqueConstraint(
            "stripe_checkout_session_id",
            name="uq_pilot_payments_checkout_session",
        ),
        Index(
            "uq_pilot_payments_payment_intent_not_null",
            "stripe_payment_intent_id",
            unique=True,
            postgresql_where=text("stripe_payment_intent_id IS NOT NULL"),
            sqlite_where=text("stripe_payment_intent_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    pilot_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("pilot_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stripe_checkout_session_id: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    stripe_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_payment_link_id: Mapped[str] = mapped_column(String(255), nullable=False)
    stripe_price_id: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_subtotal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_status: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True
    )
    livemode: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    pilot_request: Mapped[PilotRequest | None] = relationship(
        back_populates="payments"
    )
