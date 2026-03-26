"""
backend/api/routers/users.py — User profile management
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.deps import CurrentUser, DB
from api.core.security import hash_password, verify_password
from api.schemas.auth import UserPublic

router = APIRouter()


class UpdateProfileRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/me", response_model=UserPublic)
async def get_profile(current_user: CurrentUser):
    return UserPublic.model_validate(current_user)


@router.patch("/me", response_model=UserPublic)
async def update_profile(body: UpdateProfileRequest, current_user: CurrentUser, db: DB):
    if body.full_name is not None:
        current_user.full_name = body.full_name
    db.add(current_user)
    return UserPublic.model_validate(current_user)


@router.post("/me/change-password", status_code=204)
async def change_password(body: ChangePasswordRequest, current_user: CurrentUser, db: DB):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)

