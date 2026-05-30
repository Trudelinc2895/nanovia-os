"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  createCheckoutSession,
  getAccessToken,
  getBillingModules,
  getPlans,
  type BillingModulePublic,
  type Plan,
} from "@/lib/api";
import { TurnstileWidget } from "@/components/turnstile-widget";
import { Badge, Button, Card, buttonVariants } from "@/components/ui";
import { getModuleIcon, getPlanBadgeVariant, MODULE_SLUGS } from "@/lib/monetization";

const TURNSTILE_ENABLED = Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY);

function formatPlanCta(planSlug: string): string {
  if (planSlug === "free") return "Commencer gratis";
  if (planSlug === "business") return "Demarrer Business";
  return "Demarrer Pro";
}

export default function Home() {
  const [loadingPlan, setLoadingPlan] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState("");
  const [yearly, setYearly] = useState(false);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [modules, setModules] = useState<BillingModulePublic[]>([]);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getPlans(), getBillingModules()])
      .then(([plansData, modulesData]) => {
        setPlans(plansData);
        setModules(modulesData);
      })
      .catch(() => {
        setErrorMsg("Catalogue temporairement indisponible. Reessaie dans quelques instants.");
      });
  }, []);

  async function handleCheckout(planKey: string) {
    setErrorMsg("");
    setLoadingPlan(planKey);
    try {
      // Token lives in memory (api.ts _accessToken), not sessionStorage
      if (!getAccessToken()) {
        window.location.href = `/register?plan=${planKey}`;
        return;
      }
      if (TURNSTILE_ENABLED && !turnstileToken) {
        setErrorMsg("Valide la protection Cloudflare avant de lancer le paiement.");
        return;
      }
      const interval: "monthly" | "yearly" = yearly ? "yearly" : "monthly";
      const data = await createCheckoutSession(planKey, interval, turnstileToken);
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
    <main className="min-h-screen bg-bg-base text-text-primary">

      {/* NAV */}
      <nav className="fixed top-0 w-full z-50 bg-bg-base/85 backdrop-blur border-b border-ui-border">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <span className="text-xl font-bold text-primary">Nanovia OS</span>
          <div className="flex items-center gap-3 text-sm">
            <a href="#modules" className="text-text-muted hover:text-text-primary transition hidden sm:block">Modules</a>
            <a href="#pricing" className="text-text-muted hover:text-text-primary transition hidden sm:block">Tarifs</a>
            <Link href="/login" className={buttonVariants("ghost", "sm")}>
              Connexion
            </Link>
            <Link
              href="/register"
              className={buttonVariants("primary", "sm")}
            >
              Commencer gratis
            </Link>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <section className="pt-40 pb-24 px-6 text-center max-w-4xl mx-auto">
        <div className="mb-6">
          <Badge variant="info" className="px-4 py-1.5 rounded-full text-sm">
          🚀 Mode SaaS Expert — Production-Grade
          </Badge>
        </div>
        <h1 className="text-5xl md:text-7xl font-extrabold leading-tight mb-6">
          Ton business IA.<br />
          <span className="text-primary">Automatise. Rentable.</span>
        </h1>
        <p className="text-xl text-text-secondary mb-10 max-w-2xl mx-auto">
          Une plateforme SaaS unifiee pour vendre, activer et gerer des modules IA avec
          une monetisation decidee cote serveur.
        </p>
        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link
            href="/register"
            className={buttonVariants("primary", "lg")}
          >
            Commencer gratis
          </Link>
          <a
            href="#pricing"
            className={buttonVariants("secondary", "lg")}
          >
            Voir les tarifs
          </a>
        </div>
        <p className="text-text-muted text-sm mt-5">Sans carte · Annulable a tout moment · Catalogue backend unique</p>
      </section>

      {/* SOCIAL PROOF */}
      <section className="py-10 border-y border-ui-border bg-ui-surface/60">
        <div className="max-w-4xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            {[[String(MODULE_SLUGS.length), "Modules IA"], ["$0", "Pour commencer"], ["24h", "Prototype live"], ["100%", "Ownership"]].map(([n, l]) => (
            <Card key={l} variant="outlined" padding="md">
              <div className="text-3xl font-extrabold text-primary">{n}</div>
              <div className="text-text-secondary text-sm mt-1">{l}</div>
            </Card>
          ))}
        </div>
      </section>

      {/* MODULES */}
      <section id="modules" className="py-24 px-6 max-w-6xl mx-auto">
        <div className="text-center mb-14">
          <h2 className="text-4xl font-bold mb-4">{MODULE_SLUGS.length} modules. 1 système.</h2>
          <p className="text-text-secondary text-lg">Tous les prix affiches ici viennent du catalogue billing du backend.</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {modules.map((module) => (
            <Card key={module.slug} variant="outlined" className="group border-ui-border hover:border-primary/50 transition-colors">
              <div className="text-3xl mb-3">{getModuleIcon(module.slug)}</div>
              <div className="flex items-start justify-between mb-2">
                <h3 className="font-bold text-lg group-hover:text-primary transition leading-tight">{module.name}</h3>
                <span className="text-primary font-bold text-sm ml-3 whitespace-nowrap">${module.price_usd}/mo</span>
              </div>
              <p className="text-text-secondary text-sm leading-relaxed">{module.description}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* PRICING */}
      <section id="pricing" className="py-24 px-6 bg-ui-surface/40">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-14">
            <h2 className="text-4xl font-bold mb-4">Tarifs simples et transparents</h2>
            <p className="text-text-secondary">Commence gratis. Scale quand tu es pret.</p>
          </div>

          {/* Annual / Monthly toggle */}
          <div className="flex items-center justify-center gap-4 mb-10">
            <span className={`text-sm font-medium ${!yearly ? "text-text-primary" : "text-text-muted"}`}>Mensuel</span>
            <button
              onClick={() => setYearly(!yearly)}
              className={`relative w-12 h-6 rounded-full transition-colors ${yearly ? "bg-primary" : "bg-ui-border"}`}
              aria-label="Toggle annual billing"
            >
              <span className={`absolute top-1 left-1 w-4 h-4 bg-white rounded-full transition-transform ${yearly ? "translate-x-6" : ""}`} />
            </button>
            <span className={`text-sm font-medium ${yearly ? "text-text-primary" : "text-text-muted"}`}>
              Annuel <span className="text-success-text font-bold">(-17%)</span>
            </span>
          </div>

          {errorMsg && (
            <div className="max-w-md mx-auto mb-8 bg-danger-muted border border-danger/30 text-danger-text rounded-lg px-4 py-3 text-sm text-center">
              {errorMsg}
            </div>
          )}

          <div className="max-w-md mx-auto mb-8">
            <TurnstileWidget action="billing_checkout" onTokenChange={setTurnstileToken} />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {plans.map((plan) => (
              <Card
                key={plan.slug}
                variant={plan.highlight ? "solid" : "outlined"}
                className={`flex flex-col ${
                  plan.highlight
                    ? "border border-primary/40 scale-105 shadow-[0_20px_60px_rgba(79,140,255,0.2)]"
                    : "border-ui-border"
                }`}
              >
                {plan.highlight && (
                  <div className="mb-4">
                    <Badge variant={getPlanBadgeVariant(plan.slug)}>Populaire</Badge>
                  </div>
                )}
                <h3 className="text-xl font-bold mb-1">{plan.name}</h3>
                <p className={`text-sm mb-4 ${plan.highlight ? "text-text-primary" : "text-text-secondary"}`}>{plan.marketing_description}</p>
                <div className="text-4xl font-extrabold mb-1">
                  {yearly && plan.price_yearly_usd > 0
                    ? <>${plan.price_yearly_usd}<span className={`text-lg font-normal ${plan.highlight ? "text-text-primary" : "text-text-secondary"}`}>/an</span></>
                    : <>{plan.price_monthly_usd === 0 ? "$0" : `$${plan.price_monthly_usd}`}<span className={`text-lg font-normal ${plan.highlight ? "text-text-primary" : "text-text-secondary"}`}>{plan.price_monthly_usd === 0 ? "" : "/mois"}</span></>
                  }
                </div>
                {yearly && plan.yearly_discount_pct > 0 && (
                  <p className={`text-xs mb-5 ${plan.highlight ? "text-success-text" : "text-success-text"} font-semibold`}>
                    -{plan.yearly_discount_pct}% — economie annuelle
                  </p>
                )}
                {!yearly && plan.price_yearly_usd > 0 && (
                  <p className={`text-xs mb-5 ${plan.highlight ? "text-text-primary" : "text-text-muted"}`}>
                    ${plan.price_yearly_usd}/an · <span className="text-success-text">-{plan.yearly_discount_pct}%</span>
                  </p>
                )}
                <ul className="space-y-2 mb-8 flex-1">
                  {plan.features.map((f) => (
                    <li key={f} className={`text-sm flex gap-2 ${plan.highlight ? "text-text-primary" : "text-text-secondary"}`}>
                      <span className="text-success-text flex-shrink-0">+</span>{f}
                    </li>
                  ))}
                </ul>
                {plan.slug === "free" ? (
                  <Link
                    href="/register"
                    className={`w-full text-center ${buttonVariants(
                      plan.highlight
                        ? "secondary"
                        : "secondary",
                      "md",
                      true,
                    )}`}
                  >
                    {formatPlanCta(plan.slug)}
                  </Link>
                ) : (
                  <Button
                    onClick={() => handleCheckout(plan.slug)}
                    loading={loadingPlan === plan.slug}
                    variant={plan.highlight ? "secondary" : "primary"}
                    fullWidth
                  >
                    {loadingPlan === plan.slug ? "Chargement..." : formatPlanCta(plan.slug)}
                  </Button>
                )}
              </Card>
            ))}
          </div>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="py-12 border-t border-ui-border text-center text-text-muted text-sm">
        <p className="text-primary font-bold text-lg mb-2">Nanovia OS</p>
        <p>Propulse par Nanovia · nanovia.ca</p>
        <p className="mt-2">© 2026 Kevin Trudel — Tous droits réservés</p>
        <div className="flex justify-center gap-6 mt-4">
          <a href="/privacy" className="hover:text-text-primary transition">Confidentialité</a>
          <a href="/terms" className="hover:text-text-primary transition">CGU</a>
          <Link href="/contact" className="hover:text-text-primary transition">Contact</Link>
        </div>
      </footer>
    </main>
  );
}
