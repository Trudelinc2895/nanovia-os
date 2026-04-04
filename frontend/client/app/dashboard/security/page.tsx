"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import {
  setup2FA,
  enable2FA,
  disable2FA,
  type TwoFASetupResponse,
} from "@/lib/api";

type Step = "idle" | "setup" | "verify" | "disable";

export default function SecurityPage() {
  const { user } = useAuth();
  const [step, setStep] = useState<Step>("idle");
  const [setupData, setSetupData] = useState<TwoFASetupResponse | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showSecret, setShowSecret] = useState(false);

  if (!user) return null;

  const isEnabled = user.totp_enabled ?? false;

  const handleSetup = async () => {
    setError("");
    setLoading(true);
    try {
      const data = await setup2FA();
      setSetupData(data);
      setStep("setup");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur lors de la configuration.");
    } finally {
      setLoading(false);
    }
  };

  const handleEnable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await enable2FA(totpCode);
      setSuccess("✅ 2FA activé avec succès ! Ton compte est maintenant protégé.");
      setStep("idle");
      setTotpCode("");
      // Refresh user in context
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Code invalide.");
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await disable2FA(disableCode || undefined, disablePassword || undefined);
      setSuccess("2FA désactivé.");
      setStep("idle");
      setDisableCode("");
      setDisablePassword("");
      window.location.reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Code ou mot de passe incorrect.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link href="/dashboard" className="text-gray-500 hover:text-white transition">←</Link>
          <span className="font-bold">🔐 Sécurité du compte</span>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 space-y-8">
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl px-4 py-3 text-sm">
            ⚠️ {error}
          </div>
        )}
        {success && (
          <div className="bg-green-500/10 border border-green-500/30 text-green-400 rounded-xl px-4 py-3 text-sm">
            {success}
          </div>
        )}

        {/* 2FA Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold flex items-center gap-2">
                Double authentification (2FA)
                {isEnabled && <span className="text-xs font-normal bg-green-900/50 text-green-400 border border-green-700/40 px-2 py-0.5 rounded-full">Activé</span>}
                {!isEnabled && <span className="text-xs font-normal bg-gray-800 text-gray-500 border border-gray-700 px-2 py-0.5 rounded-full">Désactivé</span>}
              </h2>
              <p className="text-sm text-gray-400 mt-1">
                Protège ton compte avec un code TOTP généré par ton application d&apos;authentification (Google Authenticator, Authy, etc.)
              </p>
            </div>
          </div>

          {/* Idle state */}
          {step === "idle" && (
            <div>
              {!isEnabled ? (
                <button
                  onClick={handleSetup}
                  disabled={loading}
                  className="bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold px-5 py-2.5 rounded-xl text-sm transition"
                >
                  {loading ? "Chargement..." : "Activer le 2FA →"}
                </button>
              ) : (
                <button
                  onClick={() => setStep("disable")}
                  className="border border-red-700/50 hover:border-red-500 text-red-400 hover:text-red-300 font-semibold px-5 py-2.5 rounded-xl text-sm transition"
                >
                  Désactiver le 2FA
                </button>
              )}
            </div>
          )}

          {/* Setup step — display QR code */}
          {step === "setup" && setupData && (
            <div className="space-y-5">
              <div className="bg-gray-800/50 rounded-xl p-5">
                <p className="text-sm text-gray-300 mb-4">
                  <strong>1.</strong> Scanne ce QR code dans ton application d&apos;authentification :
                </p>
                {setupData.qr_code_base64 ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={`data:image/png;base64,${setupData.qr_code_base64}`}
                    alt="QR Code 2FA"
                    width={200}
                    height={200}
                    className="mx-auto rounded"
                  />
                ) : (
                  <div className="text-sm text-gray-500">QR code unavailable — scan the secret manually</div>
                )}
                <div className="mt-4 text-center">
                  <button
                    type="button"
                    onClick={() => setShowSecret(!showSecret)}
                    className="text-xs text-gray-500 hover:text-gray-300 transition"
                  >
                    {showSecret ? "Masquer" : "Afficher le code manuel"}
                  </button>
                  {showSecret && (
                    <div className="mt-2 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 font-mono text-sm text-purple-300 tracking-widest break-all">
                      {setupData.secret}
                    </div>
                  )}
                </div>
              </div>

              <form onSubmit={handleEnable} className="space-y-4">
                <div>
                  <label className="block text-sm text-gray-400 mb-2">
                    <strong>2.</strong> Entre le code à 6 chiffres affiché dans l&apos;app pour confirmer :
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                    autoFocus
                    className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white text-center text-2xl tracking-[0.5em] focus:outline-none focus:border-purple-500 transition"
                    placeholder="000000"
                  />
                </div>
                <div className="flex gap-3">
                  <button
                    type="submit"
                    disabled={loading || totpCode.length !== 6}
                    className="flex-1 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition"
                  >
                    {loading ? "Activation..." : "Confirmer et activer"}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setStep("idle"); setTotpCode(""); }}
                    className="px-4 border border-gray-700 hover:border-gray-600 text-gray-400 rounded-xl text-sm transition"
                  >
                    Annuler
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Disable step */}
          {step === "disable" && (
            <form onSubmit={handleDisable} className="space-y-4">
              <p className="text-sm text-gray-400">
                Entre ton code TOTP <em>ou</em> ton mot de passe pour désactiver le 2FA :
              </p>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Code TOTP (6 chiffres)</label>
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ""))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500 transition"
                  placeholder="000000"
                />
              </div>
              <div className="text-center text-xs text-gray-600">— ou —</div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">Mot de passe du compte</label>
                <input
                  type="password"
                  value={disablePassword}
                  onChange={(e) => setDisablePassword(e.target.value)}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-red-500 transition"
                  placeholder="••••••••"
                />
              </div>
              <div className="flex gap-3">
                <button
                  type="submit"
                  disabled={loading || (!disableCode && !disablePassword)}
                  className="flex-1 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white font-semibold py-2.5 rounded-xl text-sm transition"
                >
                  {loading ? "Désactivation..." : "Désactiver le 2FA"}
                </button>
                <button
                  type="button"
                  onClick={() => setStep("idle")}
                  className="px-4 border border-gray-700 text-gray-400 hover:border-gray-600 rounded-xl text-sm transition"
                >
                  Annuler
                </button>
              </div>
            </form>
          )}
        </div>

        {/* Account info */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <h2 className="text-lg font-bold mb-3">Informations du compte</h2>
          <div className="space-y-2 text-sm text-gray-400">
            <div className="flex justify-between">
              <span>Email</span>
              <span className="text-white">{user.email}</span>
            </div>
            <div className="flex justify-between">
              <span>Plan</span>
              <span className="text-purple-300 capitalize font-semibold">{user.plan}</span>
            </div>
            <div className="flex justify-between">
              <span>Compte vérifié</span>
              <span className={user.is_verified ? "text-green-400" : "text-yellow-400"}>
                {user.is_verified ? "✓ Vérifié" : "⏳ En attente"}
              </span>
            </div>
            <div className="flex justify-between">
              <span>2FA</span>
              <span className={isEnabled ? "text-green-400" : "text-gray-500"}>
                {isEnabled ? "✓ Activé" : "Désactivé"}
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
