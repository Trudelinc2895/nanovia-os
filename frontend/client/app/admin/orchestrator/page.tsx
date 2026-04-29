"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getAdminPrivateOrchestratorAgents,
  getAdminPrivateOrchestratorOverview,
  type AdminPrivateOrchestratorAgent,
  type AdminPrivateOrchestratorOverview,
} from "@/lib/api";
import { isPrivateOrchestratorUiEnabled } from "@/lib/feature-flags";

const PRIVATE_UI_ENABLED = isPrivateOrchestratorUiEnabled();

export default function AdminOrchestratorPage() {
  const [overview, setOverview] = useState<AdminPrivateOrchestratorOverview | null>(null);
  const [agents, setAgents] = useState<AdminPrivateOrchestratorAgent[]>([]);
  const [loading, setLoading] = useState(PRIVATE_UI_ENABLED);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!PRIVATE_UI_ENABLED) return;

    setLoading(true);
    setError(null);
    try {
      const [overviewResponse, agentsResponse] = await Promise.all([
        getAdminPrivateOrchestratorOverview(),
        getAdminPrivateOrchestratorAgents(),
      ]);
      setOverview(overviewResponse);
      setAgents(agentsResponse.agents);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Impossible de charger le slice prive.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!PRIVATE_UI_ENABLED) {
      setLoading(false);
      return;
    }
    void load();
  }, [load]);

  if (!PRIVATE_UI_ENABLED) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Private Orchestrator</h1>
          <p className="text-sm text-gray-500 mt-1">
            Slice admin-only masque tant que le flag frontend reste desactive.
          </p>
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="text-sm font-semibold text-yellow-300 uppercase mb-3">
            Disabled by default
          </div>
          <p className="text-sm text-gray-300 leading-6">
            Active <code className="text-purple-300">NEXT_PUBLIC_PRIVATE_ORCHESTRATOR_ENABLED=true</code> cote
            admin prive et <code className="text-purple-300">PRIVATE_ORCHESTRATOR_ENABLED=true</code> cote API
            pour rendre ce slice visible. Aucun lien public ni capacite dangereuse n&apos;est expose tant que
            les deux flags restent off.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">Private Orchestrator</h1>
          <p className="text-sm text-gray-500 mt-1">
            Bounded context admin-only pour Nanovia. Aucun acces public SaaS ni execution destructive.
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="text-sm bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 rounded-lg px-3 py-1.5 transition"
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-3">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-gray-500 animate-pulse py-10 text-center">Loading orchestrator slice...</div>
      ) : overview ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            <StatusCard
              label="Release"
              value={overview.release_stage}
              tone="text-blue-300"
            />
            <StatusCard
              label="Surface"
              value={overview.access.admin_only ? "admin-only" : "unexpected"}
              tone="text-purple-300"
            />
            <StatusCard
              label="Upstream"
              value={overview.upstream.status}
              tone={overview.upstream.ok ? "text-green-300" : "text-yellow-300"}
            />
            <StatusCard
              label="Dangerous tools"
              value={
                overview.capabilities.terminal_access ||
                overview.capabilities.filesystem_access ||
                overview.capabilities.browser_access
                  ? "enabled"
                  : "locked"
              }
              tone="text-green-300"
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            <section className="xl:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">Access contract</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <ContractItem label="Feature flagged" ok={overview.access.feature_flagged} />
                <ContractItem label="Private admin surface" ok={overview.access.requires_private_admin_surface} />
                <ContractItem label="Public SaaS exposure" ok={!overview.access.public_saas_exposure} invertLabel="blocked" />
                <ContractItem
                  label="Production IP allowlist"
                  ok={overview.access.production_ip_allowlist_required}
                />
                <ContractItem label="Prompt execution" ok={!overview.capabilities.prompt_execution} invertLabel="disabled" />
                <ContractItem label="Billing mutation" ok={!overview.capabilities.billing_mutation} invertLabel="disabled" />
                <ContractItem label="User impersonation" ok={!overview.capabilities.user_impersonation} invertLabel="disabled" />
                <ContractItem
                  label="my_agent_hub destructive merge"
                  ok={!overview.access.destructive_merge_with_my_agent_hub}
                  invertLabel="blocked"
                />
              </div>
            </section>

            <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">Allowed agents</h2>
              <div className="space-y-3">
                {(agents.length > 0 ? agents : overview.allowed_agent_keys.map((key) => ({
                  key,
                  name: key,
                  description: "Allowlisted agent",
                  allowed: true,
                }))).map((agent) => (
                  <div key={agent.key} className="border border-gray-800 rounded-lg px-4 py-3">
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-sm font-medium text-white">{agent.name}</div>
                      <span className="text-[11px] uppercase tracking-wide text-green-300">
                        {agent.allowed ? "allowlisted" : "blocked"}
                      </span>
                    </div>
                    <div className="text-xs text-gray-500 mt-1">{agent.description}</div>
                    <div className="text-[11px] text-gray-600 mt-2 font-mono">{agent.key}</div>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">Published endpoints</h2>
              <div className="space-y-2">
                {overview.endpoints.map((endpoint) => (
                  <div
                    key={endpoint}
                    className="rounded-lg border border-gray-800 bg-gray-950 px-3 py-2 text-xs text-gray-300 font-mono"
                  >
                    {endpoint}
                  </div>
                ))}
              </div>
            </section>

            <section className="bg-gray-900 border border-gray-800 rounded-xl p-6">
              <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">Safety notes</h2>
              <ul className="space-y-3 text-sm text-gray-300">
                {overview.notes.map((note) => (
                  <li key={note} className="flex gap-3">
                    <span className="text-purple-300">•</span>
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </>
      ) : null}
    </div>
  );
}

function StatusCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: string;
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="text-xs uppercase tracking-wide text-gray-500">{label}</div>
      <div className={`text-lg font-semibold mt-2 ${tone}`}>{value}</div>
    </div>
  );
}

function ContractItem({
  label,
  ok,
  invertLabel,
}: {
  label: string;
  ok: boolean;
  invertLabel?: string;
}) {
  return (
    <div className="rounded-lg border border-gray-800 bg-gray-950 px-4 py-3">
      <div className="text-gray-300">{label}</div>
      <div className={`text-xs uppercase tracking-wide mt-1 ${ok ? "text-green-300" : "text-red-300"}`}>
        {ok ? "ok" : invertLabel ?? "off"}
      </div>
    </div>
  );
}
