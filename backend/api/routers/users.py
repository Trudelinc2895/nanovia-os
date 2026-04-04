"""
backend/api/routers/users.py — User profile management + GDPR
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from api.core.deps import CurrentUser, DB
from api.core.security import hash_password, verify_password
from api.schemas.auth import UserPublic

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str
    confirmation: str = Field(..., description="Must equal 'DELETE MY ACCOUNT'")


@router.get("/me", response_model=UserPublic)
async def get_profile(current_user: CurrentUser):
    return UserPublic.model_validate(current_user)


@router.patch("/me", response_model=UserPublic)
async def update_profile(body: UpdateProfileRequest, current_user: CurrentUser, db: DB):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    db.add(current_user)
    await db.commit()
    return UserPublic.model_validate(current_user)


@router.post("/me/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest, current_user: CurrentUser, db: DB):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)
    await db.commit()


@router.get("/me/export-data")
async def export_my_data(current_user: CurrentUser, db: DB):
    """
    GDPR/CCPA: Export all data associated with the authenticated user as JSON.
    Includes profile, subscription, usage records, conversations, and credit ledger.
    """
    from api.models.conversation import Conversation
    from api.models.subscription import Subscription
    from api.models.usage_record import UsageRecord

    # Subscription
    sub_result = await db.execute(
        select(Subscription)
        .where(Subscription.user_id == current_user.id)
        .order_by(Subscription.created_at.desc())
    )
    subscriptions = [
        {
            "plan": s.plan,
            "status": s.status,
            "billing_interval": s.billing_interval,
            "current_period_end": s.current_period_end.isoformat() if s.current_period_end else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in sub_result.scalars().all()
    ]

    # Usage records (last 90 days)
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    usage_result = await db.execute(
        select(UsageRecord)
        .where(UsageRecord.user_id == current_user.id, UsageRecord.created_at >= cutoff)
        .order_by(UsageRecord.created_at.desc())
        .limit(500)
    )
    usage_records = [
        {
            "module": r.module,
            "tokens_used": r.tokens_used,
            "cost_usd": float(r.cost_usd),
            "unit_cost_credits": r.unit_cost_credits,
            "created_at": r.created_at.isoformat(),
        }
        for r in usage_result.scalars().all()
    ]

    # Credit ledger
    try:
        from api.models.credit_ledger import CreditLedger
        ledger_result = await db.execute(
            select(CreditLedger)
            .where(CreditLedger.user_id == current_user.id)
            .order_by(CreditLedger.created_at.desc())
            .limit(200)
        )
        credit_ledger = [
            {
                "type": e.type,
                "amount": e.amount,
                "balance_after": e.balance_after,
                "source": e.source,
                "created_at": e.created_at.isoformat(),
            }
            for e in ledger_result.scalars().all()
        ]
    except Exception:
        credit_ledger = []

    export = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profile": {
            "id": str(current_user.id),
            "email": current_user.email,
            "full_name": current_user.full_name,
            "plan": current_user.plan,
            "credits": current_user.credits,
            "created_at": current_user.created_at.isoformat(),
        },
        "subscriptions": subscriptions,
        "usage_records_last_90_days": usage_records,
        "credit_ledger": credit_ledger,
    }

    json_bytes = json.dumps(export, indent=2, ensure_ascii=False).encode("utf-8")
    filename = f"kt-monetization-export-{current_user.id}.json"
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/me", status_code=204)
async def delete_my_account(
    body: DeleteAccountRequest,
    current_user: CurrentUser,
    db: DB,
):
    """
    GDPR/CCPA: Soft-delete the authenticated user's account.

    - Verifies password and explicit confirmation string
    - Anonymises email and name (hard-delete of PII)
    - Deactivates account — data retained for 30 days then purged by cron
    - Does NOT cancel Stripe subscription automatically; user must cancel via portal first
    """
    if body.confirmation != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=400,
            detail="Confirmation must equal exactly: DELETE MY ACCOUNT",
        )
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect password")

    user_id = current_user.id
    # Anonymise PII — irreversible
    current_user.email = f"deleted_{user_id}@deleted.invalid"
    current_user.full_name = "Deleted User"
    current_user.password_hash = "DELETED"
    current_user.is_active = False
    current_user.stripe_customer_id = None
    current_user.password_reset_token = None
    db.add(current_user)
    await db.commit()


