import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Nanovia OS — Automatisation IA pour entrepreneurs",
  description: "Systemes d'automatisation IA qui generent des revenus avec une plateforme SaaS unifiee.",
  openGraph: {
    title: "Nanovia OS — Automatisation IA",
    description: "Automatisation IA, billing serveur et modules monetisables dans une seule plateforme.",
    url: "https://nanovia.ca",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
