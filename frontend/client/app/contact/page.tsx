"use client";
import { useState } from "react";
import Link from "next/link";

import { TurnstileWidget } from "@/components/turnstile-widget";
import { resolveApiUrl } from "@/lib/api";

const TURNSTILE_ENABLED = Boolean(process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY);

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", subject: "", message: "" });
  const [status, setStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (TURNSTILE_ENABLED && !turnstileToken) {
      setStatus("error");
      return;
    }
    setStatus("sending");
    // Send to backend email service (or just mailto fallback for now)
    try {
      const res = await fetch(resolveApiUrl("/api/v1/contact"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, turnstile_token: turnstileToken }),
      });
      if (res.ok) {
        setStatus("sent");
        setForm({ name: "", email: "", subject: "", message: "" });
      } else {
        setStatus("error");
      }
    } catch {
      // Fallback: open mailto if API not available
      window.location.href = `mailto:admin@nanovia.ca?subject=${encodeURIComponent(form.subject)}&body=${encodeURIComponent(`De: ${form.name} (${form.email})\n\n${form.message}`)}`;
      setStatus("idle");
    }
  }

  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col">
      {/* NAV */}
      <nav className="fixed top-0 w-full z-50 bg-gray-950/80 backdrop-blur border-b border-gray-800">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="text-xl font-bold text-violet-400">Nanovia OS</Link>
          <div className="flex items-center gap-3 text-sm">
            <Link href="/login" className="text-gray-400 hover:text-white transition px-3 py-2 rounded-lg">
              Connexion
            </Link>
            <Link
              href="/register"
              className="bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg transition font-medium"
            >
              Commencer gratis
            </Link>
          </div>
        </div>
      </nav>

      {/* CONTENT */}
      <div className="flex-1 pt-32 pb-24 px-6 max-w-2xl mx-auto w-full">
        <div className="text-center mb-12">
          <h1 className="text-4xl font-extrabold mb-3">Contacte-nous</h1>
          <p className="text-gray-400">Une question, un partenariat ou un bug ? On te répond sous 24h.</p>
        </div>

        {status === "sent" ? (
          <div className="bg-green-900/30 border border-green-700 text-green-300 rounded-xl p-8 text-center">
            <div className="text-4xl mb-4">✅</div>
            <h2 className="text-xl font-bold mb-2">Message envoyé !</h2>
            <p className="text-gray-400 mb-6">Nous te répondrons sous 24h à l&apos;adresse indiquée.</p>
            <Link href="/" className="text-violet-400 hover:text-violet-300 underline">
              ← Retour à l&apos;accueil
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
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
                <label className="block text-sm text-gray-400 mb-1.5">Adresse email</label>
                <input
                  type="email"
                  required
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="toi@exemple.com"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Sujet</label>
              <select
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition"
              >
                <option value="">Sélectionne un sujet…</option>
                <option value="support">Support technique</option>
                <option value="billing">Question sur la facturation</option>
                <option value="partnership">Partenariat / Collaboration</option>
                <option value="demo">Demande de démonstration</option>
                <option value="bug">Bug report</option>
                <option value="other">Autre</option>
              </select>
            </div>

            <div>
              <label className="block text-sm text-gray-400 mb-1.5">Message</label>
              <textarea
                required
                rows={6}
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="Décris ta situation ou ta question en détail…"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:border-violet-500 transition resize-none"
              />
            </div>

            {status === "error" && (
              <p className="text-red-400 text-sm text-center">
                Erreur lors de l&apos;envoi. Réessaie ou écris-nous directement à{" "}
                <a href="mailto:admin@nanovia.ca" className="underline">admin@nanovia.ca</a>.
              </p>
            )}

            <TurnstileWidget action="contact" onTokenChange={setTurnstileToken} />

            <button
              type="submit"
              disabled={status === "sending"}
              className="w-full bg-violet-600 hover:bg-violet-500 text-white font-bold py-3 rounded-xl transition disabled:opacity-50"
            >
              {status === "sending" ? "⏳ Envoi en cours…" : "Envoyer le message →"}
            </button>
          </form>
        )}

        {/* Direct contact info */}
        <div className="mt-8 text-center text-gray-500 text-sm">
          <p>Ou directement par email :</p>
          <a href="mailto:admin@nanovia.ca" className="text-violet-400 hover:text-violet-300">
            admin@nanovia.ca
          </a>
        </div>
      </div>

      {/* FOOTER */}
      <footer className="py-8 border-t border-gray-800 text-center text-gray-500 text-sm">
        <p>© 2026 Kevin Trudel — Nanovia OS · <a href="https://nanovia.ca" className="hover:text-white">nanovia.ca</a></p>
      </footer>
    </main>
  );
}
