"""White-label branding endpoints (admin-only)."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.database import get_db
from api.core.deps import AdminUser
from api.models.branding import Branding
from api.models.audit import AuditLog
import uuid

router = APIRouter()

class BrandingUpdate(BaseModel):
    company_name: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    accent_color: Optional[str] = None
    support_email: Optional[str] = None
    custom_domain: Optional[str] = None

    @field_validator("primary_color", "accent_color")
    @classmethod
    def validate_hex(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.startswith("#") or len(v) not in {4, 7}:
            raise ValueError("Color must be a valid hex code like #FF5500")
        return v

class BrandingResponse(BaseModel):
    workspace_id: str
    company_name: Optional[str]
    logo_url: Optional[str]
    primary_color: Optional[str]
    accent_color: Optional[str]
    support_email: Optional[str]
    custom_domain: Optional[str]
    model_config = {"from_attributes": True}

_DEFAULT_WORKSPACE = "platform"

@router.get("/admin/branding", response_model=BrandingResponse)
async def get_branding(
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Branding).where(Branding.workspace_id == _DEFAULT_WORKSPACE))
    row = result.scalar_one_or_none()
    if row is None:
        return BrandingResponse(workspace_id=_DEFAULT_WORKSPACE, company_name=None, logo_url=None,
                                primary_color=None, accent_color=None, support_email=None, custom_domain=None)
    return BrandingResponse.model_validate(row)

@router.put("/admin/branding", response_model=BrandingResponse)
async def update_branding(
    body: BrandingUpdate,
    request: Request,
    _admin: AdminUser,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Branding).where(Branding.workspace_id == _DEFAULT_WORKSPACE))
    row = result.scalar_one_or_none()
    if row is None:
        row = Branding(id=uuid.uuid4(), workspace_id=_DEFAULT_WORKSPACE)
        db.add(row)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.add(AuditLog(
        user_id=_admin.id,
        action="branding.updated",
        resource=f"workspace:{_DEFAULT_WORKSPACE}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status="success",
    ))
    await db.commit()
    await db.refresh(row)
    return BrandingResponse.model_validate(row)
