"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { TurnstileWidget } from "@/components/turnstile-widget";
import { Badge, Button, Card, buttonVariants } from "@/components/ui";
import { useAuth } from "@/lib/auth-context";
import {
  getMyModules,
  createModuleCheckout,
  type ModuleAccess,
} from "@/lib/api";
import { getModulePresentation, getPlanBadgeVariant, getPlanDisplayName } from "@/lib/monetization";

const TURNSTILE_ENABLED = Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY);

function SkeletonCard() {
  return (
    <Card variant="outlined" className="animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-ui-elevated rounded-xl shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-ui-elevated rounded w-3/4" />
          <div className="h-3 bg-ui-elevated rounded w-full" />
          <div className="h-3 bg-ui-elevated rounded w-2/3" />
        </div>
      </div>
      <div className="mt-4 h-9 bg-ui-elevated rounded-xl" />
    </Card>
  );
}

function ModuleCard({ mod, turnstileToken }: { mod: ModuleAccess; turnstileToken: string | null }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const moduleMeta = getModulePresentation(mod);

  const handleActivate = async () => {
    setLoading(true);
    setError("");
    try {
      if (TURNSTILE_ENABLED && !turnstileToken) {
        setError("Valide la protection Cloudflare avant d'activer ce module.");
        setLoading(false);
        return;
      }
      const res = await createModuleCheckout(mod.slug, turnstileToken);
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de paiement");
      setLoading(false);
    }
  };

  const badge =
    mod.source === "plan" ? (
      <Badge variant="success" size="sm">Inclus dans votre plan</Badge>
    ) : mod.source === "purchased" ? (
      <Badge variant="info" size="sm">Achete</Badge>
    ) : (
      <Badge variant="warning" size="sm">Verrouille</Badge>
    );

  return (
    <Card
      variant="outlined"
      className={`flex flex-col gap-4 transition ${
        mod.access
          ? "border-ui-border hover:border-primary/40"
          : "border-ui-border opacity-90"
      }`}
    >
      <div className="flex items-start gap-4">
        <div className="text-3xl w-10 h-10 flex items-center justify-center bg-ui-elevated rounded-xl shrink-0">
          {moduleMeta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-bold text-text-primary text-sm">{moduleMeta.name}</span>
            {badge}
          </div>
          <p className="text-xs text-text-secondary leading-relaxed">{moduleMeta.description}</p>
          {!mod.access && moduleMeta.priceUsd > 0 && (
            <p className="text-xs text-primary mt-1 font-semibold">
              ${moduleMeta.priceUsd}/mois
            </p>
          )}
        </div>
      </div>

      {!mod.access && mod.stripe_price_id_available && (
        <div>
          <Button
            onClick={handleActivate}
            loading={loading}
            fullWidth
            size="sm"
          >
            {loading ? "Redirection..." : `Activer — $${moduleMeta.priceUsd}/mois`}
          </Button>
          {error && <p className="text-danger-text text-xs mt-2">{error}</p>}
        </div>
      )}

      {!mod.access && !mod.stripe_price_id_available && (
        <div className="w-full text-center text-xs text-text-muted bg-ui-elevated rounded-xl py-2 px-4">
          Bientôt disponible
        </div>
      )}
    </Card>
  );
}

export default function ModulesPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [plan, setPlan] = useState<string>("");
  const [modules, setModules] = useState<ModuleAccess[]>([]);
  const [fetching, setFetching] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "locked">("all");
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  const fetchModules = () => {
    if (!user) return;
    setFetching(true);
    setError("");
    getMyModules()
      .then((data) => {
        setPlan(data.plan);
        setModules(data.modules);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Impossible de charger les modules"))
      .finally(() => setFetching(false));
  };

  useEffect(() => {
    fetchModules();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-base">
        <div className="text-primary animate-pulse">Chargement...</div>
      </div>
    );
  }

  const activeModules = modules.filter((m) => m.access);
  const lockedModules = modules.filter((m) => !m.access);

  const displayedModules =
    filter === "active"
      ? activeModules
      : filter === "locked"
      ? lockedModules
      : modules;

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="border-b border-ui-border bg-ui-surface/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className={buttonVariants("ghost", "sm")}>
              ←
            </Link>
            <span className="font-bold">🧩 Mes Modules</span>
          </div>
          {plan && (
            <Badge variant={getPlanBadgeVariant(plan)} size="sm">{getPlanDisplayName(plan)}</Badge>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
        <div className="max-w-md">
          <TurnstileWidget action="billing_checkout" onTokenChange={setTurnstileToken} />
        </div>
        {error && (
          <div className="bg-danger-muted border border-danger/30 text-danger-text rounded-xl px-4 py-3 text-sm flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={fetchModules}
              className="ml-4 text-xs underline hover:no-underline"
            >
              Réessayer
            </button>
          </div>
        )}

        {/* Custom Modules CTA — Business/Enterprise only */}
        {(plan === "business" || plan === "enterprise") && (
          <Card variant="solid" className="border border-primary/30 flex items-center justify-between gap-4">
            <div>
              <h2 className="font-bold text-text-primary text-base mb-1">Custom Modules</h2>
              <p className="text-sm text-text-secondary">
                Créez vos propres modules IA (Plan Business)
              </p>
            </div>
            <Link
              href="/dashboard/modules/custom"
              className={`shrink-0 ${buttonVariants("primary", "sm")}`}
            >
              Gerer
            </Link>
          </Card>
        )}

        {/* Filter tabs */}
        <div className="flex gap-2">
          {(["all", "active", "locked"] as const).map((f) => {
            const labels = { all: "Tous", active: `Actifs (${activeModules.length})`, locked: `Disponibles (${lockedModules.length})` };
            return (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
                  filter === f
                    ? "bg-primary text-white"
                    : "bg-ui-elevated text-text-secondary hover:text-text-primary"
                }`}
              >
                {labels[f]}
              </button>
            );
          })}
        </div>

        {/* Modules grid */}
        {fetching ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : displayedModules.length === 0 ? (
          <Card variant="outlined" className="text-center py-20">
            <div className="text-5xl mb-4">📦</div>
            <p className="text-lg font-semibold text-text-secondary">Aucun module trouvé</p>
            <p className="text-sm mt-1 text-text-muted">
              {filter === "active"
                ? "Vous n'avez pas encore de module actif."
                : "Tous vos modules sont déjà actifs !"}
            </p>
          </Card>
        ) : (
          <>
            {filter === "all" && activeModules.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                  Actifs — {activeModules.length} module{activeModules.length > 1 ? "s" : ""}
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {activeModules.map((mod) => (
                    <ModuleCard key={mod.slug} mod={mod} turnstileToken={turnstileToken} />
                  ))}
                </div>
              </section>
            )}

            {filter === "all" && lockedModules.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-text-muted uppercase tracking-wider mb-4">
                  Disponibles — {lockedModules.length} module{lockedModules.length > 1 ? "s" : ""}
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {lockedModules.map((mod) => (
                    <ModuleCard key={mod.slug} mod={mod} turnstileToken={turnstileToken} />
                  ))}
                </div>
              </section>
            )}

            {filter !== "all" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {displayedModules.map((mod) => (
                  <ModuleCard key={mod.slug} mod={mod} turnstileToken={turnstileToken} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
