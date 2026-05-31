from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.services import ai_service, learning_service, master_ai_service, prompt_registry, safety_guard, tenant_ai_service, usage_meter

router = APIRouter()


class TenantChatRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3)
    workspace_id: str | None = Field(default=None, min_length=3)
    user_id: str | None = None
    message: str = Field(..., min_length=1)
    force_agent: str | None = None


class MasterChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: str | None = None
    master_context: bool = False


class TenantProfilePatch(BaseModel):
    display_name: str | None = None
    tone: str | None = None
    business_context: str | None = None
    allowed_tools: list[str] | None = None
    learning_opt_in: bool | None = None


class MemorySaveRequest(BaseModel):
    scope: Literal["master", "tenant", "shared_learning"]
    content: str = Field(..., min_length=1)
    tenant_id: str | None = None
    master_context: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class LearningExtractRequest(BaseModel):
    source_scope: Literal["master", "tenant", "shared_learning"]
    content: str = Field(..., min_length=1)
    tenant_id: str | None = None
    category: str | None = None
    confidence: float = 0.75
    frequency: int = 1
    master_context: bool = False


class PromptUpdateRequest(BaseModel):
    prompt_name: str = Field(..., min_length=3)
    content: str = Field(..., min_length=1)
    actor: str = "super-admin"
    master_context: bool = False


@router.post("/ai/tenant/chat")
async def post_tenant_chat(payload: TenantChatRequest, authorization: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    actor_user_id = safety_guard.ensure_actor_matches_claim(payload.user_id, claims)
    tenant_id, workspace_id = safety_guard.resolve_tenant_access(
        claims,
        requested_tenant_id=payload.tenant_id,
        requested_workspace_id=payload.workspace_id,
    )
    return await tenant_ai_service.tenant_chat(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        user_id=actor_user_id,
        message=payload.message,
        force_agent=payload.force_agent,
    )


@router.post("/ai/master/chat")
async def post_master_chat(
    payload: MasterChatRequest,
    authorization: str | None = Header(None),
    x_nanovia_admin_key: str | None = Header(None),
) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    actor_user_id = safety_guard.ensure_master_identity(payload.master_context, claims, x_nanovia_admin_key)
    return await master_ai_service.master_chat(
        message=payload.message,
        user_id=actor_user_id,
    )


@router.get("/ai/tenant/profile")
def get_tenant_profile(tenant_id: str | None = Query(None), workspace_id: str | None = Query(None), authorization: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    effective_tenant_id, effective_workspace_id = safety_guard.resolve_tenant_access(
        claims,
        requested_tenant_id=tenant_id,
        requested_workspace_id=workspace_id,
    )
    return tenant_ai_service.get_or_create_profile(effective_tenant_id, effective_workspace_id)


@router.patch("/ai/tenant/profile")
def patch_tenant_profile(tenant_id: str | None = Query(None), payload: TenantProfilePatch = Body(...), authorization: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    effective_tenant_id, _ = safety_guard.resolve_tenant_access(claims, requested_tenant_id=tenant_id)
    return tenant_ai_service.update_profile(effective_tenant_id, payload.model_dump(exclude_none=True))


@router.get("/ai/usage")
def get_ai_usage(tenant_id: str | None = Query(None), workspace_id: str | None = Query(None), authorization: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    effective_tenant_id, effective_workspace_id = safety_guard.resolve_tenant_access(
        claims,
        requested_tenant_id=tenant_id,
        requested_workspace_id=workspace_id,
    )
    return tenant_ai_service.usage(effective_tenant_id, effective_workspace_id)


@router.get("/admin/ai/usage")
def get_admin_ai_usage(master_context: bool = Query(False), authorization: str | None = Header(None), x_nanovia_admin_key: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    safety_guard.ensure_master_identity(master_context, claims, x_nanovia_admin_key)
    return usage_meter.global_usage_summary()


@router.get("/admin/ai/learning")
def get_admin_ai_learning(master_context: bool = Query(False), authorization: str | None = Header(None), x_nanovia_admin_key: str | None = Header(None)) -> list[dict[str, Any]]:
    claims = safety_guard.authenticate_access_token(authorization)
    safety_guard.ensure_master_identity(master_context, claims, x_nanovia_admin_key)
    return learning_service.list_learning()


@router.post("/admin/ai/learning/extract")
def post_admin_ai_learning_extract(payload: LearningExtractRequest, authorization: str | None = Header(None), x_nanovia_admin_key: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    safety_guard.ensure_master_identity(payload.master_context, claims, x_nanovia_admin_key)
    return learning_service.extract_learning_event(
        source_scope=payload.source_scope,
        content=payload.content,
        tenant_id=payload.tenant_id,
        category=payload.category,
        confidence=payload.confidence,
        frequency=payload.frequency,
    )


@router.post("/admin/ai/prompt/update")
def post_admin_ai_prompt_update(payload: PromptUpdateRequest, authorization: str | None = Header(None), x_nanovia_admin_key: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    safety_guard.ensure_master_identity(payload.master_context, claims, x_nanovia_admin_key)
    safety_guard.ensure_no_secret_in_memory(payload.content)
    return prompt_registry.update_prompt(payload.prompt_name, payload.content, actor=payload.actor)


@router.post("/ai/memory/save")
def post_ai_memory_save(payload: MemorySaveRequest, authorization: str | None = Header(None), x_nanovia_admin_key: str | None = Header(None)) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    safety_guard.ensure_no_secret_in_memory(payload.content)
    if payload.scope == "master":
        safety_guard.ensure_master_identity(payload.master_context, claims, x_nanovia_admin_key)
    if payload.scope == "tenant" and not payload.tenant_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="tenant_id required for tenant memory.")
    if payload.scope == "tenant" and payload.tenant_id:
        effective_tenant_id, _ = safety_guard.resolve_tenant_access(claims, requested_tenant_id=payload.tenant_id)
        payload = payload.model_copy(update={"tenant_id": effective_tenant_id})
    if payload.scope == "shared_learning":
        safety_guard.ensure_master_identity(payload.master_context, claims, x_nanovia_admin_key)
        payload = payload.model_copy(update={"content": safety_guard.anonymize_learning_event(payload.content)})
    return ai_service.save_memory(payload.scope, payload.content, tenant_id=payload.tenant_id, metadata=payload.metadata)


@router.get("/ai/memory/search")
def get_ai_memory_search(
    scope: Literal["master", "tenant", "shared_learning"] = Query(...),
    query: str = Query(..., min_length=1),
    tenant_id: str | None = Query(None),
    master_context: bool = Query(False),
    authorization: str | None = Header(None),
    x_nanovia_admin_key: str | None = Header(None),
) -> dict[str, Any]:
    claims = safety_guard.authenticate_access_token(authorization)
    if scope == "master":
        safety_guard.ensure_master_identity(master_context, claims, x_nanovia_admin_key)
    if scope == "shared_learning":
        safety_guard.ensure_master_identity(master_context, claims, x_nanovia_admin_key)
    if scope == "tenant":
        tenant_id, _ = safety_guard.resolve_tenant_access(claims, requested_tenant_id=tenant_id)
    return {"items": ai_service.search_memory(scope, query, tenant_id=tenant_id)}
