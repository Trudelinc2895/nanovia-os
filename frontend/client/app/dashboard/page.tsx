"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { getEntitlements, getModuleCatalog, type Entitlements } from "@/lib/api";

const MODULE_ICONS: Record<string, string> = {
  operator: "🤖",
  content_cloner: "📢",
  micro_saas: "⚙️",
  ghost_agency: "👻",
  decision_engine: "🧠",
  knowledge_weapon: "📚",
  digital_leverage: "📈",
  reverse_engineering: "🔬",
  offer_generator: "🎯",
  execution_service: "⚡",
};

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [modules, setModules] = useState<Array<{
    key: string; name: string; description: string; is_available: boolean;
  }>>([]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    getEntitlements().then(setEntitlements).catch(console.error);
    getModuleCatalog().then(setModules).catch(console.error);
  }, [user]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-purple-400 animate-pulse text-xl">Chargement...</div>
      </div>
    );
  }

  const planColor = {
    free: "text-gray-400",
    starter: "text-blue-400",
    pro: "text-purple-400",
    business: "text-yellow-400",
  }[user.plan] ?? "text-gray-400";

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-purple-400 font-bold text-xl">⚡ KT OS</span>
            <span className="text-gray-600">|</span>
            <span className="text-sm text-gray-400">{user.full_name || user.email}</span>
          </div>
          <div className="flex items-center gap-4">
            <span className={`text-sm font-semibold uppercase ${planColor}`}>
              Plan {user.plan}
            </span>
            <button
              onClick={async () => { await logout(); router.push("/"); }}
              className="text-sm text-gray-500 hover:text-red-400 transition"
            >
              Déconnexion
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        {/* Welcome + Quick Actions */}
        <div className="mb-10 flex flex-col md:flex-row md:items-center gap-6">
          <div className="flex-1">
            <h1 className="text-3xl font-bold text-white mb-2">
              Bienvenue, {user.full_name?.split(" ")[0] || "Champion"} 👋
            </h1>
            <p className="text-gray-400">
              Votre système de monétisation IA est actif.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/dashboard/chat"
              className="bg-purple-600 hover:bg-purple-500 text-white font-semibold px-5 py-3 rounded-xl transition flex items-center gap-2"
            >
              🤖 Lancer l&apos;IA
            </Link>
            {user.plan === "free" && (
              <Link
                href="/dashboard/billing"
                className="border border-yellow-500/50 text-yellow-400 hover:bg-yellow-500/10 font-semibold px-5 py-3 rounded-xl transition"
              >
                ⚡ Upgrader
              </Link>
            )}
          </div>
        </div>

        {/* Entitlements Summary */}
        {entitlements && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
            <StatCard label="Plan" value={entitlements.plan.toUpperCase()} />
            <StatCard
              label="Modules actifs"
              value={`${entitlements.modules.length}/10`}
            />
            <StatCard
              label="Messages IA / mois"
              value={entitlements.ai_messages_per_month === 999999 ? "∞" : String(entitlements.ai_messages_per_month)}
            />
            <StatCard
              label="Sièges équipe"
              value={String(entitlements.team_seats)}
            />
          </div>
        )}

        {/* Module Grid */}
        <h2 className="text-xl font-bold text-white mb-5">🧩 Vos modules</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {modules.map((mod) => (
            <ModuleCard key={mod.key} mod={mod} />
          ))}
        </div>

        {/* Upgrade CTA for free users */}
        {user.plan === "free" && (
          <div className="mt-12 bg-gradient-to-r from-purple-900/30 to-indigo-900/30 border border-purple-700/50 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-3">⚡</div>
            <h3 className="text-2xl font-bold text-white mb-2">
              Débloquer tous les modules
            </h3>
            <p className="text-gray-400 mb-6 max-w-md mx-auto">
              Accès complet à l&apos;IA Orchestrator, Ghost Agency, et 8 autres modules de monétisation.
            </p>
            <Link
              href="/dashboard/billing"
              className="inline-block bg-purple-600 hover:bg-purple-500 text-white font-bold px-8 py-4 rounded-xl text-lg transition"
            >
              Voir les plans →
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-sm text-gray-500 mt-1">{label}</div>
    </div>
  );
}

function ModuleCard({ mod }: {
  mod: { key: string; name: string; description: string; is_available: boolean };
}) {
  const icon = MODULE_ICONS[mod.key] ?? "🔷";
  return (
    <div
      className={`bg-gray-900 border rounded-xl p-5 transition flex flex-col gap-3 ${
        mod.is_available
          ? "border-gray-700 hover:border-purple-600 cursor-pointer"
          : "border-gray-800 opacity-40"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        {!mod.is_available && (
          <span className="text-xs bg-gray-800 text-gray-500 px-2 py-0.5 rounded-full ml-auto">
            🔒 Locked
          </span>
        )}
      </div>
      <div>
        <div className="font-semibold text-white text-sm">{mod.name}</div>
        <div className="text-xs text-gray-500 mt-1 line-clamp-2">{mod.description}</div>
      </div>
      {mod.is_available && (
        <Link
          href={mod.key === "operator" || mod.key === "ghost_agency" || mod.key === "decision_engine"
            ? `/dashboard/chat?agent=${mod.key}`
            : "/dashboard/chat"
          }
          className="text-xs text-purple-400 hover:text-purple-300 mt-auto"
        >
          Utiliser →
        </Link>
      )}
    </div>
  );
}
