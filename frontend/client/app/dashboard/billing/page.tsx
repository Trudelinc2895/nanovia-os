"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import {
  createCheckoutSession,
  createAddonCheckout,
  createPortalSession,
  getEntitlements,
  getPlans,
  getUsageStats,
  getAddons,
  type Entitlements,
  type Plan,
  type UsageStats,
  type AddonPublic,
} from "@/lib/api";
import { Button, buttonVariants, Badge, Card } from "@/components/ui";
import { getPlanBadgeVariant } from "@/lib/monetization";

function UsageBar({ count, limit, pct }: { count: number; limit: number; pct: number }) {
  const isUnlimited = limit === -1;
  const color = pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warning" : "bg-primary";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-text-secondary">
        <span>{count.toLocaleString()} messages</span>
        <span>{isUnlimited ? "illimites" : limit.toLocaleString() + " / mois"}</span>
      </div>
      {!isUnlimited && (
        <div className="w-full h-2 bg-ui-elevated rounded-full overflow-hidden">
          <div className={"h-full rounded-full transition-all " + color} style={{ width: Math.min(pct, 100) + "%" }} />
        </div>
      )}
    </div>
  );
}

export default function BillingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [usage, setUsage] = useState<UsageStats | null>(null);
  const [addons, setAddons] = useState<AddonPublic[]>([]);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [user, loading, router]);

  useEffect(() => {
    if (!user) return;
    Promise.all([getPlans(), getEntitlements(), getUsageStats(), getAddons()]).then(
      ([p, e, u, a]) => {
        setPlans(p ?? []);
        setEntitlements(e ?? null);
        setUsage(u ?? null);
        setAddons(a ?? []);
      }
    );
  }, [user]);

  const handleSubscribe = async (planSlug: string, cadence: "monthly" | "yearly") => {
    setActionLoading(planSlug + "_" + cadence);
    setError(null);
    try {
      const { url } = await createCheckoutSession(planSlug, cadence);
      if (url) window.location.assign(url);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erreur checkout");
    } finally {
      setActionLoading(null);
    }
  };

  const handleAddon = async (slug: string) => {
    setActionLoading(slug);
    try {
      const { url } = await createAddonCheckout(slug);
      if (url) window.location.assign(url);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erreur addon");
    } finally {
      setActionLoading(null);
    }
  };

  const handlePortal = async () => {
    setActionLoading("portal");
    try {
      const { url } = await createPortalSession();
      if (url) window.location.assign(url);
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erreur portail");
    } finally {
      setActionLoading(null);
    }
  };

  const currentPlan = entitlements?.plan ?? "free";
  const isActive = entitlements?.status === "active";
  const upsell = entitlements?.upsell ?? null;

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-base">
        <p className="text-text-secondary animate-pulse">Chargement...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="border-b border-ui-border bg-ui-surface px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold text-primary">Nanovia</span>
          <span className="text-text-muted text-sm">/</span>
          <span className="text-text-secondary text-sm">Abonnement</span>
        </div>
        <div className="flex items-center gap-4">
          <Badge variant={getPlanBadgeVariant(currentPlan)} size="sm">{currentPlan.toUpperCase()}</Badge>
          <a href="/dashboard" className={buttonVariants("ghost", "sm")}>Tableau de bord</a>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-10 space-y-10">
        {error && (
          <div className="rounded-lg bg-danger/10 border border-danger/30 text-danger-text p-3 text-sm">{error}</div>
        )}

        {usage && usage.usage_pct >= 80 && (
          <div className={`rounded-xl border p-4 flex items-start gap-3 ${
            usage.usage_pct >= 95
              ? "bg-red-900/20 border-red-700/40 text-red-300"
              : "bg-yellow-900/20 border-yellow-700/40 text-yellow-300"
          }`}>
            <span className="text-lg">⚠️</span>
            <div>
              <p className="font-semibold text-sm">
                {usage.usage_pct >= 95 ? "Limite presque atteinte!" : "Attention — utilisation élevée"}
              </p>
              <p className="text-xs mt-0.5 opacity-80">
                Tu as utilisé {usage.usage_pct.toFixed(0)}% de ton quota mensuel.
                {usage.usage_pct >= 95
                  ? " Passe à un forfait supérieur pour éviter les interruptions."
                  : " Surveille ta consommation ou envisage une mise à niveau."}
              </p>
            </div>
          </div>
        )}

        {upsell && (
          <div className="rounded-xl border border-primary/30 bg-primary-muted p-4">
            <p className="text-sm font-semibold text-text-primary">{upsell.headline}</p>
            <p className="text-xs text-text-secondary mt-1">
              Passer a <span className="text-primary font-medium">{upsell.next_plan_name}</span>
              {" — a partir de $"}{upsell.price_monthly_usd}{"/mois"}
            </p>
            <div className="flex gap-2 mt-3 flex-wrap">
              <Button size="sm" onClick={() => handleSubscribe(upsell.next_plan, "monthly")} loading={actionLoading === upsell.next_plan + "_monthly"}>
                Mensuel — ${upsell.price_monthly_usd}
              </Button>
              <Button size="sm" variant="secondary" onClick={() => handleSubscribe(upsell.next_plan, "yearly")} loading={actionLoading === upsell.next_plan + "_yearly"}>
                Annuel — ${upsell.price_yearly_usd}
              </Button>
            </div>
          </div>
        )}

        <Card variant="outlined">
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <h2 className="text-lg font-semibold text-text-primary">Abonnement actuel</h2>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant={getPlanBadgeVariant(currentPlan)}>{currentPlan.toUpperCase()}</Badge>
                {isActive && <Badge variant="success" size="sm">Actif</Badge>}
                {!isActive && currentPlan !== "free" && <Badge variant="warning" size="sm">Inactif</Badge>}
              </div>
              {entitlements?.subscription?.current_period_end && (
                <p className="text-xs text-text-muted mt-1">
                  Renouvellement: {new Date(entitlements.subscription.current_period_end).toLocaleDateString("fr-CA")}
                </p>
              )}
            </div>
            {currentPlan !== "free" && (
              <Button variant="secondary" size="sm" onClick={handlePortal} loading={actionLoading === "portal"}>
                Gerer abonnement
              </Button>
            )}
          </div>
        </Card>

        {usage && (
          <Card variant="outlined">
            <h2 className="text-lg font-semibold text-text-primary mb-4">Utilisation</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
              <UsageBar count={usage.messages_count} limit={usage.messages_limit} pct={usage.usage_pct} />
              <div className="text-sm text-text-secondary">
                <span className="font-medium text-text-primary">Credits: </span>
                {usage.credits_remaining.toLocaleString()}
              </div>
            </div>
          </Card>
        )}

        <section>
          <h2 className="text-xl font-semibold text-text-primary mb-4">Plans disponibles</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {plans.map((plan) => {
              const isCurrent = plan.slug === currentPlan;
              return (
                <Card key={plan.slug} variant={isCurrent ? "solid" : "outlined"} className={isCurrent ? "border-primary/60" : ""}>
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="text-base font-bold text-text-primary capitalize">{plan.name}</h3>
                    {isCurrent && <Badge variant="info" size="sm">Actif</Badge>}
                  </div>
                  <p className="text-2xl font-bold text-primary mb-4">
                    {plan.price_monthly_usd === 0 ? "Gratuit" : "$" + plan.price_monthly_usd + "/mois"}
                  </p>
                  <ul className="space-y-1 mb-6 text-sm text-text-secondary">
                    {plan.features.slice(0, 5).map((f) => (
                      <li key={f} className="flex items-center gap-1">
                        <span className="text-primary text-xs">+</span> {f}
                      </li>
                    ))}
                  </ul>
                  {!isCurrent && (
                    <Button variant="primary" size="sm" fullWidth onClick={() => handleSubscribe(plan.slug, "monthly")} loading={actionLoading === plan.slug + "_monthly"}>
                      Choisir
                    </Button>
                  )}
                  {isCurrent && <p className="text-xs text-center text-text-muted">Plan actuel</p>}
                </Card>
              );
            })}
          </div>
        </section>

        {addons.length > 0 && (
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-4">Add-ons</h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {addons.map((addon) => (
                <Card key={addon.slug} variant="outlined">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h3 className="font-semibold text-text-primary text-sm">{addon.name}</h3>
                      <p className="text-xs text-text-secondary mt-0.5">{addon.description}</p>
                      <p className="text-primary font-bold mt-2">${addon.price_usd} USD</p>
                    </div>
                    <Button size="sm" variant="secondary" onClick={() => handleAddon(addon.slug)} loading={actionLoading === addon.slug} className="shrink-0">
                      Ajouter
                    </Button>
                  </div>
                </Card>
              ))}
            </div>
          </section>
        )}

        {entitlements?.features_enabled && (
          <section>
            <h2 className="text-xl font-semibold text-text-primary mb-4">Fonctionnalites</h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
              {Object.entries(entitlements.features_enabled).map(([key, enabled]) => (
                <div key={key} className={"rounded-xl p-3 text-center text-xs border " + (enabled ? "bg-primary-muted border-primary/30 text-primary" : "bg-ui-elevated border-ui-border text-text-muted")}>
                  <div className="text-lg mb-1">{enabled ? "+" : "-"}</div>
                  <div>{key.replace(/_/g, " ")}</div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
