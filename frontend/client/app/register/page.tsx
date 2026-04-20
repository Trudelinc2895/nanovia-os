"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthApiDiagnostic } from "@/components/auth-api-diagnostic";
import { AuthEntryWarning } from "@/components/auth-entry-warning";
import { useAuth } from "@/lib/auth-context";
import { Button, Card, Input } from "@/components/ui";

const PASSWORD_RULES = [
  { label: "8 caractères minimum", test: (p: string) => p.length >= 8 },
  { label: "Une majuscule", test: (p: string) => /[A-Z]/.test(p) },
  { label: "Un chiffre", test: (p: string) => /\d/.test(p) },
];

export default function RegisterPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const router = useRouter();

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
    if (!agreed) {
      setError("Vous devez accepter les conditions d'utilisation.");
      return;
    }
    setLoading(true);
    try {
      await register(email, password, name || undefined);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erreur lors de la création du compte.");
    } finally {
      setLoading(false);
    }
  };

  const confirmError = confirm.length > 0 && confirm !== password
    ? "Les mots de passe ne correspondent pas"
    : null;

  const strengthColor = passwordScore === 3 ? "bg-success" : passwordScore === 2 ? "bg-warning" : "bg-danger";

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-bg-base py-12">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <Link href="/" className="inline-block">
            <div className="text-3xl font-bold text-primary mb-1">⚡ Nanovia OS</div>
          </Link>
          <p className="text-text-secondary text-sm">Creer votre compte Nanovia</p>
        </div>

        <AuthApiDiagnostic />
        <AuthEntryWarning />

        <Card variant="outlined" padding="lg">
          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div role="alert" className="bg-danger-muted border border-danger/30 text-danger-text rounded-lg px-4 py-3 text-sm flex items-start gap-2">
                <span className="mt-0.5 flex-shrink-0">⚠️</span>
                <span>{error}</span>
              </div>
            )}

            <Input
              id="name"
              label="Nom (optionnel)"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="name"
              placeholder="Kevin Trudel"
            />

            <Input
              id="email"
              label="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="vous@example.com"
            />

            <div>
              <Input
                id="password"
                label="Mot de passe"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="new-password"
                placeholder="Créer un mot de passe"
              />
              {password.length > 0 && (
                <div className="mt-2 space-y-1">
                  <div className="flex gap-1">
                    {[0, 1, 2].map((i) => (
                      <div
                        key={i}
                        className={"h-1 flex-1 rounded-full transition-colors " + (i < passwordScore ? strengthColor : "bg-ui-border")}
                      />
                    ))}
                  </div>
                  <ul className="space-y-0.5">
                    {PASSWORD_RULES.map((r) => (
                      <li
                        key={r.label}
                        className={"text-xs flex items-center gap-1.5 " + (r.test(password) ? "text-success-text" : "text-text-muted")}
                      >
                        <span>{r.test(password) ? "✓" : "○"}</span>{r.label}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            <Input
              id="confirm"
              label="Confirmer le mot de passe"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              placeholder="Répéter le mot de passe"
              error={confirmError}
            />

            <div className="flex items-start gap-3">
              <input
                id="agree"
                type="checkbox"
                checked={agreed}
                onChange={(e) => setAgreed(e.target.checked)}
                className="mt-1 accent-primary w-4 h-4 flex-shrink-0 cursor-pointer"
              />
              <label htmlFor="agree" className="text-xs text-text-muted cursor-pointer">
                J&apos;accepte les{" "}
                <Link href="/terms" className="text-primary hover:text-primary-strong">conditions d&apos;utilisation</Link>
                {" "}et la{" "}
                <Link href="/privacy" className="text-primary hover:text-primary-strong">politique de confidentialité</Link>
              </label>
            </div>

            <Button
              type="submit"
              variant="primary"
              fullWidth
              loading={loading}
              disabled={!agreed || passwordScore < 3 || password !== confirm}
            >
              Commencer gratuitement
            </Button>

            <p className="text-center text-sm text-text-muted">
              Déjà un compte ?{" "}
              <Link href="/login" className="text-primary hover:text-primary-strong font-medium">
                Se connecter
              </Link>
            </p>
          </form>
        </Card>

        <p className="text-center mt-6">
          <Link href="/" className="text-text-muted hover:text-text-secondary text-sm transition">
            ← Retour à l&apos;accueil
          </Link>
        </p>
      </div>
    </div>
  );
}
