"""
backend/api/models/usage_record.py
Tracks AI message/token consumption per user for metered billing and plan enforcement.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class UsageRecord(Base):
    __tablename__ = "usage_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # Module that generated usage: "orchestrator", "ghost_agency", "content_cloner", etc.
    module: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # gpt-4o-mini rate: $0.000002 / token
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal("0")
    )
    # Cost in internal credits (1 credit = 1 overage message).
    # 0 = within plan limit (no credit cost), 1 = 1 credit deducted for overage.
    # Enables per-account margin analysis and cost attribution.
    unit_cost_credits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        # Fast monthly usage queries: WHERE user_id = ? AND created_at >= ?
        Index("ix_usage_records_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<UsageRecord user={self.user_id} module={self.module} "
            f"tokens={self.tokens_used} cost={self.cost_usd} credits={self.unit_cost_credits}>"
        )
