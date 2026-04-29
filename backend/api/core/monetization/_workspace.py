"""Workspace compatibility helpers for the monetization core."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.models.workspace_billing import CreditBalance, Member, Workspace


async def ensure_owner_workspace(user: User, db: AsyncSession) -> Workspace:
    """
    Create the compatibility workspace for a user if it does not exist yet.

    During the transition period the workspace id is aligned with the owner user id
    so legacy user-centric code can safely pass user.id as workspaceId.
    """
    result = await db.execute(select(Workspace).where(Workspace.id == user.id))
    workspace = result.scalar_one_or_none()
    if workspace is None:
        display_name = (user.full_name or user.email or "Nanovia Workspace").strip() or "Nanovia Workspace"
        workspace = Workspace(
            id=user.id,
            owner_user_id=user.id,
            slug=None,
            name=display_name,
            status="active",
            active_plan_key=user.plan,
            billing_email=user.email,
        )
        db.add(workspace)
    else:
        workspace.active_plan_key = user.plan
        workspace.billing_email = user.email
        workspace.name = (user.full_name or workspace.name or user.email or "Nanovia Workspace").strip() or "Nanovia Workspace"

    member_result = await db.execute(
        select(Member).where(
            Member.workspace_id == user.id,
            Member.email == user.email,
        )
    )
    member = member_result.scalar_one_or_none()
    if member is None:
        db.add(
            Member(
                workspace_id=user.id,
                user_id=user.id,
                email=user.email,
                role="owner",
                status="active",
                accepted_at=user.created_at,
            )
        )

    balance_result = await db.execute(
        select(CreditBalance).where(CreditBalance.workspace_id == user.id)
    )
    credit_balance = balance_result.scalar_one_or_none()
    current_balance = int(getattr(user, "credits", 0) or 0)
    if credit_balance is None:
        db.add(
            CreditBalance(
                workspace_id=user.id,
                balance=current_balance,
            )
        )
    else:
        credit_balance.balance = current_balance

    await db.flush()
    return workspace


async def get_workspace(workspace_id: str | uuid.UUID, db: AsyncSession) -> Workspace | None:
    try:
        workspace_uuid = uuid.UUID(str(workspace_id))
    except ValueError:
        return None

    result = await db.execute(select(Workspace).where(Workspace.id == workspace_uuid))
    workspace = result.scalar_one_or_none()
    if workspace is not None:
        return workspace

    user_result = await db.execute(select(User).where(User.id == workspace_uuid))
    user = user_result.scalar_one_or_none()
    if user is None:
        return None

    return await ensure_owner_workspace(user, db)


def workspace_is_active(workspace: Workspace) -> bool:
    return (workspace.status or "active") == "active"


async def get_workspace_owner(workspace_id: str | uuid.UUID, db: AsyncSession) -> User:
    """Resolve the owner record backing a workspace during the transition period."""
    workspace = await get_workspace(workspace_id, db)
    if workspace is not None:
        result = await db.execute(select(User).where(User.id == workspace.owner_user_id))
        user = result.scalar_one_or_none()
        if user is None:
            raise ValueError(f"Workspace {workspace_id!r} owner not found")
        return user

    try:
        owner_id = uuid.UUID(str(workspace_id))
    except ValueError as exc:
        raise ValueError(f"Invalid workspaceId: {workspace_id!r}") from exc

    result = await db.execute(select(User).where(User.id == owner_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"Workspace {workspace_id!r} not found")
    await ensure_owner_workspace(user, db)
    return user
