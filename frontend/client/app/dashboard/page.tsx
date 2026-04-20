"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { getEntitlements, getModuleCatalog, type Entitlements } from "@/lib/api";
import { Button, Card, Badge } from "@/components/ui";

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
      <div className="min-h-screen flex items-center justify-center bg-bg-base">
        <div className="text-primary animate-pulse text-xl">Chargement...</div>
      </div>
    );
  }

  const planVariant: Record<string, "info" | "success" | "warning" | "danger"> = {
    free: "info",
    starter: "info",
    pro: "success",
    business: "warning",
  };

  return (
    <div className="min-h-screen bg-bg-base">
      {/* Header */}
      <header className="border-b border-ui-border bg-ui-surface/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-primary font-bold text-xl">⚡ Nanovia OS</span>
            <span className="text-text-muted">|</span>
            <span className="text-sm text-text-secondary">{user.full_name || user.email}</span>
          </div>
          <div className="flex items-center gap-4">
            <Badge variant={planVariant[user.plan] ?? "info"}>
              Plan {user.plan.toUpperCase()}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => { await logout(); router.push("/"); }}
              className="text-text-muted hover:text-danger"
            >
              Déconnexion
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
        {/* Welcome + Quick Actions */}
        <div className="mb-10 flex flex-col md:flex-row md:items-center gap-6">
          <div className="flex-1">
            <h1 className="text-3xl font-bold text-text-primary mb-2">
              Bienvenue, {user.full_name?.split(" ")[0] || "Champion"} 👋
            </h1>
            <p className="text-text-secondary">
              Votre système de monétisation IA est actif.
            </p>
          </div>
          <div className="flex gap-3">
            <Link
              href="/dashboard/chat"
              className="bg-primary hover:bg-primary-hover text-white font-semibold px-5 py-3 rounded-xl transition flex items-center gap-2"
            >
              🤖 Lancer l&apos;IA
            </Link>
            {user.plan === "free" && (
              <Link
                href="/dashboard/billing"
                className="border border-warning/50 text-warning-text hover:bg-warning-muted font-semibold px-5 py-3 rounded-xl transition"
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
              label="Messages / mois"
              value={entitlements.limits.ai_messages_per_month === -1 ? "∞" : String(entitlements.limits.ai_messages_per_month)}
            />
            <StatCard label="Crédits overage" value={String(entitlements.credits)} />
            <StatCard label="Stockage" value={entitlements.limits.storage_gb + " GB"} />
          </div>
        )}

        {/* Module Grid */}
        <h2 className="text-xl font-bold text-text-primary mb-5">🧩 Vos modules</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {modules.map((mod) => (
            <ModuleCard key={mod.key} mod={mod} />
          ))}
        </div>

        {/* Upgrade CTA for free users */}
        {user.plan === "free" && (
          <div className="mt-12 bg-primary-muted border border-primary/20 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-3">⚡</div>
            <h3 className="text-2xl font-bold text-text-primary mb-2">
              Débloquer tous les modules
            </h3>
            <p className="text-text-secondary mb-6 max-w-md mx-auto">
              Accès complet à l&apos;IA Orchestrator, Ghost Agency, et 8 autres modules de monétisation.
            </p>
            <Link
              href="/dashboard/billing"
              className="inline-block bg-primary hover:bg-primary-hover text-white font-bold px-8 py-4 rounded-xl text-lg transition"
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
    <Card variant="outlined" padding="sm">
      <div className="text-2xl font-bold text-text-primary">{value}</div>
      <div className="text-sm text-text-muted mt-1">{label}</div>
    </Card>
  );
}

function ModuleCard({ mod }: {
  mod: { key: string; name: string; description: string; is_available: boolean };
}) {
  const icon = MODULE_ICONS[mod.key] ?? "🔷";
  return (
    <Card
      variant="outlined"
      padding="sm"
      className={"flex flex-col gap-3 transition " + (mod.is_available ? "hover:border-primary cursor-pointer" : "opacity-40")}
    >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        {!mod.is_available && (
          <Badge variant="warning" size="sm" className="ml-auto">🔒 Locked</Badge>
        )}
      </div>
      <div>
        <div className="font-semibold text-text-primary text-sm">{mod.name}</div>
        <div className="text-xs text-text-muted mt-1 line-clamp-2">{mod.description}</div>
      </div>
      {mod.is_available && (
        <Link
          href={
            mod.key === "operator" || mod.key === "ghost_agency" || mod.key === "decision_engine"
              ? "/dashboard/chat?agent=" + mod.key
              : "/dashboard/chat"
          }
          className="text-xs text-primary hover:text-primary-strong mt-auto"
        >
          Utiliser →
        </Link>
      )}
    </Card>
  );
}
