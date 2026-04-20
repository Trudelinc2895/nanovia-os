"use client";

import { useEffect, useState } from "react";
import { getPublicEntrypointHealth, type PublicEntrypointHealth } from "@/lib/api";

export function AuthApiDiagnostic() {
  const [diag, setDiag] = useState<PublicEntrypointHealth | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getPublicEntrypointHealth()
      .then(setDiag)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Impossible de verifier l'entree publique.");
      });
  }, []);

  if (error) {
    return (
      <div className="mb-5 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-100">
        <div className="font-semibold">API publique injoignable</div>
        <div className="mt-1 text-red-200/90">{error}</div>
      </div>
    );
  }

  if (!diag || diag.env !== "production") return null;

  if (typeof window !== "undefined") {
    const currentOrigin = window.location.origin;
    if (!diag.expected_public_hosts.includes(currentOrigin)) {
      return (
        <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <div className="font-semibold">Hostname public inattendu</div>
          <div className="mt-1 text-amber-200/90">
            Cette page est ouverte sur <strong>{currentOrigin}</strong>, mais l&apos;entree attendue est{" "}
            <strong>{diag.canonical_web_url}</strong>.
          </div>
        </div>
      );
    }
  }

  return null;
}
