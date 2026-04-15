"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { resolveApiUrl } from "@/lib/api";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const token = searchParams.get("token");

  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Token manquant. Vérifie le lien dans ton email.");
      return;
    }

    const verify = async () => {
      try {
        const res = await fetch(
          resolveApiUrl("/api/v1/auth/verify-email?token=" + encodeURIComponent(token)),
          { method: "POST" }
        );
        if (res.ok || res.status === 204) {
          setStatus("success");
          setMessage("Ton email a été vérifié avec succès !");
          setTimeout(() => router.push("/dashboard"), 3000);
        } else {
          const data = await res.json().catch(() => ({}));
          setStatus("error");
          setMessage(data.detail ?? "Lien invalide ou expiré.");
        }
      } catch {
        setStatus("error");
        setMessage("Une erreur est survenue. Réessaie.");
      }
    };

    verify();
  }, [token, router]);

  return (
    <div className="max-w-md w-full text-center space-y-6">
      {status === "loading" && (
        <>
          <div className="text-4xl animate-pulse">🔐</div>
          <h1 className="text-2xl font-bold text-text-primary">Vérification en cours…</h1>
        </>
      )}
      {status === "success" && (
        <>
          <div className="text-4xl">✅</div>
          <h1 className="text-2xl font-bold text-success-text">Email vérifié !</h1>
          <p className="text-text-secondary">{message}</p>
          <p className="text-sm text-text-muted">Redirection vers le dashboard dans 3 secondes…</p>
          <Link href="/dashboard" className="text-primary underline">Aller au dashboard →</Link>
        </>
      )}
      {status === "error" && (
        <>
          <div className="text-4xl">❌</div>
          <h1 className="text-2xl font-bold text-danger-text">Vérification échouée</h1>
          <p className="text-text-secondary">{message}</p>
          <Link href="/dashboard" className="block text-primary underline">Retour au dashboard</Link>
        </>
      )}
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-base p-8">
      <Suspense
        fallback={
          <div className="text-center">
            <div className="text-4xl animate-pulse">🔐</div>
            <p className="text-text-secondary mt-2">Chargement…</p>
          </div>
        }
      >
        <VerifyEmailContent />
      </Suspense>
    </div>
  );
}
