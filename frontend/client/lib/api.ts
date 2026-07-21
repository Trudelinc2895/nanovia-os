/**
 * lib/api.ts — typed API client for frontend web
 */

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "").replace(/\/$/, "");

export function resolveApiUrl(path: string): string {
  return API_URL ? `${API_URL}${path}` : path;
}

function getNetworkErrorMessage(path: string): string {
  if (typeof window === "undefined") {
    return "Impossible de joindre l'API.";
  }

  const host = window.location.hostname;
  const onRawIp = /^(?:\d{1,3}\.){3}\d{1,3}$/.test(host);
  if (onRawIp) {
    return "Impossible de joindre l'API depuis l'IP brute. Utilise https://nanovia.ca pour la connexion.";
  }

  const target = API_URL || "same-origin /api";
  return `Impossible de joindre l'API (${target}) pour ${path}. Verifie le domaine public, le TLS et le reverse proxy.`;
}

let _accessToken: string | null = null;

export function setAccessToken(token: string | null) {
  _accessToken = token;
}

export function getAccessToken(): string | null {
  return _accessToken;
}

export async function apiFetch<T>(
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

  let res: Response;
  try {
    res = await fetch(resolveApiUrl(path), { ...options, headers, credentials: "include" });
  } catch {
    throw new Error(getNetworkErrorMessage(path));
  }

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

export interface ContactRequest {
  name: string;
  email: string;
  subject: "demo";
  message: string;
}

export interface ContactResponse {
  received: true;
  message: string;
}

export async function submitContact(body: ContactRequest): Promise<ContactResponse> {
  return apiFetch<ContactResponse>("/api/v1/contact", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    // Browser sends httpOnly cookie automatically via credentials: "include"
    const res = await fetch(resolveApiUrl("/api/v1/auth/refresh"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include", // sends httpOnly refresh_token cookie
      body: JSON.stringify({}), // empty body — server reads token from cookie
    });
    if (!res.ok) return false;
    const data = await res.json();
    _accessToken = data.access_token;
    return true;
  } catch {
    return false;
  }
}

// ── Auth ─────────────────────────────────────────────────────────────────────

export interface LoginResponse {
  // Standard auth (2FA not required or completed)
  access_token?: string;
  refresh_token?: string;
  token_type?: string;
  expires_in?: number;
  // 2FA challenge
  requires_2fa?: boolean;
  partial_token?: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  plan: string;
  is_active: boolean;
  is_admin: boolean;
  is_verified: boolean;
  credits: number;
  totp_enabled: boolean;
  created_at: string;
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  const data = await apiFetch<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  // Web keeps the access token in memory only; refresh stays in the httpOnly cookie.
  if (!data.requires_2fa && data.access_token) {
    setAccessToken(data.access_token);
  }
  return data;
}

export async function verify2FALogin(
  partialToken: string,
  totpCode: string
): Promise<LoginResponse> {
  const data = await apiFetch<LoginResponse>("/api/v1/auth/2fa/verify-login", {
    method: "POST",
    body: JSON.stringify({ partial_token: partialToken, totp_code: totpCode }),
  });
  if (data.access_token) {
    setAccessToken(data.access_token);
  }
  return data;
}

// ── 2FA Management ─────────────────────────────────────────────────────────
export interface TwoFASetupResponse {
  provisioning_uri: string;
  secret: string;
  qr_code_base64?: string | null;
}

export async function setup2FA(): Promise<TwoFASetupResponse> {
  return apiFetch<TwoFASetupResponse>("/api/v1/auth/2fa/setup", { method: "POST" });
}

export async function enable2FA(totpCode: string): Promise<void> {
  await apiFetch<void>("/api/v1/auth/2fa/enable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode }),
  });
}

export async function disable2FA(totpCode?: string, password?: string): Promise<void> {
  await apiFetch<void>("/api/v1/auth/2fa/disable", {
    method: "POST",
    body: JSON.stringify({ totp_code: totpCode ?? null, password: password ?? null }),
  });
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
  setAccessToken(data.access_token ?? null);
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
  team_seats_max: number;
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
  marketing_description: string;
  highlight: boolean;
  price_monthly_usd: number;
  price_yearly_usd: number;
  yearly_discount_pct: number;
  trial_days: number;
  support_level: string;
  limits: PlanLimits;
  features: string[];
  features_enabled: FeatureGates;
  included_modules: string[];
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

export interface PublicEntrypointHealth {
  status: string;
  app: string;
  env: string;
  domain: string;
  public_web_url: string;
  api_base_url: string;
  allowed_origins: string[];
  canonical_web_url: string;
  canonical_api_url: string;
  expected_public_hosts: string[];
  raw_ip_supported_for_login: boolean;
  ts: string;
}

export interface BillingModulePublic {
  slug: string;
  name: string;
  price_usd: number;
  description: string;
  available: boolean;
  included_in_plans: string[];
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

export async function getBillingModules(): Promise<BillingModulePublic[]> {
  return apiFetch<BillingModulePublic[]>("/api/v1/billing/modules");
}

export async function getPublicEntrypointHealth(): Promise<PublicEntrypointHealth> {
  return apiFetch<PublicEntrypointHealth>("/api/v1/health/public-entrypoint", {}, false);
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
  return resolveApiUrl("/api/v1/analytics/export");
}

// ── Modules ───────────────────────────────────────────────────────────────────

export async function getModuleCatalog() {
  return apiFetch<Array<{ key: string; name: string; description: string; is_available: boolean }>>(
    "/api/v1/modules/catalog"
  );
}

export interface ModuleAccess {
  slug: string;
  name: string;
  price_usd: number;
  description: string;
  access: boolean;
  source: "plan" | "purchased" | "locked";
  stripe_price_id_available: boolean;
}

export async function getMyModules() {
  return apiFetch<{ plan: string; modules: ModuleAccess[] }>("/api/v1/billing/my-modules");
}

export async function createModuleCheckout(moduleSlug: string) {
  return apiFetch<{ url: string }>("/api/v1/billing/module-checkout-session", {
    method: "POST",
    body: JSON.stringify({ module: moduleSlug }),
  });
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export interface AdminUserSummary {
  id: string;
  email: string;
  full_name: string;
  plan: string;
  credits: number;
  is_active: boolean;
  is_admin: boolean;
  stripe_customer_id: string | null;
  created_at: string;
}

export interface AdminUsersResponse {
  total: number;
  page: number;
  per_page: number;
  users: AdminUserSummary[];
}

export interface AdminUserDetail extends AdminUserSummary {
  subscription: {
    plan: string | null;
    status: string | null;
    billing_interval: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    trial_end: string | null;
  } | null;
  credit_ledger: Array<{
    type: string;
    amount: number;
    balance_after: number;
    source: string | null;
    note: string | null;
    created_at: string;
  }>;
}

export interface AdminWebhookEvent {
  id: string;
  stripe_event_id: string;
  event_type: string;
  status: string;
  error: string | null;
  processed_at: string | null;
}

export interface AdminMetrics {
  total_users: number;
  users_by_plan: Record<string, number>;
  active_paid_users: number;
  subscriptions_by_status: Record<string, number>;
  estimated_mrr_usd: number;
}

export interface AdminPrivateOrchestratorAccess {
  admin_only: boolean;
  feature_flagged: boolean;
  public_saas_exposure: boolean;
  destructive_merge_with_my_agent_hub: boolean;
  requires_private_admin_surface: boolean;
  production_ip_allowlist_required: boolean;
}

export interface AdminPrivateOrchestratorCapabilities {
  agent_catalog_read: boolean;
  upstream_health_read: boolean;
  prompt_execution: boolean;
  terminal_access: boolean;
  filesystem_access: boolean;
  browser_access: boolean;
  billing_mutation: boolean;
  user_impersonation: boolean;
}

export interface AdminPrivateOrchestratorUpstream {
  ok: boolean;
  status: string;
  service: string | null;
  version: string | null;
  detail: string | null;
}

export interface AdminPrivateOrchestratorOverview {
  context_key: string;
  enabled: boolean;
  release_stage: string;
  access: AdminPrivateOrchestratorAccess;
  capabilities: AdminPrivateOrchestratorCapabilities;
  allowed_agent_keys: string[];
  upstream: AdminPrivateOrchestratorUpstream;
  endpoints: string[];
  notes: string[];
}

export interface AdminPrivateOrchestratorAgent {
  key: string;
  name: string;
  description: string;
  allowed: boolean;
}

export interface AdminPrivateOrchestratorAgentsResponse {
  enabled: boolean;
  source: string;
  agents: AdminPrivateOrchestratorAgent[];
}

export async function getAdminUsers(
  page = 1,
  per_page = 50,
  plan?: string,
): Promise<AdminUsersResponse> {
  let url = `/api/v1/admin/users?page=${page}&per_page=${per_page}`;
  if (plan) url += `&plan=${encodeURIComponent(plan)}`;
  return apiFetch<AdminUsersResponse>(url);
}

export async function getAdminUser(userId: string): Promise<AdminUserDetail> {
  return apiFetch<AdminUserDetail>(`/api/v1/admin/users/${userId}`);
}

export async function adminAdjustCredits(
  userId: string,
  amount: number,
  note?: string,
): Promise<{ status: string; amount: number; balance_after: number }> {
  return apiFetch(`/api/v1/admin/users/${userId}/credits`, {
    method: "POST",
    body: JSON.stringify({ amount, note }),
  });
}

export async function adminOverridePlan(
  userId: string,
  plan: string,
  reason?: string,
): Promise<{ status: string; old_plan: string; new_plan: string }> {
  return apiFetch(`/api/v1/admin/users/${userId}/plan`, {
    method: "PUT",
    body: JSON.stringify({ plan, reason }),
  });
}

export async function getAdminWebhooks(
  limit = 50,
): Promise<{ webhooks: AdminWebhookEvent[] }> {
  return apiFetch<{ webhooks: AdminWebhookEvent[] }>(
    `/api/v1/admin/webhooks?limit=${limit}`,
  );
}

export async function getAdminMetrics(): Promise<AdminMetrics> {
  return apiFetch<AdminMetrics>("/api/v1/admin/metrics");
}

export async function getAdminPrivateOrchestratorOverview(): Promise<AdminPrivateOrchestratorOverview> {
  return apiFetch<AdminPrivateOrchestratorOverview>("/api/v1/admin/orchestrator/overview");
}

export async function getAdminPrivateOrchestratorAgents(): Promise<AdminPrivateOrchestratorAgentsResponse> {
  return apiFetch<AdminPrivateOrchestratorAgentsResponse>("/api/v1/admin/orchestrator/agents");
}

// ── Team ──────────────────────────────────────────────────────────────────────

export interface TeamMemberItem {
  id: string;
  email: string;
  role: string;
  accepted: boolean;
  invited_at: string;
  accepted_at: string | null;
}

export interface TeamMembersResponse {
  members: TeamMemberItem[];
  seats_used: number;
  seats_limit: number;
}

export async function getTeamMembers(): Promise<TeamMembersResponse> {
  return apiFetch<TeamMembersResponse>("/api/v1/team/members");
}

export async function inviteTeamMember(
  email: string,
  role: string = "member",
): Promise<{ id: string; email: string; role: string; status: string }> {
  return apiFetch("/api/v1/team/invite", {
    method: "POST",
    body: JSON.stringify({ email, role }),
  });
}

export async function removeTeamMember(memberId: string): Promise<void> {
  await apiFetch(`/api/v1/team/members/${memberId}`, { method: "DELETE" });
}

export async function replayWebhook(stripeEventId: string): Promise<{ status: string; event_type: string }> {
  return apiFetch(`/api/v1/admin/webhooks/${encodeURIComponent(stripeEventId)}/reprocess`, { method: "POST" });
}

export async function downloadGdprExport(): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = getAccessToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const res = await fetch(resolveApiUrl("/api/v1/users/me/export-data"), { headers, credentials: "include" });
  if (!res.ok) throw new Error("Export failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "nanovia-export.json";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export interface BrandingSettings {
  workspace_id: string;
  company_name: string | null;
  logo_url: string | null;
  primary_color: string | null;
  accent_color: string | null;
  support_email: string | null;
  custom_domain: string | null;
}

export async function getBranding(): Promise<BrandingSettings> {
  return apiFetch("/api/v1/admin/branding");
}

export async function updateBranding(data: Partial<BrandingSettings>): Promise<BrandingSettings> {
  return apiFetch("/api/v1/admin/branding", { method: "PUT", body: JSON.stringify(data) });
}

export interface CustomModuleData {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  prompt_template: string;
  is_active: boolean;
  created_at: string;
}

export async function listCustomModules(): Promise<CustomModuleData[]> {
  return apiFetch("/api/v1/modules/custom");
}

export async function createCustomModule(data: { name: string; description?: string; prompt_template: string }): Promise<CustomModuleData> {
  return apiFetch("/api/v1/modules/custom", { method: "POST", body: JSON.stringify(data) });
}

export async function deleteCustomModule(id: string): Promise<void> {
  return apiFetch(`/api/v1/modules/custom/${id}`, { method: "DELETE" });
}

