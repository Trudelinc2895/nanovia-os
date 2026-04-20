"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const CANONICAL_HOST = "nanovia.ca";
const IPV4_RE = /^(?:\d{1,3}\.){3}\d{1,3}$/;

export function AuthEntryWarning() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    setShow(IPV4_RE.test(window.location.hostname));
  }, []);

  if (!show) return null;

  return (
    <div className="mb-5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
      <div className="font-semibold">Connexion publique non supportee via l&apos;IP brute.</div>
      <div className="mt-1 text-amber-200/90">
        Utilise plutot{" "}
        <Link href={`https://${CANONICAL_HOST}/login`} className="font-medium underline">
          https://{CANONICAL_HOST}
        </Link>
        {" "}pour la connexion, les cookies securises et les appels API.
      </div>
    </div>
  );
}
