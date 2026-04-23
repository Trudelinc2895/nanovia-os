"""Schemas for the private/admin-only orchestrator slice."""
from __future__ import annotations

from pydantic import BaseModel


class PrivateOrchestratorAccessBoundary(BaseModel):
    admin_only: bool = True
    feature_flagged: bool = True
    public_saas_exposure: bool = False
    destructive_merge_with_my_agent_hub: bool = False
    requires_private_admin_surface: bool = True
    production_ip_allowlist_required: bool = True


class PrivateOrchestratorCapabilityMatrix(BaseModel):
    agent_catalog_read: bool = True
    upstream_health_read: bool = True
    planner_preview: bool = True
    agent_routing: bool = True
    conversation_memory: bool = True
    result_scoring: bool = True
    prompt_execution: bool = False
    terminal_access: bool = False
    filesystem_access: bool = False
    browser_access: bool = False
    billing_mutation: bool = False
    user_impersonation: bool = False


class PrivateOrchestratorUpstreamHealth(BaseModel):
    ok: bool
    status: str
    service: str | None = None
    version: str | None = None
    detail: str | None = None


class PrivateOrchestratorAgent(BaseModel):
    key: str
    name: str
    description: str
    allowed: bool = True


class PrivateOrchestratorRouteCandidate(BaseModel):
    key: str
    name: str
    score: float
    reasons: list[str]


class PrivateOrchestratorMemorySnapshot(BaseModel):
    message_count: int
    recent_messages: list[dict[str, str]]
    summary: str


class PrivateOrchestratorRoutePreview(BaseModel):
    selected_agent_key: str
    selected_agent_name: str
    confidence: float
    force_agent_applied: bool = False
    intent: str
    required_capabilities: list[str]
    memory: PrivateOrchestratorMemorySnapshot
    candidates: list[PrivateOrchestratorRouteCandidate]
    upstream: PrivateOrchestratorUpstreamHealth
    conversation_id: str | None = None


class PrivateOrchestratorOverview(BaseModel):
    context_key: str
    enabled: bool
    release_stage: str
    access: PrivateOrchestratorAccessBoundary
    capabilities: PrivateOrchestratorCapabilityMatrix
    allowed_agent_keys: list[str]
    upstream: PrivateOrchestratorUpstreamHealth
    endpoints: list[str]
    notes: list[str]


class PrivateOrchestratorAgentsResponse(BaseModel):
    enabled: bool
    source: str
    agents: list[PrivateOrchestratorAgent]
