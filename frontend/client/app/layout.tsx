import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "KT Monetization OS — Automatisation IA pour entrepreneurs",
  description: "Systèmes d automatisation IA qui génèrent des revenus pendant que tu dors. Ghost Agency, AI Operator, SaaS — tout en un.",
  openGraph: { title: "KT Monetization OS", description: "Automatisation IA = revenus passifs", url: "https://tkverse.ca" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
