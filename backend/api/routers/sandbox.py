from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from api.services import sandbox_service

router = APIRouter(tags=["sandbox"])


class AgentRouteRequest(BaseModel):
    task: str
    actor: str = "system"
    workspace_id: str = "sandbox_workspace"
    agent_id: str | None = None
    confirm_dangerous_action: bool = False


class MemorySaveRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    actor: str = "memory_agent"


class WorkspacePlanOverrideRequest(BaseModel):
    plan: str
    actor: str = "admin"
    reason: str | None = None


class WorkspaceBlockRequest(BaseModel):
    actor: str = "admin"
    reason: str


class WorkspaceCreditsAdjustRequest(BaseModel):
    amount: int
    actor: str = "admin"
    reason: str


class UsageRecordRequest(BaseModel):
    workspace_id: str = "sandbox_workspace"
    actor: str = "system"
    kind: str = "ai_request"
    model: str = "gpt-4.1-mini"
    units: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    credits: int | None = None
    reason: str | None = None


class CheckoutRequest(BaseModel):
    workspace_id: str = "sandbox_workspace"
    plan: str = "starter"
    success_url: str | None = None
    cancel_url: str | None = None
    actor: str = "admin"


class PortalRequest(BaseModel):
    workspace_id: str = "sandbox_workspace"
    return_url: str | None = None
    actor: str = "admin"


class ModuleToggleRequest(BaseModel):
    enabled: bool
    actor: str = "admin"
    reason: str | None = None


class BotRunRequest(BaseModel):
    workspace_id: str = "sandbox_workspace"
    actor: str = "bot"
    task: str | None = None
    confirm_dangerous_action: bool = False


@router.get("/modules")
def modules() -> list[dict[str, Any]]:
    return sandbox_service.list_modules()


@router.get("/modules/{module_id}")
def module_detail(module_id: str) -> dict[str, Any]:
    return sandbox_service.get_module(module_id)


@router.get("/billing/plans")
def billing_plans() -> list[dict[str, Any]]:
    return sandbox_service.list_plans()


@router.get("/billing/entitlements")
def billing_entitlements(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    return sandbox_service.get_entitlements(workspace_id)


@router.get("/billing/subscription")
def billing_subscription(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    return sandbox_service.get_subscription(workspace_id)


@router.post("/billing/checkout")
def billing_checkout(payload: CheckoutRequest) -> dict[str, Any]:
    return sandbox_service.create_checkout_session(
        workspace_id=payload.workspace_id,
        plan_id=payload.plan,
        success_url=payload.success_url,
        cancel_url=payload.cancel_url,
        actor=payload.actor,
    )


@router.post("/billing/portal")
def billing_portal(payload: PortalRequest) -> dict[str, Any]:
    return sandbox_service.create_portal_session(
        workspace_id=payload.workspace_id,
        return_url=payload.return_url,
        actor=payload.actor,
    )


@router.post("/stripe/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict[str, Any]:
    payload = await request.body()
    return sandbox_service.process_stripe_webhook(payload=payload, stripe_signature=stripe_signature)


@router.get("/credits")
def credits(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    return sandbox_service.get_credits(workspace_id)


@router.get("/usage")
def usage(workspace_id: str = "sandbox_workspace") -> dict[str, Any]:
    return sandbox_service.get_usage(workspace_id)


@router.post("/usage/record")
def usage_record(payload: UsageRecordRequest) -> dict[str, Any]:
    return sandbox_service.record_usage(
        workspace_id=payload.workspace_id,
        actor=payload.actor,
        kind=payload.kind,
        model=payload.model,
        units=payload.units,
        input_tokens=payload.input_tokens,
        output_tokens=payload.output_tokens,
        reason=payload.reason,
        credits_override=payload.credits,
    )


@router.get("/agents")
def agents() -> list[dict[str, Any]]:
    return sandbox_service.list_agents()


@router.post("/agents/route")
def route_agent(payload: AgentRouteRequest) -> dict[str, Any]:
    return sandbox_service.route_agent_task(
        task=payload.task,
        actor=payload.actor,
        workspace_id=payload.workspace_id,
        agent_id=payload.agent_id,
        confirm_dangerous_action=payload.confirm_dangerous_action,
    )


@router.get("/bots")
def bots() -> list[dict[str, Any]]:
    return sandbox_service.list_bots()


@router.post("/bots/{bot_id}/run")
def run_bot(bot_id: str, payload: BotRunRequest) -> dict[str, Any]:
    return sandbox_service.run_bot(
        bot_id=bot_id,
        workspace_id=payload.workspace_id,
        actor=payload.actor,
        task=payload.task,
        confirm_dangerous_action=payload.confirm_dangerous_action,
    )


@router.get("/sandbox/status")
def sandbox_status() -> dict[str, Any]:
    return sandbox_service.get_status()


@router.get("/sandbox/audit")
def sandbox_audit(limit: int = 25) -> list[dict[str, Any]]:
    return sandbox_service.read_audit_entries(limit)


@router.get("/memory")
def memory(limit: int = 25) -> dict[str, Any]:
    return sandbox_service.list_memory(limit)


@router.post("/memory/save")
def memory_save(payload: MemorySaveRequest) -> dict[str, Any]:
    return sandbox_service.save_memory(content=payload.content, actor=payload.actor)


@router.get("/memory/search")
def memory_search(query: str) -> list[dict[str, Any]]:
    return sandbox_service.search_memory(query)


@router.get("/admin/audit")
def admin_audit(limit: int = 50) -> list[dict[str, Any]]:
    return sandbox_service.read_audit_entries(limit)


@router.get("/admin/modules")
def admin_modules() -> list[dict[str, Any]]:
    return sandbox_service.list_admin_modules()


@router.post("/admin/modules/{module_id}/toggle-sandbox")
def admin_toggle_module(module_id: str, payload: ModuleToggleRequest) -> dict[str, Any]:
    return sandbox_service.toggle_module_sandbox(
        module_id=module_id,
        enabled=payload.enabled,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.get("/admin/workspaces")
def admin_workspaces() -> list[dict[str, Any]]:
    return sandbox_service.list_workspaces()


@router.get("/admin/workspaces/{workspace_id}")
def admin_workspace_detail(workspace_id: str) -> dict[str, Any]:
    workspace = sandbox_service.get_workspace(workspace_id)
    return {
        "workspace": workspace,
        "subscription": sandbox_service.get_subscription(workspace_id),
        "entitlements": sandbox_service.get_entitlements(workspace_id),
        "credits": sandbox_service.get_credits(workspace_id),
    }


@router.post("/admin/workspaces/{workspace_id}/override-plan")
def admin_override_plan(workspace_id: str, payload: WorkspacePlanOverrideRequest) -> dict[str, Any]:
    return sandbox_service.override_workspace_plan(
        workspace_id=workspace_id,
        plan=payload.plan,
        actor=payload.actor,
        reason=payload.reason,
    )


@router.post("/admin/workspaces/{workspace_id}/block")
def admin_block_workspace(workspace_id: str, payload: WorkspaceBlockRequest) -> dict[str, Any]:
    return sandbox_service.block_workspace(workspace_id, actor=payload.actor, reason=payload.reason)


@router.post("/admin/workspaces/{workspace_id}/unblock")
def admin_unblock_workspace(workspace_id: str, payload: WorkspaceBlockRequest) -> dict[str, Any]:
    return sandbox_service.unblock_workspace(workspace_id, actor=payload.actor, reason=payload.reason)


@router.post("/admin/workspaces/{workspace_id}/credits/adjust")
def admin_adjust_credits(workspace_id: str, payload: WorkspaceCreditsAdjustRequest) -> dict[str, Any]:
    return sandbox_service.adjust_workspace_credits(
        workspace_id=workspace_id,
        amount=payload.amount,
        actor=payload.actor,
        reason=payload.reason,
    )
