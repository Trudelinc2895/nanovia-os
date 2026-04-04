"use client";

import { useEffect } from "react";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";

const NAV_ITEMS = [
  { label: "Users", href: "/admin/users", icon: "👥" },
  { label: "Webhooks", href: "/admin/webhooks", icon: "🔗" },
  { label: "Metrics", href: "/admin/metrics", icon: "📊" },
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
      <div className="min-h-screen flex items-center justify-center bg-gray-950">
        <div className="text-purple-400 animate-pulse text-xl">Loading...</div>
      </div>
    );
  }

  if (!user.is_admin) return null;

  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col shrink-0">
        <div className="p-5 border-b border-gray-800">
          <span className="text-purple-400 font-bold text-lg">⚡ KT Admin</span>
        </div>
        <nav className="flex-1 p-4 flex flex-col gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition ${
                  active
                    ? "bg-purple-600/20 text-purple-300 border border-purple-700/50"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="p-4 border-t border-gray-800">
          <Link
            href="/dashboard"
            className="text-sm text-gray-500 hover:text-gray-300 transition"
          >
            ← Back to Dashboard
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-screen overflow-auto">
        <header className="border-b border-gray-800 bg-gray-900/50 px-8 py-4 shrink-0">
          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">
              Logged in as <span className="text-gray-300">{user.email}</span>
            </span>
            <span className="text-xs bg-purple-600/20 text-purple-300 border border-purple-700/50 px-2 py-1 rounded-full">
              ADMIN
            </span>
          </div>
        </header>
        <main className="flex-1 p-8">{children}</main>
      </div>
    </div>
  );
}
