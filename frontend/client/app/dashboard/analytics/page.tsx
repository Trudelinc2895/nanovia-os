"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  getModuleBreakdown,
  getMilestones,
  getExportUrl,
  type ModuleBreakdown,
  type MilestonesData,
} from "@/lib/api";

function ModuleBar({ item, max }: { item: ModuleBreakdown; max: number }) {
  const pct = max > 0 ? (item.message_count / max) * 100 : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-300 font-medium capitalize">{item.module.replace(/_/g, " ")}</span>
        <span className="text-gray-500">{item.message_count} msgs · ${item.cost_usd_total.toFixed(4)}</span>
      </div>
      <div className="w-full bg-ui-elevated rounded-full h-1.5">
        <div className="h-1.5 bg-primary rounded-full" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [days, setDays] = useState(30);
  const [breakdown, setBreakdown] = useState<ModuleBreakdown[]>([]);
  const [milestones, setMilestones] = useState<MilestonesData | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    setFetching(true);
    setError("");
    Promise.all([
      getModuleBreakdown(days),
      getMilestones(),
    ])
      .then(([bdata, mdata]) => {
        setBreakdown(bdata.breakdown);
        setMilestones(mdata);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Erreur de chargement"))
      .finally(() => setFetching(false));
  }, [user, days]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-base">
        <div className="text-primary animate-pulse">Chargement...</div>
      </div>
    );
  }

  const maxCount = breakdown[0]?.message_count ?? 1;
  const totalMessages = breakdown.reduce((sum, b) => sum + b.message_count, 0);
  const totalCost = breakdown.reduce((sum, b) => sum + b.cost_usd_total, 0);

  return (
    <div className="min-h-screen bg-bg-base text-white">
      <header className="border-b border-ui-border bg-ui-surface/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-gray-500 hover:text-white transition">←</Link>
            <span className="font-bold">📊 Analytics</span>
          </div>
          <div className="flex items-center gap-3">
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="bg-ui-elevated border border-ui-border text-sm text-gray-300 rounded-lg px-3 py-1.5 focus:outline-none focus:border-primary"
            >
              <option value={7}>7 jours</option>
              <option value={30}>30 jours</option>
              <option value={90}>90 jours</option>
            </select>
            <a
              href={getExportUrl()}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs border border-ui-border hover:border-primary text-gray-400 hover:text-white px-3 py-1.5 rounded-lg transition"
            >
              ↓ Exporter CSV
            </a>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-10">
        {error && (
          <div className="bg-danger-muted border border-danger/30 text-danger-text rounded-xl px-4 py-3 text-sm">
            {error}
          </div>
        )}

        {/* Summary KPIs */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: "Messages", value: totalMessages.toLocaleString() },
            { label: "Tokens", value: breakdown.reduce((s, b) => s + b.tokens_total, 0).toLocaleString() },
            { label: "Coût estimé", value: `$${totalCost.toFixed(4)}` },
            { label: "Modules actifs", value: String(breakdown.length) },
          ].map((kpi) => (
            <div key={kpi.label} className="bg-ui-surface border border-ui-border rounded-2xl p-4 text-center">
              <div className="text-2xl font-black text-white">{kpi.value}</div>
              <div className="text-xs text-gray-500 mt-1">{kpi.label}</div>
            </div>
          ))}
        </div>

        {/* Module breakdown */}
        <div className="bg-ui-surface border border-ui-border rounded-2xl p-6 space-y-5">
          <h2 className="font-bold text-base">Usage par module</h2>
          {fetching ? (
            <p className="text-gray-500 text-sm animate-pulse">Chargement...</p>
          ) : breakdown.length === 0 ? (
            <p className="text-gray-500 text-sm">Aucune activité sur cette période.</p>
          ) : (
            <div className="space-y-4">
              {breakdown.map((b) => (
                <ModuleBar key={b.module} item={b} max={maxCount} />
              ))}
            </div>
          )}
        </div>

        {/* Gamification milestones */}
        {milestones && (
          <div className="bg-ui-surface border border-ui-border rounded-2xl p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="font-bold text-base">🏆 Progression</h2>
              <span className="text-sm text-gray-500">
                {milestones.total_unlocked}/{milestones.total} débloqués · {milestones.progress_pct}%
              </span>
            </div>
            {/* Progress bar */}
            <div className="w-full bg-ui-elevated rounded-full h-2 mb-6">
              <div
                className="h-2 bg-gradient-to-r from-primary to-primary-hover rounded-full transition-all"
                style={{ width: `${milestones.progress_pct}%` }}
              />
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              {milestones.milestones.map((m) => (
                <div
                  key={m.key}
                  className={`rounded-xl p-3 flex items-center gap-3 ${
                    m.unlocked
                      ? "bg-primary-muted border border-primary/20"
                      : "bg-ui-elevated/30 border border-ui-border opacity-50"
                  }`}
                >
                  <span className="text-2xl">{m.icon}</span>
                  <div>
                    <div className={`text-xs font-semibold ${m.unlocked ? "text-primary" : "text-gray-500"}`}>
                      {m.unlocked ? "✓ Débloqué" : "Verrouillé"}
                    </div>
                    <div className="text-xs text-gray-400">{m.label}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
