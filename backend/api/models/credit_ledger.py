"""backend/api/models/credit_ledger.py — Immutable credit history ledger.

Every credit movement (purchase, deduction, adjustment, refund) is recorded here.
This is the source of truth for disputes, auditing, and financial reporting.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.database import Base

if TYPE_CHECKING:
    from api.models.user import User


class CreditLedger(Base):
    __tablename__ = "credit_ledger"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # "purchase" | "deduction" | "adjustment" | "refund" | "expiry"
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Positive = credit in, negative = credit out
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    # Human-readable source: module name, addon slug, admin action, etc.
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # For idempotent Stripe webhook credit adds — prevents double-crediting
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    user: Mapped[User] = relationship("User", back_populates="credit_ledger")
