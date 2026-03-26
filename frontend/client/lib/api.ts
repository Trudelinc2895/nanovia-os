/**
 * lib/api.ts — typed API client for frontend web
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://167.114.155.166";

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

export interface Plan {
  slug: string;
  name: string;
  price_monthly: number;
  price_yearly: number;
  features: string[];
}

export interface Entitlements {
  plan: string;
  modules: string[];
  ai_messages_per_month: number;
  team_seats: number;
}

export async function getPlans(): Promise<Plan[]> {
  return apiFetch<Plan[]>("/api/v1/billing/plans");
}

export async function getEntitlements(): Promise<Entitlements> {
  return apiFetch<Entitlements>("/api/v1/billing/entitlements");
}

export async function createCheckoutSession(plan_slug: string, yearly: boolean) {
  return apiFetch<{ url: string }>("/api/v1/billing/checkout-session", {
    method: "POST",
    body: JSON.stringify({ plan_slug, yearly }),
  });
}

export async function createPortalSession() {
  return apiFetch<{ url: string }>("/api/v1/billing/portal-session", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

// ── Modules ───────────────────────────────────────────────────────────────────

export async function getModuleCatalog() {
  return apiFetch<Array<{ key: string; name: string; description: string; is_available: boolean }>>(
    "/api/v1/modules/catalog"
  );
}
