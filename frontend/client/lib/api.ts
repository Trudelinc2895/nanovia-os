/**
 * lib/api.ts — typed API client for frontend web
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (res.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return apiFetch<T>(path, options, false);
    }
    // Token invalid — redirect to login
    if (typeof window !== "undefined") {
      _accessToken = null;
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    throw new Error("Session expirée");
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "API Error");
  }

  if (res.status === 204) return {} as T;
  return res.json();
}

async function refreshAccessToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) return false;

  try {
    const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    _accessToken = data.access_token;
    if (data.refresh_token) {
      localStorage.setItem("refresh_token", data.refresh_token);
    }
    return true;
  } catch {
    return false;
  }
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  plan: string;
  is_active: boolean;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const data = await apiFetch<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  setAccessToken(data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return data;
}

export async function register(
  email: string,
  password: string,
  full_name?: string
): Promise<LoginResponse> {
  const data = await apiFetch<LoginResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name }),
  });
  setAccessToken(data.access_token);
  localStorage.setItem("refresh_token", data.refresh_token);
  return data;
}

export async function forgotPassword(email: string): Promise<void> {
  await apiFetch<void>("/api/v1/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(token: string, new_password: string): Promise<void> {
  await apiFetch<void>("/api/v1/auth/reset-password", {
    method: "POST",
    body: JSON.stringify({ token, new_password }),
  });
}

export async function getMe(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me");
}

export async function logout(): Promise<void> {
  try {
    await apiFetch("/api/v1/auth/logout", { method: "POST" });
  } catch {}
  setAccessToken(null);
  localStorage.removeItem("refresh_token");
}

// ── AI Orchestrator ───────────────────────────────────────────────────────────

export interface OrchestrateResponse {
  response: string;
  agent_used: string;
  agent_name: string;
  confidence: number;
  conversation_id: string;
  session_id: string;
}

export async function orchestrate(
  message: string,
  conversation_id?: string | null
): Promise<OrchestrateResponse> {
  return apiFetch<OrchestrateResponse>("/api/v1/orchestrate", {
    method: "POST",
    body: JSON.stringify({ message, conversation_id }),
  });
}

export async function listAgents() {
  return apiFetch<Array<{ key: string; name: string; description: string }>>(
    "/api/v1/orchestrate/agents"
  );
}

// ── Billing ───────────────────────────────────────────────────────────────────

export interface PlanLimits {
  ai_messages_per_month: number;
  conversations: number;
  active_modules: number;
  api_calls_per_day: number;
  storage_gb: number;
}

export interface FeatureGates {
  api_access: boolean;
  white_label: boolean;
  priority_support: boolean;
  advanced_analytics: boolean;
  custom_modules: boolean;
  automation: boolean;
  team_seats: boolean;
  data_export: boolean;
  overage_allowed: boolean;
  early_access: boolean;
}

export interface Plan {
  slug: string;
  name: string;
  price_monthly_usd: number;
  price_yearly_usd: number;
  yearly_discount_pct: number;
  trial_days: number;
  support_level: string;
  limits: PlanLimits;
  features: string[];
  features_enabled: FeatureGates;
}

export interface UpsellSuggestion {
  next_plan: string;
  next_plan_name: string;
  price_monthly_usd: number;
  price_yearly_usd: number;
  yearly_discount_pct: number;
  yearly_savings_usd: number;
  trigger: string | null;
  headline: string;
  new_features: string[];
}

export interface Entitlements {
  plan: string;
  status: string;
  limits: PlanLimits;
  features: string[];
  features_enabled: FeatureGates;
  credits: number;
  subscription: {
    id: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    billing_interval: string | null;
  };
  upsell: UpsellSuggestion | null;
}

export interface UsageStats {
  month: string;
  messages_count: number;
  messages_limit: number;
  usage_pct: number;
  tokens_total: number;
  cost_usd_total: number;
  credits_remaining: number;
}

export interface AddonPublic {
  slug: string;
  name: string;
  description: string;
  price_usd: number;
  type: string;
  grants: Record<string, number>;
}

export async function getPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>("/api/v1/billing/plans");
}

export async function getEntitlements(): Promise<Entitlements> {
  return apiFetch<Entitlements>("/api/v1/billing/entitlements");
}

export async function getUsageStats(): Promise<UsageStats> {
  return apiFetch<UsageStats>("/api/v1/billing/usage");
}

export async function getUpsell(): Promise<UpsellSuggestion | null> {
  return apiFetch<UpsellSuggestion | null>("/api/v1/billing/upsell");
}

export async function getAddons(): Promise<AddonPublic[]> {
  return apiFetch<AddonPublic[]>("/api/v1/billing/addons");
}

export async function createCheckoutSession(plan: string, interval: "monthly" | "yearly") {
  return apiFetch<{ url: string }>("/api/v1/billing/checkout-session", {
    method: "POST",
    body: JSON.stringify({ plan, interval }),
  });
}

export async function createAddonCheckout(addon: string) {
  return apiFetch<{ url: string; addon_name: string; price_usd: number }>(
    "/api/v1/billing/addon/checkout",
    { method: "POST", body: JSON.stringify({ addon }) }
  );
}

export async function createPortalSession() {
  return apiFetch<{ url: string }>("/api/v1/billing/portal-session", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export interface ModuleBreakdown {
  module: string;
  message_count: number;
  tokens_total: number;
  cost_usd_total: number;
}

export interface UsageHistory {
  days: number;
  records: Array<{
    id: string;
    module: string;
    tokens_used: number;
    cost_usd: number;
    created_at: string;
  }>;
  breakdown: ModuleBreakdown[];
  total_messages: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface Milestone {
  key: string;
  label: string;
  icon: string;
  unlocked: boolean;
}

export interface MilestonesData {
  milestones: Milestone[];
  total_unlocked: number;
  total: number;
  progress_pct: number;
}

export async function getUsageHistory(days = 30): Promise<UsageHistory> {
  return apiFetch<UsageHistory>(`/api/v1/analytics/history?days=${days}`);
}

export async function getModuleBreakdown(days = 30): Promise<{ days: number; breakdown: ModuleBreakdown[] }> {
  return apiFetch(`/api/v1/analytics/breakdown?days=${days}`);
}

export async function getMilestones(): Promise<MilestonesData> {
  return apiFetch<MilestonesData>("/api/v1/analytics/milestones");
}

export function getExportUrl(): string {
  return `${API_URL}/api/v1/analytics/export`;
}

// ── Modules ───────────────────────────────────────────────────────────────────

export async function getModuleCatalog() {
  return apiFetch<Array<{ key: string; name: string; description: string; is_available: boolean }>>(
    "/api/v1/modules/catalog"
  );
}
