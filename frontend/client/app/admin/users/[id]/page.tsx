"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  getAdminUser,
  adminAdjustCredits,
  adminOverridePlan,
  type AdminUserDetail,
} from "@/lib/api";
import { getPlanBadgeClass, getPlanDisplayName, PLAN_SLUGS } from "@/lib/monetization";

export default function AdminUserDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [user, setUser] = useState<AdminUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Credit adjustment state
  const [creditAmount, setCreditAmount] = useState("");
  const [creditNote, setCreditNote] = useState("");
  const [creditMsg, setCreditMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [creditLoading, setCreditLoading] = useState(false);

  // Plan override state
  const [overridePlan, setOverridePlan] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [planMsg, setPlanMsg] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [planLoading, setPlanLoading] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    getAdminUser(id)
      .then((u) => {
        setUser(u);
        setOverridePlan(u.plan);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleAdjustCredits = async () => {
    const amount = parseInt(creditAmount, 10);
    if (isNaN(amount) || amount === 0) {
      setCreditMsg({ type: "error", text: "Enter a non-zero integer amount." });
      return;
    }
    setCreditLoading(true);
    setCreditMsg(null);
    try {
      const res = await adminAdjustCredits(id, amount, creditNote || undefined);
      setCreditMsg({
        type: "success",
        text: `Done. New balance: ${res.balance_after} credits.`,
      });
      setCreditAmount("");
      setCreditNote("");
      load();
    } catch (e: unknown) {
      setCreditMsg({ type: "error", text: (e as Error).message });
    } finally {
      setCreditLoading(false);
    }
  };

  const handleOverridePlan = async () => {
    setPlanLoading(true);
    setPlanMsg(null);
    try {
      const res = await adminOverridePlan(id, overridePlan, overrideReason || undefined);
      setPlanMsg({
        type: "success",
        text: `Plan updated: ${res.old_plan} → ${res.new_plan}`,
      });
      setOverrideReason("");
      load();
    } catch (e: unknown) {
      setPlanMsg({ type: "error", text: (e as Error).message });
    } finally {
      setPlanLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-purple-400 animate-pulse">Loading user...</div>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="bg-red-900/30 border border-red-700/50 text-red-300 rounded-lg px-4 py-3">
        {error ?? "User not found."}
      </div>
    );
  }

  return (
    <div className="max-w-4xl">
      {/* Back */}
      <button
        onClick={() => router.push("/admin/users")}
        className="text-sm text-gray-500 hover:text-gray-300 mb-6 flex items-center gap-1 transition"
      >
        ← Users
      </button>

      <h1 className="text-2xl font-bold text-white mb-6">{user.email}</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* User Info Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-4">User Info</h2>
          <dl className="space-y-2 text-sm">
            <InfoRow label="Email" value={user.email} />
            <InfoRow
              label="Plan"
              value={
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    getPlanBadgeClass(user.plan)
                  }`}
                >
                  {getPlanDisplayName(user.plan)}
                </span>
              }
            />
            <InfoRow label="Credits" value={String(user.credits)} />
            <InfoRow
              label="Status"
              value={
                <span
                  className={`text-xs px-2 py-0.5 rounded-full ${
                    user.is_active ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"
                  }`}
                >
                  {user.is_active ? "active" : "inactive"}
                </span>
              }
            />
            <InfoRow
              label="Stripe Customer"
              value={user.stripe_customer_id ?? "—"}
            />
            <InfoRow
              label="Created"
              value={new Date(user.created_at).toLocaleString()}
            />
          </dl>
        </div>

        {/* Subscription Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-4">Subscription</h2>
          {user.subscription ? (
            <dl className="space-y-2 text-sm">
              <InfoRow label="Plan" value={user.subscription.plan ?? "—"} />
              <InfoRow label="Status" value={user.subscription.status ?? "—"} />
              <InfoRow
                label="Interval"
                value={user.subscription.billing_interval ?? "—"}
              />
              <InfoRow
                label="Period End"
                value={
                  user.subscription.current_period_end
                    ? new Date(user.subscription.current_period_end).toLocaleDateString()
                    : "—"
                }
              />
              <InfoRow
                label="Trial End"
                value={
                  user.subscription.trial_end
                    ? new Date(user.subscription.trial_end).toLocaleDateString()
                    : "—"
                }
              />
            </dl>
          ) : (
            <p className="text-sm text-gray-500">No active subscription.</p>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Adjust Credits */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-4">Adjust Credits</h2>
          <div className="space-y-3">
            <input
              type="number"
              placeholder="Amount (e.g. 50 or -10)"
              value={creditAmount}
              onChange={(e) => setCreditAmount(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            />
            <input
              type="text"
              placeholder="Note (optional)"
              value={creditNote}
              onChange={(e) => setCreditNote(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            />
            <button
              onClick={handleAdjustCredits}
              disabled={creditLoading}
              className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2 transition"
            >
              {creditLoading ? "Applying..." : "Adjust Credits"}
            </button>
            {creditMsg && (
              <p
                className={`text-sm ${
                  creditMsg.type === "success" ? "text-green-400" : "text-red-400"
                }`}
              >
                {creditMsg.text}
              </p>
            )}
          </div>
        </div>

        {/* Override Plan */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase mb-4">Override Plan</h2>
          <div className="space-y-3">
            <select
              value={overridePlan}
              onChange={(e) => setOverridePlan(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            >
              {PLAN_SLUGS.map((plan) => (
                <option key={plan} value={plan}>
                  {getPlanDisplayName(plan)}
                </option>
              ))}
            </select>
            <input
              type="text"
              placeholder="Reason (optional)"
              value={overrideReason}
              onChange={(e) => setOverrideReason(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 text-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-purple-600"
            />
            <button
              onClick={handleOverridePlan}
              disabled={planLoading}
              className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2 transition"
            >
              {planLoading ? "Updating..." : "Override Plan"}
            </button>
            {planMsg && (
              <p
                className={`text-sm ${
                  planMsg.type === "success" ? "text-green-400" : "text-red-400"
                }`}
              >
                {planMsg.text}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Credit Ledger */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-5 py-4 border-b border-gray-800">
          <h2 className="text-sm font-semibold text-gray-400 uppercase">
            Credit Ledger (last 20)
          </h2>
        </div>
        {user.credit_ledger.length === 0 ? (
          <p className="text-sm text-gray-500 px-5 py-6">No ledger entries.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-800 text-left">
                <th className="px-4 py-3 text-gray-500 font-medium">Type</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Amount</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Balance After</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Source</th>
                <th className="px-4 py-3 text-gray-500 font-medium">Date</th>
              </tr>
            </thead>
            <tbody>
              {user.credit_ledger.map((entry, i) => (
                <tr key={i} className="border-b border-gray-800/50">
                  <td className="px-4 py-2.5 text-gray-300">{entry.type}</td>
                  <td
                    className={`px-4 py-2.5 font-mono ${
                      entry.amount > 0 ? "text-green-400" : "text-red-400"
                    }`}
                  >
                    {entry.amount > 0 ? `+${entry.amount}` : entry.amount}
                  </td>
                  <td className="px-4 py-2.5 text-gray-300">{entry.balance_after}</td>
                  <td className="px-4 py-2.5 text-gray-500 max-w-[150px] truncate">
                    {entry.source ?? "—"}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">
                    {new Date(entry.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function InfoRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-gray-500 shrink-0">{label}</dt>
      <dd className="text-gray-200 text-right break-all">{value}</dd>
    </div>
  );
}
