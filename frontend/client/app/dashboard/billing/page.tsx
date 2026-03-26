"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  createCheckoutSession,
  createPortalSession,
  getEntitlements,
  getPlans,
  type Entitlements,
  type Plan,
} from "@/lib/api";

export default function BillingPage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [yearly, setYearly] = useState(false);
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    getPlans().then(setPlans).catch(console.error);
    getEntitlements().then(setEntitlements).catch(console.error);
  }, [user]);

  const handleUpgrade = async (slug: string) => {
    setLoadingPlan(slug);
    try {
      const res = await createCheckoutSession(slug, yearly);
      window.location.href = res.url;
    } catch (err) {
      alert(`Erreur: ${err instanceof Error ? err.message : "Impossible de lancer le paiement"}`);
      setLoadingPlan(null);
    }
  };

  const handlePortal = async () => {
    try {
      const res = await createPortalSession();
      window.location.href = res.url;
    } catch (err) {
      alert(`Erreur portail: ${err instanceof Error ? err.message : err}`);
    }
  };

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-purple-400 animate-pulse">Chargement...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-950">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link href="/dashboard" className="text-gray-500 hover:text-white transition">←</Link>
          <span className="text-white font-bold">💳 Billing & Plans</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        {/* Current plan banner */}
        {entitlements && (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 mb-10 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="text-sm text-gray-500 mb-1">Plan actuel</div>
              <div className="text-2xl font-bold text-white uppercase">{entitlements.plan}</div>
              <div className="text-sm text-gray-400 mt-1">
                {entitlements.modules.length} modules • {entitlements.ai_messages_per_month === 999999 ? "Messages illimités" : `${entitlements.ai_messages_per_month} messages/mois`}
              </div>
            </div>
            {entitlements.plan !== "free" && (
              <button
                onClick={handlePortal}
                className="border border-gray-700 hover:border-purple-600 text-gray-300 hover:text-white px-5 py-2.5 rounded-xl text-sm transition"
              >
                Gérer l&apos;abonnement →
              </button>
            )}
          </div>
        )}

        {/* Toggle */}
        <div className="flex items-center justify-center gap-4 mb-10">
          <span className={`text-sm ${!yearly ? "text-white" : "text-gray-500"}`}>Mensuel</span>
          <button
            onClick={() => setYearly(!yearly)}
            className={`relative w-12 h-6 rounded-full transition ${yearly ? "bg-purple-600" : "bg-gray-700"}`}
          >
            <span
              className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${yearly ? "translate-x-6" : ""}`}
            />
          </button>
          <span className={`text-sm ${yearly ? "text-white" : "text-gray-500"}`}>
            Annuel <span className="text-green-400 text-xs">(-20%)</span>
          </span>
        </div>

        {/* Plans */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {plans.map((plan) => {
            const isCurrent = entitlements?.plan === plan.slug;
            const price = yearly ? plan.price_yearly : plan.price_monthly;
            const isPopular = plan.slug === "pro";

            return (
              <div
                key={plan.slug}
                className={`bg-gray-900 border rounded-2xl p-6 flex flex-col ${
                  isPopular ? "border-purple-500 shadow-lg shadow-purple-500/10" : "border-gray-800"
                }`}
              >
                {isPopular && (
                  <div className="text-xs font-bold text-purple-400 uppercase tracking-wider mb-3">
                    ★ Populaire
                  </div>
                )}
                <div className="font-bold text-white text-lg capitalize mb-1">{plan.name}</div>
                <div className="text-3xl font-black text-white mb-1">
                  {price === 0 ? "Gratuit" : `$${price}`}
                </div>
                {price > 0 && (
                  <div className="text-xs text-gray-500 mb-4">
                    / {yearly ? "an" : "mois"}
                  </div>
                )}

                <ul className="space-y-2 text-sm text-gray-400 flex-1 my-4">
                  {plan.features.map((f, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <span className="text-green-400 mt-0.5">✓</span>
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>

                {isCurrent ? (
                  <div className="w-full text-center bg-gray-800 text-gray-400 font-semibold py-2.5 rounded-xl text-sm">
                    Plan actuel
                  </div>
                ) : (
                  <button
                    onClick={() => plan.slug !== "free" && handleUpgrade(plan.slug)}
                    disabled={!!loadingPlan || plan.slug === "free"}
                    className={`w-full font-semibold py-2.5 rounded-xl text-sm transition ${
                      plan.slug === "free"
                        ? "bg-gray-800 text-gray-500 cursor-default"
                        : isPopular
                        ? "bg-purple-600 hover:bg-purple-500 text-white"
                        : "border border-gray-700 hover:border-purple-600 text-gray-300 hover:text-white"
                    } disabled:opacity-50`}
                  >
                    {loadingPlan === plan.slug ? "Redirection..." : plan.slug === "free" ? "Gratuit" : "Choisir"}
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
