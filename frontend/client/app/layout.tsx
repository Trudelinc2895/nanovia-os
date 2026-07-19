import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Nanovia Pro Pilot — Automatisez une tâche répétitive",
  description: "Un assistant IA Nanovia configuré pour automatiser une tâche répétitive de votre entreprise en 30 jours.",
  openGraph: {
    title: "Nanovia Pro Pilot",
    description: "Automatisez une tâche répétitive avec un assistant IA configuré pour votre entreprise.",
    url: "https://nanovia.ca",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="bg-bg-base text-text-primary antialiased">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}
