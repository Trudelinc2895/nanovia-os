from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from api.services import ai_service, context_builder, model_policy, safety_guard, sandbox_service, usage_meter
from api.services import prompt_registry
from api.services import private_orchestrator_service


def _default_allowed_modules(workspace_id: str) -> list[str]:
    entitlements = sandbox_service.get_entitlements(workspace_id)
    enabled = [key for key, value in entitlements.get("modules", {}).items() if value]
    if "ai_orchestrator" not in enabled:
        enabled.append("ai_orchestrator")
    return sorted(set(enabled))


def get_or_create_profile(tenant_id: str, workspace_id: str, *, owner_email: str | None = None) -> dict[str, Any]:
    tenant_id = safety_guard.ensure_safe_identifier(tenant_id, field_name="tenant_id")
    workspace_id = safety_guard.ensure_safe_identifier(workspace_id, field_name="workspace_id")
    existing = ai_service.get_profile(tenant_id, workspace_id)
    if existing:
        if existing.get("workspace_id") != workspace_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Profile workspace mismatch.")
        return existing

    workspace = sandbox_service.get_workspace(workspace_id)
    plan = str(workspace.get("plan", "starter")).lower()
    profile = {
        "id": f"profile_{tenant_id}",
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "display_name": workspace.get("workspace_name", tenant_id),
        "tone": "professional",
        "business_context": "Nanovia tenant workspace",
        "allowed_modules": _default_allowed_modules(workspace_id),
        "allowed_tools": ["knowledge_search", "usage_dashboard"] if model_policy.tools_enabled(plan) else [],
        "memory_enabled": model_policy.memory_enabled(plan),
        "learning_opt_in": False,
        "plan": plan,
        "billing_status": workspace.get("subscription_status", "inactive"),
        "memory_namespace": str(ai_service.tenant_memory_dir(tenant_id)),
        "owner_email": owner_email or workspace.get("owner_email"),
        "created_at": ai_service.utcnow(),
        "updated_at": ai_service.utcnow(),
    }
    return ai_service.upsert_profile(tenant_id, profile, workspace_id)


def update_profile(tenant_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    tenant_id = safety_guard.ensure_safe_identifier(tenant_id, field_name="tenant_id")
    profile = ai_service.get_profile(tenant_id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant AI profile not found.")
    editable_fields = {"display_name", "tone", "business_context", "allowed_tools", "learning_opt_in"}
    for key, value in patch.items():
        if key in editable_fields and value is not None:
            profile[key] = value
    profile["updated_at"] = ai_service.utcnow()
    return ai_service.upsert_profile(tenant_id, profile, str(profile.get("workspace_id", "") or ""))


async def tenant_chat(*, tenant_id: str, workspace_id: str, user_id: str | None, message: str, force_agent: str | None = None) -> dict[str, Any]:
    ai_service.ensure_runtime_layout()
    safety_guard.ensure_no_live_key_in_sandbox()
    tenant_id = safety_guard.ensure_safe_identifier(tenant_id, field_name="tenant_id")
    workspace_id = safety_guard.ensure_safe_identifier(workspace_id, field_name="workspace_id")
    profile = get_or_create_profile(tenant_id, workspace_id)
    safety_guard.ensure_tenant_isolation(tenant_id, profile.get("tenant_id"))
    if profile.get("workspace_id") != workspace_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant workspace mismatch.")

    workspace = sandbox_service.get_workspace(workspace_id)
    safety_guard.ensure_subscription_active(workspace)
    safety_guard.ensure_module_allowed("ai_orchestrator", profile)

    prompt = prompt_registry.load_prompt("tenant_base_prompt.md")
    model = model_policy.select_model(profile.get("plan", "starter"))
    conversation = ai_service.get_or_create_conversation("tenant", tenant_id=tenant_id, user_id=user_id)
    history = ai_service.conversation_messages(conversation["id"])
    scored_agents = private_orchestrator_service.score_agents(
        message,
        allowed_agent_keys=["operator", "ghost_agency", "decision_engine"],
        force_agent=force_agent,
    )
    route_preview = {
        "selected_agent_key": scored_agents[0]["key"],
        "selected_agent_name": scored_agents[0]["name"],
        "intent": private_orchestrator_service.classify_intent(message),
        "memory": private_orchestrator_service.build_memory_snapshot(history),
    }
    context = context_builder.build_tenant_context(
        tenant_id=tenant_id,
        profile=profile,
        message=message,
        context_limit=model_policy.max_context_messages(profile.get("plan", "starter")),
    )

    input_tokens = ai_service.estimate_tokens(prompt, message, context)
    quoted = usage_meter.quote_usage(profile.get("plan", "starter"), model, input_tokens, 32)
    safety_guard.ensure_credits_available(workspace_id, int(quoted["credits_charged"]), profile.get("plan", "starter"))

    ai_service.append_conversation_message(conversation["id"], "user", message, input_tokens=input_tokens, cost_estimate=quoted["estimated_openai_cost_usd"])
    response_text = ai_service.render_tenant_response(message=message, profile=profile, route_preview=route_preview, context=context)
    output_tokens = ai_service.estimate_tokens(response_text)
    usage = usage_meter.record_tenant_usage(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        reason="tenant ai chat",
    )
    ai_service.append_conversation_message(
        conversation["id"],
        "assistant",
        response_text,
        output_tokens=output_tokens,
        cost_estimate=usage["quote"]["estimated_openai_cost_usd"],
    )
    ai_service.log_audit(
        "tenant",
        "ai_chat",
        tenant_id=tenant_id,
        user_id=user_id,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=usage["quote"]["estimated_openai_cost_usd"],
        credits_charged=usage["quote"]["credits_charged"],
        status_value="success",
    )
    return {
        "conversation_id": conversation["id"],
        "tenant_id": tenant_id,
        "workspace_id": workspace_id,
        "model": model,
        "prompt_name": "tenant_base_prompt.md",
        "prompt_preview": prompt[:160],
        "response": response_text,
        "route_preview": route_preview,
        "usage": usage["event"],
        "policy": model_policy.plan_policy(profile.get("plan", "starter")),
    }


def usage(tenant_id: str, workspace_id: str) -> dict[str, Any]:
    return usage_meter.tenant_usage_summary(tenant_id, workspace_id)
