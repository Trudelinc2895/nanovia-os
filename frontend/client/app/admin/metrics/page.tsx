"use client";

import { useEffect, useState, useCallback } from "react";
import { getAdminMetrics, type AdminMetrics } from "@/lib/api";

const PLAN_COLORS: Record<string, string> = {
  free: "bg-gray-500",
  pro: "bg-purple-600",
  business: "bg-yellow-500",
};

export default function AdminMetricsPage() {
  const [metrics, setMetrics] = useState<AdminMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

  const load = useCallback(() => {
    setError(null);
    getAdminMetrics()
      .then((m) => {
        setMetrics(m);
        setLastRefresh(new Date());
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, [load]);

  const totalByPlan = metrics
    ? Object.values(metrics.users_by_plan).reduce((a, b) => a + b, 0)
    : 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Business Metrics</h1>
          <p className="text-sm text-gray-500 mt-1">
            Auto-refreshes every 60s · Last: {lastRefresh.toLocaleTimeString()}
          </p>
        </div>
        <button
          onClick={load}
          className="text-sm bg-gray-800 border border-gray-700 text-gray-300 hover:bg-gray-700 rounded-lg px-3 py-1.5 transition"
        >
          ↻ Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-3 mb-4">
          {error}
        </div>
      )}

      {loading && !metrics ? (
        <div className="text-gray-500 animate-pulse py-10 text-center">Loading metrics...</div>
      ) : metrics ? (
        <>
          {/* KPI Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <KpiCard label="Total Users" value={String(metrics.total_users)} icon="👥" />
            <KpiCard
              label="Active Paid"
              value={String(metrics.active_paid_users)}
              icon="💎"
            />
            <KpiCard
              label="Est. MRR"
              value={`$${metrics.estimated_mrr_usd.toLocaleString()}`}
              icon="💰"
            />
            <KpiCard
              label="Free Plan"
              value={String(metrics.users_by_plan["free"] ?? 0)}
              icon="🆓"
            />
          </div>

          {/* Plan Distribution */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-6">
            <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">
              Plan Distribution
            </h2>
            <div className="space-y-4">
              {["free", "pro", "business"].map((plan) => {
                const count = metrics.users_by_plan[plan] ?? 0;
                const pct = totalByPlan > 0 ? Math.round((count / totalByPlan) * 100) : 0;
                return (
                  <div key={plan}>
                    <div className="flex items-center justify-between text-sm mb-1.5">
                      <span className="text-gray-300 capitalize font-medium">{plan}</span>
                      <span className="text-gray-500">
                        {count} users · {pct}%
                      </span>
                    </div>
                    <div className="h-2.5 bg-gray-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${
                          PLAN_COLORS[plan] ?? "bg-gray-500"
                        }`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Subscription Status Grid */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <h2 className="text-sm font-semibold text-gray-400 uppercase mb-5">
              Subscription Status
            </h2>
            {Object.keys(metrics.subscriptions_by_status).length === 0 ? (
              <p className="text-sm text-gray-500">No subscriptions.</p>
            ) : (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
                {Object.entries(metrics.subscriptions_by_status).map(([status, count]) => (
                  <div
                    key={status}
                    className="bg-gray-800 border border-gray-700 rounded-xl p-4 text-center"
                  >
                    <div className="text-2xl font-bold text-white">{count}</div>
                    <div className="text-xs text-gray-500 mt-1 capitalize">{status}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : null}
    </div>
  );
}

function KpiCard({ label, value, icon }: { label: string; value: string; icon: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="text-2xl mb-1">{icon}</div>
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-sm text-gray-500 mt-1">{label}</div>
    </div>
  );
}
