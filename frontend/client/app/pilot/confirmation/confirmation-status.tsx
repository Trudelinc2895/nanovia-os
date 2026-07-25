"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import {
  getPilotConfirmation,
  type PilotConfirmationStatus,
} from "@/lib/api";

const SESSION_ID_PATTERN = /^cs_[A-Za-z0-9_]{3,252}$/;
const PUBLIC_STATES = new Set<PilotConfirmationStatus>([
  "confirmed",
  "processing",
  "manual_review",
]);

const STATE_CONTENT: Record<
  PilotConfirmationStatus,
  { label: string; title: string; description: string }
> = {
  confirmed: {
    label: "confirmed",
    title: "Paiement confirmé",
    description:
      "Votre paiement Nanovia Pro Pilot a été confirmé. La prise en charge peut commencer.",
  },
  processing: {
    label: "processing",
    title: "Traitement en cours",
    description:
      "La confirmation du paiement est en cours. Cette page se met à jour automatiquement.",
  },
  manual_review: {
    label: "manual_review",
    title: "Vérification manuelle",
    description:
      "La confirmation automatique n’est pas disponible. Nanovia vérifiera la situation avant toute activation.",
  },
};

function isValidSessionId(value: string | null): value is string {
  return value !== null && SESSION_ID_PATTERN.test(value);
}

export function ConfirmationStatus() {
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const validSessionId = isValidSessionId(sessionId) ? sessionId : null;
  const [publicStatus, setPublicStatus] = useState<PilotConfirmationStatus>(
    validSessionId ? "processing" : "manual_review"
  );

  useEffect(() => {
    if (!validSessionId) {
      setPublicStatus("manual_review");
      return;
    }
    const checkoutSessionId = validSessionId;

    let active = true;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    async function refreshStatus() {
      try {
        const response = await getPilotConfirmation(checkoutSessionId);
        const nextStatus = PUBLIC_STATES.has(response.status)
          ? response.status
          : "manual_review";
        if (!active) return;
        setPublicStatus(nextStatus);
        if (nextStatus === "processing") {
          retryTimer = setTimeout(refreshStatus, 3000);
        }
      } catch {
        if (active) {
          setPublicStatus("manual_review");
        }
      }
    }

    setPublicStatus("processing");
    void refreshStatus();
    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [validSessionId]);

  const content = STATE_CONTENT[publicStatus];
  return (
    <section
      aria-live="polite"
      className="rounded-2xl border border-slate-600/70 bg-slate-950/80 p-8 text-center shadow-[0_0_60px_rgba(37,99,235,0.16)] sm:p-12"
    >
      <div className="mx-auto mb-6 h-px w-28 bg-gradient-to-r from-transparent via-blue-400 to-transparent" />
      <p className="mb-3 font-mono text-xs uppercase tracking-[0.28em] text-blue-300">
        {content.label}
      </p>
      <h1 className="text-3xl font-semibold text-slate-100 sm:text-4xl">
        {content.title}
      </h1>
      <p className="mx-auto mt-4 max-w-xl text-sm leading-7 text-slate-300 sm:text-base">
        {content.description}
      </p>
    </section>
  );
}
