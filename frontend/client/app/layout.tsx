import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "KT Monetization OS — Automatisation IA pour entrepreneurs",
  description: "Systèmes d'automatisation IA qui génèrent des revenus pendant que tu dors. Ghost Agency, AI Operator, SaaS — tout en un.",
  openGraph: { title: "KT Monetization OS — Automatisation IA", description: "Automatisation IA qui génère des revenus passifs. Ghost Agency, AI Operator, SaaS.", url: "https://tkverse.ca" },
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
