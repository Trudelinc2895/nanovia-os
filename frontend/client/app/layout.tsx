import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Nanovia Pro Pilot — Automatisez une tâche répétitive en 30 jours",
  description: "Un assistant IA Nanovia configuré avec vous pour automatiser une tâche répétitive en 30 jours.",
  openGraph: {
    title: "Nanovia Pro Pilot",
    description: "Automatisez une tâche répétitive avec un assistant IA Nanovia, livré avec accompagnement en 30 jours.",
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
