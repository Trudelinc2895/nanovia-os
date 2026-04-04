"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log error to monitoring (add Sentry here in prod)
    console.error("[error boundary]", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="text-6xl mb-4">⚠️</div>
        <h1 className="text-2xl font-bold mb-3">Une erreur s&apos;est produite</h1>
        <p className="text-gray-400 mb-2">
          Quelque chose s&apos;est mal passé. L&apos;équipe est déjà notifiée.
        </p>
        {error.digest && (
          <p className="text-xs text-gray-600 mb-6">ID: {error.digest}</p>
        )}
        <div className="flex gap-4 justify-center">
          <button
            onClick={reset}
            className="bg-violet-600 hover:bg-violet-500 text-white font-semibold px-6 py-3 rounded-lg transition"
          >
            Réessayer
          </button>
          <Link
            href="/"
            className="bg-gray-800 hover:bg-gray-700 text-white font-semibold px-6 py-3 rounded-lg border border-gray-700 transition"
          >
            Accueil
          </Link>
        </div>
      </div>
    </main>
  );
}
