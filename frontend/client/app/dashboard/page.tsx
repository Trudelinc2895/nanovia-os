"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  getEntitlements,
  getMyModules,
  type Entitlements,
  type ModuleAccess,
} from "@/lib/api";
import { Button, Card, Badge } from "@/components/ui";
import { getModuleIcon, getModulePresentation, MODULE_SLUGS } from "@/lib/monetization";

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [modules, setModules] = useState<ModuleAccess[]>([]);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    getEntitlements().then(setEntitlements).catch(console.error);
    getMyModules()
      .then((data) => setModules(data.modules))
      .catch(console.error);
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

  const effectivePlan = entitlements?.plan ?? user.plan;
  const subscriptionStatus = entitlements?.status ?? "free";
  const isPaidPlan = effectivePlan !== "free";
  const showSubscriptionWarning = !["active", "free"].includes(subscriptionStatus);

  return (
    <div className="min-h-screen bg-bg-base">
      <header className="border-b border-ui-border bg-ui-surface/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="text-primary font-bold text-xl">⚡ Nanovia OS</span>
            <span className="text-text-muted">|</span>
            <span className="text-sm text-text-secondary">{user.full_name || user.email}</span>
          </div>
          <div className="flex items-center gap-4">
            <Badge variant={planVariant[effectivePlan] ?? "info"}>
              Plan {effectivePlan.toUpperCase()}
            </Badge>
            <Button
              variant="ghost"
              size="sm"
              onClick={async () => {
                await logout();
                router.push("/");
              }}
              className="text-text-muted hover:text-danger"
            >
              Déconnexion
            </Button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-10">
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
            {!isPaidPlan && (
              <Link
                href="/dashboard/billing"
                className="border border-warning/50 text-warning-text hover:bg-warning-muted font-semibold px-5 py-3 rounded-xl transition"
              >
                ⚡ Upgrader
              </Link>
            )}
          </div>
        </div>

        {entitlements && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <StatCard label="Plan" value={effectivePlan.toUpperCase()} />
            <StatCard
              label="Messages / mois"
              value={
                entitlements.limits.ai_messages_per_month === -1
                  ? "∞"
                  : String(entitlements.limits.ai_messages_per_month)
              }
            />
            <StatCard label="Crédits overage" value={String(entitlements.credits)} />
            <StatCard label="Stockage" value={entitlements.limits.storage_gb + " GB"} />
          </div>
        )}

        {showSubscriptionWarning && (
          <div className="mb-10 rounded-xl border border-warning/40 bg-warning-muted px-4 py-3 text-sm text-warning-text">
            Statut billing à surveiller:{" "}
            <span className="font-semibold uppercase">{subscriptionStatus}</span>. Les accès affichés
            reflètent les entitlements serveur en temps réel.
          </div>
        )}

        <div className="mb-5 flex items-center justify-between gap-4">
          <h2 className="text-xl font-bold text-text-primary">🧩 Vos modules</h2>
          <Link href="/dashboard/modules" className="text-sm text-primary hover:text-primary-strong">
            Gérer les modules →
          </Link>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {modules.map((mod) => (
            <ModuleCard key={mod.slug} mod={mod} />
          ))}
        </div>

        {!isPaidPlan && (
          <div className="mt-12 bg-primary-muted border border-primary/20 rounded-2xl p-8 text-center">
            <div className="text-4xl mb-3">⚡</div>
            <h3 className="text-2xl font-bold text-text-primary mb-2">
              Débloquer tous les modules
            </h3>
              <p className="text-text-secondary mb-6 max-w-md mx-auto">
               Accès complet à l&apos;IA Orchestrator, Ghost Agency, et {Math.max(MODULE_SLUGS.length - 2, 0)} autres modules de monétisation.
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

function ModuleCard({ mod }: { mod: ModuleAccess }) {
  const moduleMeta = getModulePresentation(mod);
  const agentSlug = ["operator", "ghost", "decision"].includes(moduleMeta.slug) ? moduleMeta.slug : null;

  return (
    <Card
      variant="outlined"
      padding="sm"
      className={"flex flex-col gap-3 transition " + (mod.access ? "hover:border-primary cursor-pointer" : "opacity-40")}
      >
      <div className="flex items-center gap-3">
        <span className="text-2xl">{getModuleIcon(mod.slug)}</span>
        {!mod.access && (
          <Badge variant="warning" size="sm" className="ml-auto">
            🔒 Locked
          </Badge>
        )}
      </div>
      <div>
        <div className="font-semibold text-text-primary text-sm">{moduleMeta.name}</div>
        <div className="text-xs text-text-muted mt-1 line-clamp-2">{moduleMeta.description}</div>
        {mod.access && (
          <div className="mt-2 text-xs text-success">
            {mod.source === "plan" ? "Inclus dans votre plan" : "Acheté à l’unité"}
          </div>
        )}
      </div>
      {mod.access ? (
        <Link
          href={agentSlug ? `/dashboard/chat?agent=${agentSlug}` : "/dashboard/chat"}
          className="text-xs text-primary hover:text-primary-strong mt-auto"
        >
          Utiliser →
        </Link>
      ) : (
        <Link href="/dashboard/modules" className="text-xs text-warning hover:text-warning-text mt-auto">
          Voir options →
        </Link>
      )}
    </Card>
  );
}
