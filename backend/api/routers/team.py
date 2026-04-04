"""backend/api/routers/team.py — Team seat management (Business plan only).

Endpoints:
  GET  /team/members      — list team members for current user
  POST /team/invite       — invite a member (requires team_seats feature)
  DELETE /team/members/{member_id} — remove a member
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from api.core.deps import CurrentUser, DB
from api.models.team_member import TeamMember
from api.services.billing_service import PLANS_CONFIG, has_feature

logger = logging.getLogger(__name__)
router = APIRouter()


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "member"


@router.get("/team/members")
async def list_team_members(
    current_user: CurrentUser,
    db: DB,
):
    """List all team members for the authenticated user (workspace owner)."""
    result = await db.execute(
        select(TeamMember)
        .where(TeamMember.owner_id == current_user.id)
        .order_by(TeamMember.invited_at.desc())
    )
    members = result.scalars().all()

    # Get seat limits from plan config
    plan_cfg = PLANS_CONFIG.get(current_user.plan, PLANS_CONFIG["free"])
    seats_limit = plan_cfg["limits"].get("team_seats_max", 1)

    return {
        "members": [
            {
                "id": str(m.id),
                "email": m.member_email,
                "role": m.role,
                "accepted": m.accepted,
                "invited_at": m.invited_at.isoformat(),
                "accepted_at": m.accepted_at.isoformat() if m.accepted_at else None,
            }
            for m in members
        ],
        "seats_used": len(members),
        "seats_limit": seats_limit,
    }


@router.post("/team/invite", status_code=status.HTTP_201_CREATED)
async def invite_member(
    body: InviteRequest,
    current_user: CurrentUser,
    db: DB,
):
    """Invite a team member. Requires team_seats feature (Business plan)."""
    if not has_feature(current_user.plan, "team_seats"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team seats require the Business plan.",
        )

    # Check seat limit
    plan_cfg = PLANS_CONFIG.get(current_user.plan, PLANS_CONFIG["free"])
    seats_limit = plan_cfg["limits"].get("team_seats_max", 1)

    # Check seat limit using SQL COUNT — avoids loading all rows into memory
    count_result = await db.execute(
        select(func.count(TeamMember.id)).where(TeamMember.owner_id == current_user.id)
    )
    current_count = count_result.scalar_one()

    if seats_limit != -1 and current_count >= seats_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Seat limit reached ({seats_limit}). Upgrade to add more members.",
        )

    # Prevent duplicate invites
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.owner_id == current_user.id,
            TeamMember.member_email == body.email,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Member already invited.")

    member = TeamMember(
        owner_id=current_user.id,
        member_email=body.email,
        role=body.role if body.role in ("admin", "member") else "member",
        invited_by=current_user.email,
    )
    db.add(member)
    await db.commit()

    logger.info("[team] %s invited %s as %s", current_user.email, body.email, member.role)
    return {"id": str(member.id), "email": body.email, "role": member.role, "status": "invited"}


@router.delete("/team/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    member_id: uuid.UUID,
    current_user: CurrentUser,
    db: DB,
):
    """Remove a team member. Only the workspace owner can remove members."""
    result = await db.execute(
        select(TeamMember).where(
            TeamMember.id == member_id,
            TeamMember.owner_id == current_user.id,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found.")

    await db.delete(member)
    await db.commit()
    logger.info("[team] %s removed member %s", current_user.email, member.member_email)
