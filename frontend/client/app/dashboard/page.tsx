"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, getEntitlements, getMyModules, type Entitlements, type ModuleAccess } from "@/lib/api";
import { getModuleIcon, getModulePresentation } from "@/lib/monetization";

type NavItem = { label: string; hint: string; icon: string; href: string };

const clientNavigation: NavItem[] = [
  { label: "Intelligence", hint: "IA & agents", icon: "✦", href: "/dashboard/chat" },
  { label: "Automatisation", hint: "Modules actifs", icon: "⚙", href: "/dashboard/modules" },
  { label: "Sécurité", hint: "Protection & accès", icon: "◇", href: "/dashboard/security" },
  { label: "Performance", hint: "Usage en direct", icon: "⌁", href: "/dashboard/analytics" },
  { label: "Résultats", hint: "Plan & valeur", icon: "◎", href: "/dashboard/billing" },
];

export default function DashboardPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [entitlements, setEntitlements] = useState<Entitlements | null>(null);
  const [modules, setModules] = useState<ModuleAccess[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [backendState, setBackendState] = useState<"checking" | "online" | "limited">("checking");

  useEffect(() => {
    if (!loading && !user) router.push("/login");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    Promise.all([getEntitlements(), getMyModules()])
      .then(([rights, moduleData]) => {
        setEntitlements(rights);
        setModules(moduleData.modules);
        setBackendState("online");
      })
      .catch(() => setBackendState("limited"));
    apiFetch<{ unread_count: number }>("/api/v1/notifications")
      .then((data) => setUnreadCount(data.unread_count ?? 0))
      .catch(() => undefined);
  }, [user]);

  const activeModules = useMemo(() => modules.filter((module) => module.access), [modules]);

  if (loading || !user) {
    return <div className="noi-loading"><span className="noi-loader" />Connexion à Nanovia Intelligence…</div>;
  }

  const effectivePlan = entitlements?.plan ?? user.plan;
  const role = user.is_admin ? "Fondateur · Contrôle total" : effectivePlan === "business" ? "Équipe · Business" : "Client · Pro Pilot";
  const firstName = user.full_name?.trim().split(/\s+/)[0] || user.email.split("@")[0] || "Client";
  const messageLimit = entitlements?.limits.ai_messages_per_month;

  return (
    <div className="noi-shell">
      <aside className="noi-sidebar">
        <Link href="/dashboard" className="noi-brand" aria-label="Accueil Nanovia">
          <span className="noi-mark">N</span>
          <span><strong>NANOVIA</strong><small>OPERATING INTELLIGENCE</small></span>
        </Link>

        <div className="noi-profile">
          <span className="noi-avatar">{firstName.slice(0, 1).toUpperCase()}</span>
          <div><strong>{user.full_name || user.email}</strong><small>{role}</small></div>
        </div>

        <nav className="noi-nav" aria-label="Navigation principale">
          {clientNavigation.map((item) => (
            <Link key={item.label} href={item.href} className={pathname.startsWith(item.href) ? "active" : ""}>
              <span className="noi-nav-icon">{item.icon}</span>
              <span><strong>{item.label}</strong><small>{item.hint}</small></span>
            </Link>
          ))}
          {user.is_admin && (
            <Link href="/admin" className="noi-admin-link">
              <span className="noi-nav-icon">⌘</span><span><strong>Contrôle central</strong><small>Administration</small></span>
            </Link>
          )}
        </nav>

        <div className="noi-sidebar-bottom">
          <Link href="/dashboard/settings">⚙ Paramètres</Link>
          <button type="button" onClick={async () => { await logout(); router.push("/"); }}>↗ Déconnexion</button>
        </div>
      </aside>

      <main className="noi-main">
        <header className="noi-topbar">
          <div>
            <p className="noi-eyebrow">CENTRE D&apos;OPÉRATIONS</p>
            <h1>Bonjour {firstName}, <span>le système est prêt.</span></h1>
          </div>
          <div className="noi-top-actions">
            <span className={`noi-system-state ${backendState}`}><i />{backendState === "online" ? "Systèmes opérationnels" : backendState === "limited" ? "Connexion limitée" : "Vérification…"}</span>
            <Link href="/dashboard" className="noi-notification" aria-label={`${unreadCount} notifications`}>♢{unreadCount > 0 && <b>{unreadCount}</b>}</Link>
            <Link href="/dashboard/settings" className="noi-utility" aria-label="Paramètres">⚙</Link>
            <button type="button" className="noi-utility" aria-label="Déconnexion" onClick={async () => { await logout(); router.push("/"); }}>↗</button>
          </div>
        </header>

        <section className="noi-command">
          <div className="noi-command-copy">
            <span className="noi-orb">N</span>
            <div>
              <p>NANOVIA INTELLIGENCE</p>
              <h2>Que veux-tu accomplir aujourd&apos;hui?</h2>
              <span>Décris ton objectif. Nanovia sélectionnera l&apos;agent et le module autorisés.</span>
            </div>
          </div>
          <Link href="/dashboard/chat" className="noi-command-input">
            <span>Ex. Analyse mes opérations et propose la prochaine action rentable…</span>
            <b>→</b>
          </Link>
          <div className="noi-suggestions">
            <Link href="/dashboard/chat?agent=operator">✦ Prioriser mes actions</Link>
            <Link href="/dashboard/analytics">⌁ Analyser ma performance</Link>
            <Link href="/dashboard/modules">⚙ Automatiser une tâche</Link>
          </div>
        </section>

        <section className="noi-kpis" aria-label="État du compte">
          <Kpi label="Intelligence" value={activeModules.length ? `${activeModules.length} actifs` : "En attente"} note="Modules autorisés" tone="blue" />
          <Kpi label="Sécurité" value={user.totp_enabled ? "Renforcée" : "À compléter"} note={user.totp_enabled ? "2FA activée" : "Activer la 2FA"} tone={user.totp_enabled ? "green" : "amber"} />
          <Kpi label="Capacité IA" value={messageLimit === -1 ? "Illimitée" : String(messageLimit ?? "—")} note="Messages par mois" tone="cyan" />
          <Kpi label="Crédits" value={String(entitlements?.credits ?? user.credits)} note={`Plan ${effectivePlan.toUpperCase()}`} tone="violet" />
        </section>

        <div className="noi-grid">
          <section className="noi-panel noi-modules">
            <div className="noi-panel-head"><div><p>CAPACITÉS DISPONIBLES</p><h2>Modules intelligents</h2></div><Link href="/dashboard/modules">Tout voir →</Link></div>
            <div className="noi-module-grid">
              {modules.slice(0, 6).map((module) => {
                const meta = getModulePresentation(module);
                const agent = ["operator", "ghost", "decision"].includes(meta.slug) ? meta.slug : "operator";
                return (
                  <Link key={module.slug} href={module.access ? `/dashboard/chat?agent=${agent}` : "/dashboard/billing"} className={`noi-module ${module.access ? "enabled" : "locked"}`}>
                    <span>{getModuleIcon(module.slug)}</span>
                    <div><strong>{meta.name}</strong><small>{module.access ? "Prêt à exécuter" : "Non inclus au plan"}</small></div>
                    <i>{module.access ? "→" : "⌁"}</i>
                  </Link>
                );
              })}
            </div>
          </section>

          <section className="noi-panel noi-pilot">
            <div className="noi-panel-head"><div><p>MISSION PRIORITAIRE</p><h2>Nanovia Pro Pilot</h2></div><span className="noi-live"><i /> ACTIF</span></div>
            <div className="noi-progress-ring"><span>30</span><small>JOURS</small></div>
            <h3>Une tâche répétitive.<br />Automatisée avec l&apos;IA.</h3>
            <p>Ton espace suit l&apos;objectif, les accès, l&apos;usage et les résultats depuis les données réelles du compte.</p>
            <Link href="/dashboard/analytics">Voir les résultats <span>→</span></Link>
          </section>
        </div>

        <footer className="noi-footer"><span>Nanovia · Operating Intelligence</span><span>Backend FastAPI · Données serveur</span></footer>
      </main>
    </div>
  );
}

function Kpi({ label, value, note, tone }: { label: string; value: string; note: string; tone: string }) {
  return <article className={`noi-kpi ${tone}`}><p>{label}</p><strong>{value}</strong><span><i />{note}</span></article>;
}
