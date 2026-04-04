"use client";

import { useState, useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { resetPassword } from "@/lib/api";

const PASSWORD_RULES = [
  { label: "8 caractères minimum", test: (p: string) => p.length >= 8 },
  { label: "Une majuscule", test: (p: string) => /[A-Z]/.test(p) },
  { label: "Un chiffre", test: (p: string) => /\d/.test(p) },
];

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!token) setError("Lien invalide. Refaites une demande de réinitialisation.");
  }, [token]);

  const passwordScore = PASSWORD_RULES.filter((r) => r.test(password)).length;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (passwordScore < PASSWORD_RULES.length) {
      setError("Le mot de passe ne respecte pas les critères requis.");
      return;
    }
    if (password !== confirm) {
      setError("Les mots de passe ne correspondent pas.");
      return;
    }
    setLoading(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
      setTimeout(() => router.push("/login"), 3000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Lien invalide ou expiré. Refaites une demande.");
    } finally {
      setLoading(false);
    }
  };

  if (success) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center space-y-4">
        <div className="text-5xl">✅</div>
        <h2 className="text-white font-bold text-xl">Mot de passe mis à jour</h2>
        <p className="text-gray-400 text-sm">
          Votre mot de passe a été réinitialisé avec succès.
          Vous serez redirigé vers la connexion dans quelques secondes.
        </p>
        <Link href="/login" className="inline-block text-purple-400 hover:text-purple-300 text-sm transition">
          Se connecter maintenant →
        </Link>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-2xl p-8 space-y-5">
      {error && (
        <div role="alert" className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-4 py-3 text-sm flex items-start gap-2">
          <span className="flex-shrink-0">⚠️</span>
          <div>
            <span>{error}</span>
            {(error.includes("expiré") || error.includes("invalide")) && (
              <div className="mt-2">
                <Link href="/forgot-password" className="text-purple-400 hover:text-purple-300 underline text-xs">
                  Refaire une demande →
                </Link>
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        <label htmlFor="password" className="block text-sm text-gray-400 mb-2">Nouveau mot de passe</label>
        <div className="relative">
          <input
            id="password"
            type={showPassword ? "text" : "password"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={!token}
            autoComplete="new-password"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 pr-12 text-white focus:outline-none focus:border-purple-500 transition disabled:opacity-40"
            placeholder="Nouveau mot de passe"
          />
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 transition"
            aria-label={showPassword ? "Masquer" : "Afficher"}
          >
            {showPassword ? "🙈" : "👁"}
          </button>
        </div>
        {password.length > 0 && (
          <div className="mt-2 space-y-1">
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <div key={i} className={`h-1 flex-1 rounded-full transition-colors ${
                  i < passwordScore
                    ? passwordScore === 3 ? "bg-green-500" : passwordScore === 2 ? "bg-yellow-500" : "bg-red-500"
                    : "bg-gray-700"
                }`} />
              ))}
            </div>
            <ul className="space-y-0.5">
              {PASSWORD_RULES.map((r) => (
                <li key={r.label} className={`text-xs flex items-center gap-1.5 ${r.test(password) ? "text-green-400" : "text-gray-500"}`}>
                  <span>{r.test(password) ? "✓" : "○"}</span>{r.label}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div>
        <label htmlFor="confirm" className="block text-sm text-gray-400 mb-2">Confirmer le mot de passe</label>
        <input
          id="confirm"
          type={showPassword ? "text" : "password"}
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          required
          disabled={!token}
          autoComplete="new-password"
          className={`w-full bg-gray-800 border rounded-lg px-4 py-3 text-white focus:outline-none transition disabled:opacity-40 ${
            confirm.length > 0
              ? confirm === password ? "border-green-600" : "border-red-700"
              : "border-gray-700 focus:border-purple-500"
          }`}
          placeholder="Répéter le mot de passe"
        />
      </div>

      <button
        type="submit"
        disabled={loading || !token || passwordScore < 3 || password !== confirm}
        className="w-full bg-purple-600 hover:bg-purple-500 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition"
      >
        {loading ? (
          <span className="flex items-center justify-center gap-2">
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Mise à jour...
          </span>
        ) : "Réinitialiser mon mot de passe"}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-gray-950">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <div className="text-3xl font-bold text-purple-400 mb-1">⚡ KT OS</div>
          </Link>
          <p className="text-gray-400 text-sm">Nouveau mot de passe</p>
        </div>
        <Suspense fallback={<div className="text-center text-gray-500">Chargement...</div>}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}
