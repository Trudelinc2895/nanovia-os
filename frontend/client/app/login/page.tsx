"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AuthApiDiagnostic } from "@/components/auth-api-diagnostic";
import { AuthEntryWarning } from "@/components/auth-entry-warning";
import { useAuth } from "@/lib/auth-context";
import { verify2FALogin } from "@/lib/api";
import { Button, Card, Input } from "@/components/ui";
import { trackAmplitudeEvent } from "@/components/amplitude-provider";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // 2FA step state
  const [requires2FA, setRequires2FA] = useState(false);
  const [partialToken, setPartialToken] = useState("");
  const [totpCode, setTotpCode] = useState("");

  const { login } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    trackAmplitudeEvent("Login Submitted");
    setError("");
    if (!email || !password) {
      setError("Veuillez remplir tous les champs.");
      return;
    }
    setLoading(true);
    try {
      const result = await login(email, password);
      // login() in auth-context calls apiLogin and then getMe()
      // But we need to handle 2FA — override with raw API call here
      if ((result as any)?.requires_2fa) {
        trackAmplitudeEvent("Login 2FA Required");
        setPartialToken((result as any).partial_token ?? "");
        setRequires2FA(true);
        return;
      }
      trackAmplitudeEvent("Login Succeeded", { two_factor: false });
      router.push("/dashboard");
    } catch (err: unknown) {
      trackAmplitudeEvent("Login Failed");
      setError(err instanceof Error ? err.message : "Email ou mot de passe incorrect.");
    } finally {
      setLoading(false);
    }
  };

  const handle2FA = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    if (totpCode.length !== 6) {
      setError("Le code doit contenir 6 chiffres.");
      return;
    }
    setLoading(true);
    try {
      await verify2FALogin(partialToken, totpCode);
      trackAmplitudeEvent("Login Succeeded", { two_factor: true });
      router.push("/dashboard");
    } catch (err: unknown) {
      trackAmplitudeEvent("Login 2FA Failed");
      setError(err instanceof Error ? err.message : "Code incorrect.");
    } finally {
      setLoading(false);
    }
  };

  // 2FA verification step
  if (requires2FA) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4 bg-bg-base">
        <div className="w-full max-w-sm">
          <div className="text-center mb-8">
            <div className="text-4xl mb-2">🔐</div>
            <h1 className="text-xl font-bold text-white">Vérification 2FA</h1>
            <p className="text-gray-400 text-sm mt-1">Entre le code de ton application d&apos;authentification</p>
          </div>

          <form onSubmit={handle2FA}>
            <Card variant="outlined" padding="lg" className="space-y-5">
              {error && (
                <div role="alert" className="bg-danger-muted border border-danger/30 text-danger-text rounded-lg px-4 py-3 text-sm">
                  ⚠️ {error}
                </div>
              )}
              <div>
                <label htmlFor="totp" className="block text-sm font-medium text-text-secondary mb-2">
                  Code à 6 chiffres
                </label>
                <input
                  id="totp"
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                  autoFocus
                  className="w-full bg-ui-elevated border border-ui-border rounded-xl px-4 py-3 text-white text-center text-2xl tracking-[0.5em] focus:outline-none focus:ring-2 focus:ring-primary/40 focus:border-primary transition"
                  placeholder="000000"
                />
              </div>
              <Button
                type="submit"
                variant="primary"
                fullWidth
                loading={loading}
                disabled={totpCode.length !== 6}
              >
                Confirmer
              </Button>
              <button
                type="button"
                onClick={() => { setRequires2FA(false); setTotpCode(""); setError(""); }}
                className="w-full text-center text-sm text-text-muted hover:text-text-secondary transition"
              >
                ← Retour à la connexion
              </button>
            </Card>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 bg-bg-base">
        <div className="w-full max-w-sm">
          {/* Logo */}
          <div className="text-center mb-8">
            <Link href="/" className="inline-block">
              <div className="text-3xl font-bold text-primary mb-1">⚡ Nanovia OS</div>
            </Link>
            <p className="text-gray-400 text-sm">Connexion a votre espace Nanovia</p>
          </div>

          <AuthApiDiagnostic />
          <AuthEntryWarning />

          <form onSubmit={handleSubmit}>
          <Card variant="outlined" padding="lg" className="space-y-5">
            {error && (
              <div role="alert" className="bg-danger-muted border border-danger/30 text-danger-text rounded-lg px-4 py-3 text-sm flex items-start gap-2">
                <span className="mt-0.5">⚠️</span>
                <span>{error}</span>
              </div>
            )}

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
              <div className="flex items-center justify-between mb-1.5">
                <label htmlFor="password" className="text-sm font-medium text-text-secondary">
                  Mot de passe
                </label>
                <Link href="/forgot-password" className="text-xs text-primary hover:text-primary-strong transition">
                  Mot de passe oublié ?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>

            <Button type="submit" variant="primary" fullWidth loading={loading}>
              Se connecter
            </Button>

            <p className="text-center text-sm text-gray-500">
              Pas de compte ?{" "}
              <Link href="/register" className="text-primary hover:text-primary-strong font-medium">
                Créer un compte
              </Link>
            </p>
          </Card>
        </form>

        <p className="text-center mt-6">
          <Link href="/" className="text-gray-600 hover:text-gray-400 text-sm transition">
            ← Retour à l&apos;accueil
          </Link>
        </p>
      </div>
    </div>
  );
}
