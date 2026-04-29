"""Custom module generator — Business tier only."""
from __future__ import annotations
import re
import uuid
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.database import get_db
from api.core.deps import CurrentUser
from api.models.custom_module import CustomModule
from api.models.audit import AuditLog

router = APIRouter()

def _require_business(user) -> None:
    """Raises 403 if user is not on Business plan."""
    plan = getattr(user, "plan", "free") or "free"
    if plan not in {"business"}:
        raise HTTPException(status_code=403, detail="Custom modules require a Business plan or higher")

def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]

class CustomModuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    prompt_template: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3 or len(v) > 80:
            raise ValueError("Name must be 3–80 characters")
        return v

    @field_validator("prompt_template")
    @classmethod
    def validate_template(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("Prompt template must be at least 10 characters")
        if len(v) > 10000:
            raise ValueError("Prompt template must be under 10,000 characters")
        return v

class CustomModuleResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str]
    prompt_template: str
    is_active: bool
    created_at: datetime
    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_safe(cls, obj: CustomModule) -> "CustomModuleResponse":
        return cls(
            id=str(obj.id),
            name=obj.name,
            slug=obj.slug,
            description=obj.description,
            prompt_template=obj.prompt_template,
            is_active=obj.is_active,
            created_at=obj.created_at,
        )

@router.get("/modules/custom", response_model=list[CustomModuleResponse])
async def list_custom_modules(
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_business(user)
    result = await db.execute(
        select(CustomModule)
        .where(CustomModule.owner_user_id == user.id, CustomModule.is_active == True)  # noqa: E712
        .order_by(CustomModule.created_at.desc())
    )
    return [CustomModuleResponse.from_orm_safe(m) for m in result.scalars().all()]

@router.post("/modules/custom", response_model=CustomModuleResponse, status_code=201)
async def create_custom_module(
    body: CustomModuleCreate,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_business(user)
    slug = _slugify(body.name)
    existing = await db.execute(
        select(CustomModule).where(CustomModule.owner_user_id == user.id, CustomModule.slug == slug)
    )
    if existing.scalar_one_or_none():
        slug = slug + "-" + str(uuid.uuid4())[:8]
    module = CustomModule(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name=body.name,
        slug=slug,
        description=body.description,
        prompt_template=body.prompt_template,
    )
    db.add(module)
    db.add(AuditLog(
        user_id=user.id,
        action="custom_module.created",
        resource=f"module:{slug}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status="success",
    ))
    await db.commit()
    await db.refresh(module)
    return CustomModuleResponse.from_orm_safe(module)

@router.delete("/modules/custom/{module_id}", status_code=204)
async def delete_custom_module(
    module_id: str,
    request: Request,
    user: CurrentUser,
    db: AsyncSession = Depends(get_db),
):
    _require_business(user)
    try:
        mid = uuid.UUID(module_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid module ID")
    result = await db.execute(
        select(CustomModule).where(CustomModule.id == mid, CustomModule.owner_user_id == user.id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    module.is_active = False
    db.add(AuditLog(
        user_id=user.id,
        action="custom_module.deleted",
        resource=f"module:{module.slug}",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        status="success",
    ))
    await db.commit()
