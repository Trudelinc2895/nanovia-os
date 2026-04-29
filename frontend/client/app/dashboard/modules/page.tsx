"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  getMyModules,
  createModuleCheckout,
  type ModuleAccess,
} from "@/lib/api";
import { getModulePresentation, getPlanTextClass } from "@/lib/monetization";

function SkeletonCard() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-2xl p-5 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-gray-800 rounded-xl shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-4 bg-gray-800 rounded w-3/4" />
          <div className="h-3 bg-gray-800 rounded w-full" />
          <div className="h-3 bg-gray-800 rounded w-2/3" />
        </div>
      </div>
      <div className="mt-4 h-9 bg-gray-800 rounded-xl" />
    </div>
  );
}

function ModuleCard({ mod }: { mod: ModuleAccess }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const moduleMeta = getModulePresentation(mod);

  const handleActivate = async () => {
    setLoading(true);
    setError("");
    try {
      const res = await createModuleCheckout(mod.slug);
      window.location.href = res.url;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur de paiement");
      setLoading(false);
    }
  };

  const badge =
    mod.source === "plan" ? (
      <span className="inline-flex items-center gap-1 text-xs bg-green-900/40 text-green-400 border border-green-700/30 px-2 py-0.5 rounded-full font-medium">
        ✓ Inclus dans votre plan
      </span>
    ) : mod.source === "purchased" ? (
      <span className="inline-flex items-center gap-1 text-xs bg-blue-900/40 text-blue-400 border border-blue-700/30 px-2 py-0.5 rounded-full font-medium">
        ✓ Acheté
      </span>
    ) : (
      <span className="inline-flex items-center gap-1 text-xs bg-gray-800 text-gray-500 border border-gray-700 px-2 py-0.5 rounded-full font-medium">
        🔒 Verrouillé
      </span>
    );

  return (
    <div
      className={`bg-gray-900 border rounded-2xl p-5 flex flex-col gap-4 transition ${
        mod.access
          ? "border-gray-700 hover:border-violet-700/50"
          : "border-gray-800 opacity-80"
      }`}
    >
      <div className="flex items-start gap-4">
        <div className="text-3xl w-10 h-10 flex items-center justify-center bg-gray-800 rounded-xl shrink-0">
          {moduleMeta.icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="font-bold text-white text-sm">{moduleMeta.name}</span>
            {badge}
          </div>
          <p className="text-xs text-gray-400 leading-relaxed">{moduleMeta.description}</p>
          {!mod.access && moduleMeta.priceUsd > 0 && (
            <p className="text-xs text-violet-300 mt-1 font-semibold">
              ${moduleMeta.priceUsd}/mois
            </p>
          )}
        </div>
      </div>

      {!mod.access && mod.stripe_price_id_available && (
        <div>
          <button
            onClick={handleActivate}
            disabled={loading}
            className="w-full bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white font-semibold py-2 px-4 rounded-xl text-sm transition"
          >
            {loading ? "Redirection..." : `Activer — $${moduleMeta.priceUsd}/mois`}
          </button>
          {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
        </div>
      )}

      {!mod.access && !mod.stripe_price_id_available && (
        <div className="w-full text-center text-xs text-gray-600 bg-gray-800/50 rounded-xl py-2 px-4">
          Bientôt disponible
        </div>
      )}
    </div>
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
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="text-violet-400 animate-pulse">Chargement...</div>
      </div>
    );
  }

  const planColor = getPlanTextClass(plan);
  const activeModules = modules.filter((m) => m.access);
  const lockedModules = modules.filter((m) => !m.access);

  const displayedModules =
    filter === "active"
      ? activeModules
      : filter === "locked"
      ? lockedModules
      : modules;

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link href="/dashboard" className="text-gray-500 hover:text-white transition">
              ←
            </Link>
            <span className="font-bold">🧩 Mes Modules</span>
          </div>
          {plan && (
            <span className={`text-sm font-semibold uppercase ${planColor}`}>
              Plan {plan}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10 space-y-8">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl px-4 py-3 text-sm flex items-center justify-between">
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
          <div className="bg-violet-950/40 border border-violet-700/40 rounded-2xl p-6 flex items-center justify-between gap-4">
            <div>
              <h2 className="font-bold text-white text-base mb-1">✨ Custom Modules</h2>
              <p className="text-sm text-gray-400">
                Créez vos propres modules IA (Plan Business)
              </p>
            </div>
            <Link
              href="/dashboard/modules/custom"
              className="shrink-0 bg-violet-700 hover:bg-violet-600 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition"
            >
              Gérer →
            </Link>
          </div>
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
                    ? "bg-violet-700 text-white"
                    : "bg-gray-800 text-gray-400 hover:text-white"
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
          <div className="text-center py-20 text-gray-500">
            <div className="text-5xl mb-4">📦</div>
            <p className="text-lg font-semibold text-gray-400">Aucun module trouvé</p>
            <p className="text-sm mt-1">
              {filter === "active"
                ? "Vous n'avez pas encore de module actif."
                : "Tous vos modules sont déjà actifs !"}
            </p>
          </div>
        ) : (
          <>
            {filter === "all" && activeModules.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  ✓ Actifs — {activeModules.length} module{activeModules.length > 1 ? "s" : ""}
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {activeModules.map((mod) => (
                    <ModuleCard key={mod.slug} mod={mod} />
                  ))}
                </div>
              </section>
            )}

            {filter === "all" && lockedModules.length > 0 && (
              <section>
                <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-4">
                  🔒 Disponibles — {lockedModules.length} module{lockedModules.length > 1 ? "s" : ""}
                </h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                  {lockedModules.map((mod) => (
                    <ModuleCard key={mod.slug} mod={mod} />
                  ))}
                </div>
              </section>
            )}

            {filter !== "all" && (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
                {displayedModules.map((mod) => (
                  <ModuleCard key={mod.slug} mod={mod} />
                ))}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
