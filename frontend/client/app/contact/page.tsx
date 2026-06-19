"use client";
import { useState } from "react";
import Link from "next/link";

type OnboardingForm = {
  name: string;
  company: string;
  companyUrl: string;
  email: string;
  businessType: string;
  repetitiveTask: string;
  examples: string;
  goal: string;
  urgency: string;
  consent: boolean;
};

const initialForm: OnboardingForm = {
  name: "",
  company: "",
  companyUrl: "",
  email: "",
  businessType: "",
  repetitiveTask: "",
  examples: "",
  goal: "",
  urgency: "",
  consent: false,
};

function buildPilotMessage(form: OnboardingForm): string {
  return [
    "Demande Nanovia Pro Pilot — 297 CAD / 30 jours",
    "",
    `Nom complet: ${form.name}`,
    `Entreprise: ${form.company}`,
    `Adresse email: ${form.email}`,
    `Type d'activite: ${form.businessType}`,
    `Tache repetitive a automatiser: ${form.repetitiveTask}`,
    `Exemples de messages ou documents: ${form.examples}`,
    `Objectif souhaite: ${form.goal}`,
    `Niveau d'urgence: ${form.urgency}`,
    `Consentement a etre contacte: ${form.consent ? "Oui" : "Non"}`,
  ].join("\n");
}

export default function ContactPage() {
  const [form, setForm] = useState<OnboardingForm>(initialForm);
  const [status, setStatus] = useState<"idle" | "opening" | "ready">("idle");

  function openPilotMailto(currentForm: OnboardingForm) {
    window.location.href = `mailto:nanovia@duck.com?subject=${encodeURIComponent("Demande Nanovia Pro Pilot — 297 CAD / 30 jours")}&body=${encodeURIComponent(
      buildPilotMessage(currentForm)
    )}`;
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (form.companyUrl.trim()) {
      return;
    }

    if (!form.email.includes("@")) {
      return;
    }

    if (
      !form.name.trim() ||
      !form.company.trim() ||
      !form.businessType.trim() ||
      !form.repetitiveTask.trim() ||
      !form.examples.trim() ||
      !form.goal.trim() ||
      !form.urgency.trim() ||
      !form.consent
    ) {
      return;
    }

    setStatus("opening");
    openPilotMailto(form);
    setStatus("ready");
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col">
      <nav className="fixed top-0 w-full z-50 bg-gray-950/80 backdrop-blur border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-violet-400">Nanovia</Link>
          <div className="flex items-center gap-3 text-sm">
            <Link href="/login" className="text-gray-400 hover:text-white transition px-3 py-2 rounded-lg">
              Connexion
            </Link>
            <Link
              href="/contact"
              className="bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg transition font-medium"
            >
              Démarrer mon pilot Nanovia
            </Link>
          </div>
        </div>
      </nav>

      <div className="flex-1 pt-32 pb-24 px-6 max-w-3xl mx-auto w-full">
        <div className="text-center mb-12">
          <div className="inline-flex rounded-full border border-violet-500/30 bg-violet-500/10 px-4 py-1.5 text-sm text-violet-300 mb-5">
            Nanovia Pro Pilot — 297 CAD / 30 jours
          </div>
          <h1 className="text-4xl font-extrabold mb-3">Démarrer mon pilot Nanovia</h1>
          <p className="text-gray-300 max-w-2xl mx-auto">
            Remplis ce formulaire pour démarrer Nanovia Pro Pilot — 297 CAD / 30 jours.
          </p>
          <div className="mt-5 space-y-1 text-sm text-gray-400">
            <p>Après le pilot : 79 CAD / mois</p>
            <p>Une tâche répétitive automatisée avec IA en 30 jours.</p>
          </div>
        </div>

        {status === "ready" ? (
          <div className="bg-violet-900/20 border border-violet-500/30 text-violet-100 rounded-xl p-8 text-center">
            <div className="text-4xl mb-4">✉️</div>
            <h2 className="text-xl font-bold mb-2">Vérifie ton email prérempli</h2>
            <p className="text-gray-300 mb-3">
              Ton application courriel va s&apos;ouvrir avec ta demande préremplie. Vérifie puis clique Envoyer.
            </p>
            <p className="text-gray-400 mb-6">
              Si rien ne s&apos;ouvre, écris directement à <span className="font-semibold text-white">nanovia@duck.com</span>.
            </p>
            <Link href="/" className="text-violet-400 hover:text-violet-300 underline">
              ← Retour à l&apos;accueil
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
            <input
              type="text"
              name="company_url"
              tabIndex={-1}
              autoComplete="off"
              value={form.companyUrl}
              onChange={(e) => setForm({ ...form, companyUrl: e.target.value })}
              className="hidden"
              aria-hidden="true"
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Nom complet</label>
                <input
                  type="text"
                  required
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  placeholder="Kevin Trudel"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Entreprise</label>
                <input
                  type="text"
                  required
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value })}
                  placeholder="Nom de votre entreprise"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Adresse email</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="vous@entreprise.com"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-400 mb-1.5">Type d&apos;activité</label>
                <input
                  type="text"
                  required
                  value={form.businessType}
                  onChange={(e) => setForm({ ...form, businessType: e.target.value })}
                  placeholder="PME locale, service residentiel, consultant..."
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Tâche répétitive à automatiser</label>
              <textarea
                required
                rows={3}
                value={form.repetitiveTask}
                onChange={(e) => setForm({ ...form, repetitiveTask: e.target.value })}
                placeholder="Ex.: repondre aux demandes clients, preparer des suivis, resumer des documents..."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition resize-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Exemples de messages ou documents</label>
              <textarea
                required
                rows={4}
                value={form.examples}
                onChange={(e) => setForm({ ...form, examples: e.target.value })}
                placeholder="Colle un exemple de message client, document, note ou contenu a traiter."
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition resize-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Objectif souhaité</label>
              <textarea
                required
                rows={3}
                value={form.goal}
                onChange={(e) => setForm({ ...form, goal: e.target.value })}
                placeholder="Quel resultat veux-tu obtenir avec Nanovia Pro Pilot?"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition resize-none"
              />
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Niveau d&apos;urgence</label>
              <select
                required
                value={form.urgency}
                onChange={(e) => setForm({ ...form, urgency: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
              >
                <option value="">Sélectionne un niveau</option>
                <option value="faible">Faible</option>
                <option value="moyen">Moyen</option>
                <option value="eleve">Élevé</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>

            <div className="flex items-start gap-3">
              <input
                id="consent"
                type="checkbox"
                checked={form.consent}
                onChange={(e) => setForm({ ...form, consent: e.target.checked })}
                className="mt-1 accent-violet-500 w-4 h-4 flex-shrink-0 cursor-pointer"
              />
              <label htmlFor="consent" className="text-sm text-gray-300 cursor-pointer">
                Je consens à être contacté au sujet de ma demande Nanovia Pro Pilot.
              </label>
            </div>

            <button
              type="submit"
              disabled={status === "opening" || !form.consent}
              className="w-full bg-violet-600 hover:bg-violet-500 text-white font-bold py-3 rounded-xl transition disabled:opacity-50"
            >
              {status === "opening" ? "⏳ Ouverture de ton courriel…" : "Envoyer ma demande de pilot"}
            </button>
          </form>
        )}

        <div className="mt-8 text-center text-gray-500 text-sm">
          <p>Ou directement par email :</p>
          <a href="mailto:nanovia@duck.com" className="text-violet-400 hover:text-violet-300">
            nanovia@duck.com
          </a>
        </div>
      </div>

      <footer className="py-8 border-t border-gray-800 text-center text-gray-500 text-sm">
        <p>© 2026 Kevin Trudel — Nanovia · <a href="https://nanovia.ca" className="hover:text-white">nanovia.ca</a></p>
      </footer>
    </main>
  );
}
