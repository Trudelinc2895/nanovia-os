"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { isPrivateOrchestratorUiEnabled } from "@/lib/feature-flags";
import { Badge } from "@/components/ui";

const NAV_ITEMS = [
  { label: "Users", href: "/admin/users", icon: "👥" },
  { label: "Webhooks", href: "/admin/webhooks", icon: "🔗" },
  { label: "Metrics", href: "/admin/metrics", icon: "📊" },
  ...(isPrivateOrchestratorUiEnabled()
    ? [{ label: "Orchestrator", href: "/admin/orchestrator", icon: "🔒" }]
    : []),
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading) {
      if (!user) {
        router.push("/login");
      } else if (!user.is_admin) {
        router.push("/dashboard");
      }
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-bg-base">
        <div className="text-primary animate-pulse text-xl">Loading...</div>
      </div>
    );
  }

  if (!user.is_admin) return null;

  return (
    <div className="min-h-screen bg-bg-base flex">
      {/* Sidebar */}
      <aside className="w-56 bg-ui-surface border-r border-ui-border flex flex-col shrink-0">
        <div className="p-5 border-b border-ui-border">
          <span className="text-primary font-bold text-lg">⚡ Nanovia Admin</span>
        </div>
        <nav className="flex-1 p-4 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition " +
                  (active
                    ? "bg-primary-muted text-primary border border-primary/30"
                    : "text-text-secondary hover:text-text-primary hover:bg-ui-elevated")
                }
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-ui-border">
          <Link
            href="/dashboard"
            className="text-sm text-text-muted hover:text-text-secondary transition"
          >
            ← Back to Dashboard
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-screen overflow-auto">
        <header className="border-b border-ui-border bg-ui-surface/50 px-8 py-4 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-muted">
              Logged in as <span className="text-primary font-medium">{user.email}</span>
            </span>
            <Badge variant="info">ADMIN</Badge>
          </div>
        </header>
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
