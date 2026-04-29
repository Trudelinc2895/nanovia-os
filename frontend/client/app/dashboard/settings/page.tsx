"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";

export default function SettingsPage() {
  const { user } = useAuth();

  // Profile form
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileMsg, setProfileMsg] = useState("");
  const [profileError, setProfileError] = useState("");

  // Password form
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [pwMsg, setPwMsg] = useState("");
  const [pwError, setPwError] = useState("");

  const handleProfileSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileLoading(true);
    setProfileMsg("");
    setProfileError("");
    try {
      await apiFetch<{ full_name: string; email: string }>(
        "/api/v1/users/me",
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ full_name: fullName }),
        }
      );
      setProfileMsg("Nom mis à jour avec succès.");
    } catch (err) {
      setProfileError(err instanceof Error ? err.message : "Erreur lors de la mise à jour.");
    } finally {
      setProfileLoading(false);
    }
  };

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwMsg("");
    setPwError("");
    if (newPassword !== confirmPassword) {
      setPwError("Les mots de passe ne correspondent pas.");
      return;
    }
    if (newPassword.length < 8) {
      setPwError("Le nouveau mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    setPwLoading(true);
    try {
      await apiFetch("/api/v1/users/me/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setPwMsg("Mot de passe modifié avec succès.");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPwError(err instanceof Error ? err.message : "Erreur lors du changement de mot de passe.");
    } finally {
      setPwLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 bg-gray-900/50 backdrop-blur sticky top-0 z-10">
        <div className="max-w-2xl mx-auto px-6 py-4 flex items-center gap-3">
          <Link href="/dashboard" className="text-gray-500 hover:text-white transition">
            ←
          </Link>
          <span className="font-bold">⚙️ Paramètres</span>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-6 py-10 space-y-8">
        {/* Profile section */}
        <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <h2 className="font-bold text-white text-lg mb-4">Profil</h2>
          <form onSubmit={handleProfileSave} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Email</label>
              <input
                type="email"
                value={user?.email ?? ""}
                disabled
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-gray-400 text-sm cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Nom complet</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Votre nom"
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-violet-600 outline-none transition"
              />
            </div>
            {profileMsg && (
              <p className="text-green-400 text-sm">{profileMsg}</p>
            )}
            {profileError && (
              <p className="text-red-400 text-sm">{profileError}</p>
            )}
            <button
              type="submit"
              disabled={profileLoading}
              className="bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white font-semibold py-2.5 px-6 rounded-xl text-sm transition"
            >
              {profileLoading ? "Enregistrement..." : "Enregistrer"}
            </button>
          </form>
        </section>

        {/* Change password section */}
        <section className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
          <h2 className="font-bold text-white text-lg mb-4">Changer de mot de passe</h2>
          <form onSubmit={handlePasswordChange} className="space-y-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">Mot de passe actuel</label>
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-violet-600 outline-none transition"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Nouveau mot de passe</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                minLength={8}
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-violet-600 outline-none transition"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Confirmer le nouveau mot de passe</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2.5 text-white text-sm focus:border-violet-600 outline-none transition"
              />
            </div>
            {pwMsg && (
              <p className="text-green-400 text-sm">{pwMsg}</p>
            )}
            {pwError && (
              <p className="text-red-400 text-sm">{pwError}</p>
            )}
            <button
              type="submit"
              disabled={pwLoading}
              className="bg-violet-700 hover:bg-violet-600 disabled:opacity-50 text-white font-semibold py-2.5 px-6 rounded-xl text-sm transition"
            >
              {pwLoading ? "Modification..." : "Changer le mot de passe"}
            </button>
          </form>
        </section>

        {/* Danger zone */}
        <section className="bg-gray-900 border border-red-900/40 rounded-2xl p-6">
          <h2 className="font-bold text-red-400 text-lg mb-2">Zone sensible</h2>
          <p className="text-sm text-gray-400 mb-4">
            Suppression de compte et export GDPR disponibles depuis la page Sécurité.
          </p>
          <Link
            href="/dashboard/security"
            className="inline-flex items-center gap-2 text-sm text-red-400 hover:text-red-300 border border-red-900/50 hover:border-red-700/50 px-4 py-2 rounded-xl transition"
          >
            🔒 Accéder à la page Sécurité →
          </Link>
        </section>
      </main>
    </div>
  );
}
