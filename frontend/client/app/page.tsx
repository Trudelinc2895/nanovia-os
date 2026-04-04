"use client";
import { useState } from "react";
import Link from "next/link";
import { createCheckoutSession, getAccessToken } from "@/lib/api";

const PLANS = [
  {
    key: "free",
    name: "Free",
    price: "$0",
    period: "",
    yearlyPrice: null,
    desc: "Commence gratuitement",
    features: ["1 module IA", "50 messages/mois", "Support communauté", "Dashboard inclus"],
    cta: "Commencer gratis",
    ctaHref: "/register",
    highlight: false,
  },
  {
    key: "pro",
    name: "Pro",
    price: "$79",
    period: "/mois",
    yearlyPrice: "$790/an",
    yearlyDiscount: "17% off",
    desc: "Pour freelancers & solopreneurs",
    features: ["5 modules IA", "1 000 messages/mois", "Accès API", "Support prioritaire", "Export données", "Automatisations"],
    cta: "Démarrer Pro",
    ctaHref: null,
    highlight: true,
  },
  {
    key: "business",
    name: "Business",
    price: "$149",
    period: "/mois",
    yearlyPrice: "$1490/an",
    yearlyDiscount: "17% off",
    desc: "Pour agences & équipes",
    features: ["10 modules IA", "Messages illimités", "White-label", "Support dédié", "Accès anticipé", "Sièges équipe", "API illimitée"],
    cta: "Démarrer Business",
    ctaHref: null,
    highlight: false,
  },
];

const MODULES = [
  { icon: "🤖", title: "AI Personal Operator", price: "$19/mo", desc: "Un employé digital qui gère tes emails, décisions et tâches — 24/7." },
  { icon: "📡", title: "Content Cloner Engine", price: "$15/mo", desc: "Prend le contenu viral → le restructure → publie sur toutes tes plateformes." },
  { icon: "⚙️", title: "Micro-SaaS Builder", price: "$29/mo", desc: "Lance un outil ultra-spécifique en 24h. Un problème, une solution, des abonnés." },
  { icon: "👻", title: "Ghost Automation Agency", price: "$39/mo", desc: "Automatise les tâches répétitives de tes clients. Ils paient, tu livres." },
  { icon: "🧠", title: "AI Decision Engine", price: "$19/mo", desc: "Analyse, structure et recommande. Prends de meilleures décisions plus vite." },
  { icon: "📚", title: "Knowledge Weapon System", price: "$15/mo", desc: "Transforme livres, vidéos, formations en plans d'action immédiat." },
  { icon: "⚡", title: "Digital Leverage Engine", price: "$19/mo", desc: "Multiplie ta production sans multiplier tes heures." },
  { icon: "🔍", title: "Reverse Engineering Module", price: "$25/mo", desc: "Décode ce qui fonctionne chez tes compétiteurs et reproduis-le." },
  { icon: "🎯", title: "Offer Generator", price: "$15/mo", desc: "Crée des offres irrésistibles en quelques minutes avec l'IA." },
  { icon: "🚀", title: "Execution Service", price: "$29/mo", desc: "Transforme chaque idée en système exécutable et mesurable." },
];

export default function Home() {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [yearly, setYearly] = useState(false);

  async function handleCheckout(planKey: string) {
    setErrorMsg("");
    setLoadingPlan(planKey);
    try {
      // Token lives in memory (api.ts _accessToken), not sessionStorage
      if (!getAccessToken()) {
        window.location.href = `/register?plan=${planKey}`;
        return;
      }
      const interval: "monthly" | "yearly" = yearly ? "yearly" : "monthly";
      const data = await createCheckoutSession(planKey, interval);
      if (data.url) window.location.href = data.url;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Erreur lors du paiement.";
      setErrorMsg(
        msg.includes("no configured price")
          ? "Paiement temporairement indisponible — contacte le support."
          : msg || "Erreur lors du paiement. Réessaie."
      );
    } finally {
      setLoadingPlan(null);
    }
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white">

      {/* NAV */}
      <nav className="fixed top-0 w-full z-50 bg-gray-950/80 backdrop-blur border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold text-violet-400">KT Monetization OS</span>
          <div className="flex items-center gap-3 text-sm">
            <a href="#modules" className="text-gray-400 hover:text-white transition hidden sm:block">Modules</a>
            <a href="#pricing" className="text-gray-400 hover:text-white transition hidden sm:block">Tarifs</a>
            <Link href="/login" className="text-gray-400 hover:text-white transition px-3 py-2 rounded-lg">
              Connexion
            </Link>
            <Link
              href="/register"
              className="bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg transition font-medium"
            >
              Commencer gratis
            </Link>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="pt-40 pb-24 px-6 text-center max-w-4xl mx-auto">
        <div className="inline-block bg-violet-600/20 border border-violet-500/30 text-violet-300 text-sm px-4 py-1.5 rounded-full mb-6">
          🚀 Mode SaaS Expert — Production-Grade
        </div>
        <h1 className="text-5xl md:text-7xl font-extrabold leading-tight mb-6">
          Ton business IA.<br />
          <span className="text-violet-400">Automatisé. Rentable.</span>
        </h1>
        <p className="text-xl text-gray-400 mb-10 max-w-2xl mx-auto">
          10 modules d&apos;automatisation IA qui génèrent des revenus.
          Ghost Agency, AI Operator, Micro-SaaS — tout dans un système.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/register"
            className="bg-violet-600 hover:bg-violet-500 text-white font-bold px-8 py-4 rounded-xl transition text-lg"
          >
            Commencer gratis →
          </Link>
          <a
            href="#pricing"
            className="bg-gray-800 hover:bg-gray-700 text-white font-bold px-8 py-4 rounded-xl transition text-lg border border-gray-700"
          >
            Voir les tarifs
          </a>
        </div>
        <p className="text-gray-600 text-sm mt-5">✓ Sans carte · ✓ Annulable à tout moment · ✓ Mode test actif</p>
      </section>

      {/* SOCIAL PROOF */}
      <section className="py-10 border-y border-gray-800 bg-gray-900/30">
        <div className="max-w-4xl mx-auto px-6 flex flex-wrap justify-center gap-10 text-center">
          {[["10", "Modules IA"], ["$0", "Pour commencer"], ["24h", "Prototype live"], ["100%", "Ownership"]].map(([n, l]) => (
            <div key={l}>
              <div className="text-3xl font-extrabold text-violet-400">{n}</div>
              <div className="text-gray-400 text-sm mt-1">{l}</div>
            </div>
          ))}
        </div>
      </section>

      {/* MODULES */}
      <section id="modules" className="py-24 px-6 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <h2 className="text-4xl font-bold mb-4">10 modules. 1 système.</h2>
          <p className="text-gray-400 text-lg">Chaque module = une source de revenu indépendante.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {MODULES.map((m) => (
            <div key={m.title} className="bg-gray-900 border border-gray-800 rounded-xl p-6 hover:border-violet-500/50 transition group">
              <div className="text-3xl mb-3">{m.icon}</div>
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-bold text-lg group-hover:text-violet-400 transition leading-tight">{m.title}</h3>
                <span className="text-violet-400 font-bold text-sm ml-3 whitespace-nowrap">{m.price}</span>
              </div>
              <p className="text-gray-400 text-sm leading-relaxed">{m.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="py-24 px-6 bg-gray-900/30">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-4xl font-bold mb-4">Tarifs simples et transparents</h2>
            <p className="text-gray-400">Commence gratis. Scale quand tu es prêt.</p>
          </div>

          {/* Annual / Monthly toggle */}
          <div className="flex items-center justify-center gap-4 mb-10">
            <span className={`text-sm font-medium ${!yearly ? "text-white" : "text-gray-500"}`}>Mensuel</span>
            <button
              onClick={() => setYearly(!yearly)}
              className={`relative w-12 h-6 rounded-full transition-colors ${yearly ? "bg-violet-600" : "bg-gray-700"}`}
              aria-label="Toggle annual billing"
            >
              <span className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${yearly ? "translate-x-6" : ""}`} />
            </button>
            <span className={`text-sm font-medium ${yearly ? "text-white" : "text-gray-500"}`}>
              Annuel <span className="text-green-400 font-bold">(-17%)</span>
            </span>
          </div>

          {errorMsg && (
            <div className="max-w-md mx-auto mb-8 bg-red-900/40 border border-red-700 text-red-300 rounded-lg px-4 py-3 text-sm text-center">
              {errorMsg}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {PLANS.map((plan) => (
              <div
                key={plan.key}
                className={`rounded-2xl p-8 border flex flex-col ${
                  plan.highlight
                    ? "bg-violet-600 border-violet-500 scale-105 shadow-xl shadow-violet-900/40"
                    : "bg-gray-900 border-gray-800"
                }`}
              >
                {plan.highlight && (
                  <div className="text-xs font-bold bg-white/20 rounded-full px-3 py-1 inline-block mb-4 tracking-wider">
                    ⭐ POPULAIRE
                  </div>
                )}
                <h3 className="text-xl font-bold mb-1">{plan.name}</h3>
                <p className={`text-sm mb-4 ${plan.highlight ? "text-violet-200" : "text-gray-400"}`}>{plan.desc}</p>
                <div className="text-4xl font-extrabold mb-1">
                  {yearly && plan.yearlyPrice
                    ? <>{plan.yearlyPrice.split("/")[0]}<span className={`text-lg font-normal ${plan.highlight ? "text-violet-200" : "text-gray-400"}`}>/an</span></>
                    : <>{plan.price}<span className={`text-lg font-normal ${plan.highlight ? "text-violet-200" : "text-gray-400"}`}>{plan.period}</span></>
                  }
                </div>
                {yearly && plan.yearlyDiscount && (
                  <p className={`text-xs mb-5 ${plan.highlight ? "text-green-300" : "text-green-400"} font-semibold`}>
                    ✓ {plan.yearlyDiscount} — économise 2 mois
                  </p>
                )}
                {!yearly && plan.yearlyPrice && (
                  <p className={`text-xs mb-5 ${plan.highlight ? "text-violet-200" : "text-gray-500"}`}>
                    {plan.yearlyPrice} · <span className="text-green-400">{plan.yearlyDiscount}</span>
                  </p>
                )}
                <ul className="space-y-2 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className={`text-sm flex gap-2 ${plan.highlight ? "text-violet-100" : "text-gray-300"}`}>
                      <span className="text-green-400 flex-shrink-0">✓</span>{f}
                    </li>
                  ))}
                </ul>
                {plan.ctaHref ? (
                  <Link
                    href={plan.ctaHref}
                    className={`w-full py-3 rounded-xl font-bold text-sm text-center transition block ${
                      plan.highlight
                        ? "bg-white text-violet-700 hover:bg-gray-100"
                        : "bg-gray-800 hover:bg-gray-700 border border-gray-700"
                    }`}
                  >
                    {plan.cta}
                  </Link>
                ) : (
                  <button
                    onClick={() => handleCheckout(plan.key)}
                    disabled={!!loadingPlan}
                    className={`w-full py-3 rounded-xl font-bold text-sm transition disabled:opacity-50 ${
                      plan.highlight
                        ? "bg-white text-violet-700 hover:bg-gray-100"
                        : "bg-gray-800 hover:bg-gray-700 border border-gray-700"
                    }`}
                  >
                    {loadingPlan === plan.key ? "⏳ Chargement..." : plan.cta}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="py-12 border-t border-gray-800 text-center text-gray-500 text-sm">
        <p className="text-violet-400 font-bold text-lg mb-2">KT Monetization OS</p>
        <p>Propulsé par TKVerse · tkverse.ca</p>
        <p className="mt-2">© 2026 Kevin Trudel — Tous droits réservés</p>
        <div className="flex justify-center gap-6 mt-4">
          <a href="/privacy" className="hover:text-white transition">Confidentialité</a>
          <a href="/terms" className="hover:text-white transition">CGU</a>
          <Link href="/contact" className="hover:text-white transition">Contact</Link>
        </div>
      </footer>
    </main>
  );
}
