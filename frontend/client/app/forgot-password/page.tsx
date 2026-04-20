"use client";

import { useState } from "react";
import Link from "next/link";
import { AuthEntryWarning } from "@/components/auth-entry-warning";
import { forgotPassword } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch {
      // Always show success to prevent email enumeration
      setSent(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-gray-950">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <div className="text-3xl font-bold text-purple-400 mb-1">⚡ Nanovia OS</div>
          </Link>
          <p className="text-gray-400 text-sm">Réinitialisation de mot de passe</p>
        </div>

        <AuthEntryWarning />

        {sent ? (
          <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center space-y-4">
            <div className="text-5xl">📬</div>
            <h2 className="text-white font-bold text-xl">Email envoyé</h2>
            <p className="text-gray-400 text-sm leading-relaxed">
              Si un compte existe pour <strong className="text-white">{email}</strong>,
              vous recevrez un lien de réinitialisation dans les prochaines minutes.
            </p>
            <p className="text-gray-600 text-xs">
              Vérifiez aussi vos spams.
            </p>
            <Link
              href="/login"
              className="inline-block mt-4 text-purple-400 hover:text-purple-300 text-sm transition"
            >
              ← Retour à la connexion
            </Link>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
            <div>
              <p className="text-gray-400 text-sm mb-5 leading-relaxed">
                Entrez votre adresse email. Si un compte existe, vous recevrez un lien pour réinitialiser votre mot de passe.
              </p>
            </div>

            {error && (
              <div role="alert" className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm">
                {error}
              </div>
            )}

            <div>
              <label htmlFor="email" className="block text-sm text-gray-400 mb-2">Email</label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500 transition"
                placeholder="vous@example.com"
              />
            </div>

            <button
              type="submit"
              disabled={loading || !email}
              className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Envoi en cours...
                </span>
              ) : "Envoyer le lien de réinitialisation"}
            </button>

            <p className="text-center text-sm text-gray-500">
              <Link href="/login" className="text-purple-400 hover:text-purple-300 transition">
                ← Retour à la connexion
              </Link>
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
