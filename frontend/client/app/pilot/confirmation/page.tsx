import { Suspense } from "react";
import Link from "next/link";

import { ConfirmationStatus } from "./confirmation-status";

function ProcessingFallback() {
  return (
    <section
      aria-live="polite"
      className="rounded-2xl border border-slate-600/70 bg-slate-950/80 p-8 text-center shadow-[0_0_60px_rgba(37,99,235,0.16)] sm:p-12"
    >
      <div className="mx-auto mb-6 h-px w-28 bg-gradient-to-r from-transparent via-blue-400 to-transparent" />
      <p className="mb-3 font-mono text-xs uppercase tracking-[0.28em] text-blue-300">
        processing
      </p>
      <h1 className="text-3xl font-semibold text-slate-100 sm:text-4xl">
        Traitement en cours
      </h1>
      <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-slate-300 sm:text-base">
        La confirmation du paiement est en cours.
      </p>
    </section>
  );
}

export default function PilotConfirmationPage() {
  return (
    <main className="flex min-h-screen flex-col bg-[#02040a] text-slate-100">
      <nav className="border-b border-slate-800 bg-black/70 backdrop-blur">
        <div className="mx-auto flex h-16 w-full max-w-5xl items-center justify-between px-6">
          <Link href="/" className="font-semibold tracking-wide text-blue-300">
            Nanovia
          </Link>
          <Link
            href="/contact"
            className="text-sm text-slate-400 transition hover:text-slate-100"
          >
            Contact
          </Link>
        </div>
      </nav>

      <div className="mx-auto flex w-full max-w-3xl flex-1 items-center px-6 py-20">
        <div className="w-full">
          <Suspense fallback={<ProcessingFallback />}>
            <ConfirmationStatus />
          </Suspense>
          <p className="mt-8 text-center text-xs leading-6 text-slate-500">
            Aucun accès n’est accordé depuis cette page. La confirmation provient
            uniquement du paiement enregistré par Nanovia.
          </p>
        </div>
      </div>

      <footer className="border-t border-slate-800 py-6 text-center text-xs text-slate-500">
        <Link href="/terms" className="transition hover:text-slate-300">
          Conditions
        </Link>
        <span className="px-3 text-slate-700">•</span>
        <Link href="/privacy" className="transition hover:text-slate-300">
          Confidentialité
        </Link>
      </footer>
    </main>
  );
}
