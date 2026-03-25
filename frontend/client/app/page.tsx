"use client";
import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8010";

const PLANS = [
  {
    key: "starter",
    name: "Starter",
    price: "$0",
    period: "",
    desc: "Commence gratuitement",
    features: ["1 workspace", "AI Operator basique", "Support communauté", "Accès dashboard"],
    cta: "Commencer gratis",
    highlight: false,
  },
  {
    key: "pro",
    name: "Pro",
    price: "$49",
    period: "/mois",
    desc: "Pour freelancers & solopreneurs",
    features: ["Modules 1–5 complets", "5 workspaces", "Ghost Agency templates", "Support prioritaire", "API access"],
    cta: "Démarrer Pro",
    highlight: true,
  },
  {
    key: "business",
    name: "Business",
    price: "$149",
    period: "/mois",
    desc: "Pour agences & équipes",
    features: ["Tous les 10 modules", "Workspaces illimités", "Automation Agency tools", "Support dédié", "Custom integrations", "White-label"],
    cta: "Démarrer Business",
    highlight: false,
  },
];

const MODULES = [
  { icon: "🤖", title: "AI Personal Operator", desc: "Un employé digital qui gère tes emails, décisions et tâches — 24/7." },
  { icon: "📡", title: "Content Cloner Engine", desc: "Prend le contenu viral → le restructure → publie sur toutes tes plateformes." },
  { icon: "⚙️", title: "Micro-SaaS Invisible", desc: "Lance un outil ultra-spécifique en 24h. Un problème, une solution, des abonnés." },
  { icon: "👻", title: "Ghost Automation Agency", desc: "Automatise les tâches répétitives de tes clients. Ils paient, tu livres." },
  { icon: "🧠", title: "AI Decision Engine", desc: "Analyse, structure et recommande. Prends des meilleures décisions plus vite." },
  { icon: "📚", title: "Knowledge Weapon System", desc: "Transforme livres, vidéos, formations en plans d action immédiat." },
];

export default function Home() {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState("");

  async function handleCheckout(planKey: string) {
    if (!email || !email.includes("@")) {
      setEmailError("Entre ton email d abord.");
      return;
    }
    setEmailError("");
    setLoadingPlan(planKey);
    try {
      const res = await fetch(`${API}/api/v1/billing/checkout-session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: planKey, email }),
      });
      const data = await res.json();
      if (data.url) window.location.href = data.url;
      else alert("Erreur: " + JSON.stringify(data));
    } catch (e) {
      alert("Erreur réseau. Réessaie.");
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
          <div className="flex items-center gap-6 text-sm text-gray-400">
            <a href="#modules" className="hover:text-white transition">Modules</a>
            <a href="#pricing" className="hover:text-white transition">Tarifs</a>
            <a href="#pricing" className="bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg transition font-medium">
              Démarrer
            </a>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="pt-40 pb-24 px-6 text-center max-w-4xl mx-auto">
        <div className="inline-block bg-violet-600/20 border border-violet-500/30 text-violet-300 text-sm px-4 py-1.5 rounded-full mb-6">
          🚀 Mode SAAS EXPERT — Production-Grade
        </div>
        <h1 className="text-5xl md:text-7xl font-extrabold leading-tight mb-6">
          Ton business IA.<br />
          <span className="text-violet-400">Automatisé. Rentable.</span>
        </h1>
        <p className="text-xl text-gray-400 mb-10 max-w-2xl mx-auto">
          10 modules d automatisation IA qui génèrent des revenus.
          Ghost Agency, AI Operator, Micro-SaaS — tout dans un système.
        </p>

        {/* Email capture + CTA */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center max-w-md mx-auto">
          <input
            type="email"
            placeholder="ton@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-violet-500"
          />
          <button
            onClick={() => handleCheckout("pro")}
            disabled={!!loadingPlan}
            className="bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-bold px-6 py-3 rounded-lg transition whitespace-nowrap"
          >
            {loadingPlan === "pro" ? "⏳ Chargement..." : "Démarrer Pro — $49/mois"}
          </button>
        </div>
        {emailError && <p className="text-red-400 text-sm mt-2">{emailError}</p>}
        <p className="text-gray-600 text-sm mt-4">✓ Sans engagement · ✓ Annulable à tout moment · ✓ Mode test actif</p>
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
              <h3 className="font-bold text-lg mb-2 group-hover:text-violet-400 transition">{m.title}</h3>
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

          {/* Email pour pricing */}
          <div className="max-w-sm mx-auto mb-10">
            <input
              type="email"
              placeholder="ton@email.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:border-violet-500"
            />
            {emailError && <p className="text-red-400 text-sm mt-1">{emailError}</p>}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {PLANS.map((plan) => (
              <div
                key={plan.key}
                className={`rounded-2xl p-8 border ${
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
                <div className="text-4xl font-extrabold mb-6">
                  {plan.price}<span className={`text-lg font-normal ${plan.highlight ? "text-violet-200" : "text-gray-400"}`}>{plan.period}</span>
                </div>
                <ul className="space-y-2 mb-8">
                  {plan.features.map((f) => (
                    <li key={f} className={`text-sm flex gap-2 ${plan.highlight ? "text-violet-100" : "text-gray-300"}`}>
                      <span className="text-green-400 flex-shrink-0">✓</span>{f}
                    </li>
                  ))}
                </ul>
                <button
                  onClick={() => plan.key !== "starter" ? handleCheckout(plan.key) : null}
                  disabled={!!loadingPlan}
                  className={`w-full py-3 rounded-xl font-bold text-sm transition disabled:opacity-50 ${
                    plan.highlight
                      ? "bg-white text-violet-700 hover:bg-gray-100"
                      : "bg-gray-800 hover:bg-gray-700 border border-gray-700"
                  }`}
                >
                  {loadingPlan === plan.key ? "⏳ Chargement..." : plan.cta}
                </button>
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
          <a href="mailto:admin@tkverse.ca" className="hover:text-white transition">Contact</a>
        </div>
      </footer>
    </main>
  );
}
