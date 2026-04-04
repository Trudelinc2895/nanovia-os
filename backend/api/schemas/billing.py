"""
backend/api/schemas/billing.py — Billing request/response schemas
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PlanLimits(BaseModel):
    ai_messages_per_month: int
    conversations: int
    active_modules: int
    api_calls_per_day: int
    storage_gb: int


class FeatureGates(BaseModel):
    api_access: bool
    white_label: bool
    priority_support: bool
    advanced_analytics: bool
    custom_modules: bool
    automation: bool
    team_seats: bool
    data_export: bool
    overage_allowed: bool
    early_access: bool


class UpsellSuggestion(BaseModel):
    next_plan: str
    next_plan_name: str
    price_monthly_usd: int
    price_yearly_usd: int
    yearly_discount_pct: int
    yearly_savings_usd: int
    trigger: str | None
    headline: str
    new_features: list[str]


class PlanPublic(BaseModel):
    slug: str
    name: str
    price_monthly_usd: int
    price_yearly_usd: int
    yearly_discount_pct: int
    trial_days: int
    support_level: str
    limits: PlanLimits
    features: list[str]
    features_enabled: FeatureGates


class CheckoutRequest(BaseModel):
    plan: str = Field(..., pattern="^(pro|business)$")
    interval: str = Field(default="monthly", pattern="^(monthly|yearly)$")


class CheckoutResponse(BaseModel):
    url: str


class PortalResponse(BaseModel):
    url: str


class SubscriptionInfo(BaseModel):
    id: str | None
    plan: str
    status: str
    current_period_end: str | None
    cancel_at_period_end: bool
    billing_interval: str | None = None


class UsageResponse(BaseModel):
    month: str
    messages_count: int
    messages_limit: int          # -1 = unlimited
    usage_pct: float             # 0–100, -1 if unlimited
    tokens_total: int
    cost_usd_total: float
    credits_remaining: int


class EntitlementsResponse(BaseModel):
    plan: str
    status: str
    limits: dict[str, Any]
    features: list[str]
    features_enabled: dict[str, bool]
    credits: int
    subscription: dict[str, Any]
    upsell: dict[str, Any] | None


class CreditPurchaseRequest(BaseModel):
    quantity: int = Field(default=1, ge=1, le=100)


class CreditPurchaseResponse(BaseModel):
    url: str
    credits_to_add: int


# ─── Add-ons ──────────────────────────────────────────────────────────────────

class AddonPublic(BaseModel):
    slug: str
    name: str
    description: str
    price_usd: int
    type: str
    grants: dict[str, int]


class AddonCheckoutRequest(BaseModel):
    addon: str = Field(..., description="Add-on slug (e.g. api_calls_500, storage_10gb, credits_50)")


class AddonCheckoutResponse(BaseModel):
    url: str
    addon_name: str
    price_usd: int


# ─── Analytics ────────────────────────────────────────────────────────────────

class UsageHistoryItem(BaseModel):
    id: str
    module: str
    tokens_used: int
    cost_usd: float
    created_at: str


class ModuleBreakdownItem(BaseModel):
    module: str
    message_count: int
    tokens_total: int
    cost_usd_total: float


class UsageHistoryResponse(BaseModel):
    days: int
    records: list[UsageHistoryItem]
    breakdown: list[ModuleBreakdownItem]
    total_messages: int
    total_tokens: int
    total_cost_usd: float


# ─── Gamification ─────────────────────────────────────────────────────────────

class MilestoneStatus(BaseModel):
    key: str
    label: str
    icon: str
    unlocked: bool


class MilestonesResponse(BaseModel):
    milestones: list[MilestoneStatus]
    total_unlocked: int
    total: int
    progress_pct: float
