"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  getAdminPilotReport,
  getAdminPilotRequests,
  retryAdminPilotNotifications,
  updateAdminPilotFulfillment,
  type AdminPilotReport,
  type AdminPilotRequest,
  type PilotFulfillmentStatus,
} from "@/lib/api";


const FULFILLMENT_LABELS: Record<PilotFulfillmentStatus, string> = {
  new: "Nouvelle",
  qualified: "Qualifiée",
  in_progress: "En cours",
  waiting_client: "Attente client",
  delivered: "Livrée",
  closed: "Fermée",
  rejected: "Refusée",
};

const URGENCY_STYLES: Record<string, string> = {
  faible: "bg-slate-800 text-slate-300",
  moyen: "bg-blue-950 text-blue-300",
  eleve: "bg-amber-950 text-amber-300",
  urgent: "bg-red-950 text-red-300",
};

const URGENCY_ORDER: Record<string, number> = {
  urgent: 0,
  eleve: 1,
  moyen: 2,
  faible: 3,
};

function notificationFailed(request: AdminPilotRequest): boolean {
  return [
    request.notification_status,
    request.client_notification_status,
    request.payment_notification_status,
  ].includes("failed");
}

export default function AdminPilotPage() {
  const [requests, setRequests] = useState<AdminPilotRequest[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [report, setReport] = useState<AdminPilotReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [workingId, setWorkingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [requestResult, reportResult] = await Promise.all([
        getAdminPilotRequests(page),
        getAdminPilotReport(),
      ]);
      setRequests(requestResult.requests);
      setTotalPages(Math.max(1, Math.ceil(requestResult.total / requestResult.per_page)));
      setReport(reportResult);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    void load();
  }, [load]);

  const orderedRequests = useMemo(
    () =>
      [...requests].sort((left, right) => {
        return (
          (URGENCY_ORDER[left.urgency ?? "faible"] ?? 4) -
          (URGENCY_ORDER[right.urgency ?? "faible"] ?? 4)
        );
      }),
    [requests],
  );

  async function updateStatus(requestId: string, value: PilotFulfillmentStatus) {
    setWorkingId(requestId);
    setError(null);
    try {
      await updateAdminPilotFulfillment(requestId, value);
      await load();
    } catch (updateError) {
      setError(updateError instanceof Error ? updateError.message : "Mise à jour impossible.");
    } finally {
      setWorkingId(null);
    }
  }

  async function retryNotifications(requestId: string) {
    setWorkingId(requestId);
    setError(null);
    try {
      await retryAdminPilotNotifications(requestId);
      await load();
    } catch (retryError) {
      setError(retryError instanceof Error ? retryError.message : "Nouvelle tentative impossible.");
    } finally {
      setWorkingId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Centre Nanovia Pro Pilot</h1>
        <p className="mt-1 text-sm text-gray-500">
          Demandes, paiements, acheminement, alertes et état de livraison.
        </p>
      </div>

      {error && (
        <div role="alert" className="rounded-lg border border-red-700/50 bg-red-900/30 px-4 py-3 text-red-200">
          {error}
        </div>
      )}

      {report && (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["Demandes", report.total],
              ["7 derniers jours", report.last_7_days],
              ["À traiter", report.requires_action],
              ["Alertes notification", report.notification_failures],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
                <p className="text-sm text-gray-500">{label}</p>
                <p className="mt-2 text-3xl font-bold text-white">{value}</p>
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-violet-800/40 bg-violet-950/20 px-5 py-4 text-sm text-violet-100">
            <strong>Synthèse simple :</strong> {report.simple_summary}
          </div>
        </>
      )}

      {loading ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900 px-6 py-12 text-center text-gray-500 animate-pulse">
          Chargement des demandes…
        </div>
      ) : orderedRequests.length === 0 ? (
        <div className="rounded-xl border border-gray-800 bg-gray-900 px-6 py-12 text-center text-gray-500">
          Aucune demande Pilot enregistrée.
        </div>
      ) : (
        <div className="space-y-4">
          <nav aria-label="Pages des demandes Pilot" className="flex items-center justify-between text-sm text-gray-300">
            <button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)} className="rounded-lg border border-gray-700 px-3 py-2 disabled:opacity-50">Précédent</button>
            <span>Page {page} sur {totalPages}</span>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage((current) => current + 1)} className="rounded-lg border border-gray-700 px-3 py-2 disabled:opacity-50">Suivant</button>
          </nav>
          {orderedRequests.map((request) => (
            <article key={request.id} className="rounded-xl border border-gray-800 bg-gray-900 p-5">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold text-white">
                      {request.company || request.name}
                    </h2>
                    <span className={`rounded-full px-2.5 py-1 text-xs ${URGENCY_STYLES[request.urgency ?? "faible"]}`}>
                      {request.urgency || "non classée"}
                    </span>
                    <span className="rounded-full bg-gray-800 px-2.5 py-1 text-xs text-gray-300">
                      Paiement : {request.status}
                    </span>
                    {request.payments.length > 1 && (
                      <span className="rounded-full bg-amber-950 px-2.5 py-1 text-xs text-amber-200">
                        {request.payments.length} tentatives — rapprochement requis
                      </span>
                    )}
                    {notificationFailed(request) && (
                      <span className="rounded-full bg-red-950 px-2.5 py-1 text-xs text-red-300">
                        Notification à reprendre
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-gray-300">{request.repetitive_task}</p>
                  <p className="text-xs text-gray-500">
                    {request.name} · {request.email} · {new Date(request.created_at).toLocaleString("fr-CA")}
                  </p>
                  <p className="font-mono text-xs text-gray-600">{request.id}</p>
                </div>

                <div className="flex flex-col gap-2 sm:flex-row xl:flex-col">
                  <label className="sr-only" htmlFor={`status-${request.id}`}>État de livraison</label>
                  <select
                    id={`status-${request.id}`}
                    value={request.fulfillment_status}
                    disabled={workingId === request.id}
                    onChange={(event) => void updateStatus(request.id, event.target.value as PilotFulfillmentStatus)}
                    className="rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white disabled:opacity-50"
                  >
                    {Object.entries(FULFILLMENT_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>{label}</option>
                    ))}
                  </select>
                  {notificationFailed(request) && (
                    <button
                      type="button"
                      disabled={workingId === request.id}
                      onClick={() => void retryNotifications(request.id)}
                      className="rounded-lg border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200 disabled:opacity-50"
                    >
                      Relancer les notifications
                    </button>
                  )}
                </div>
              </div>

              <details className="mt-4 border-t border-gray-800 pt-4 text-sm">
                <summary className="cursor-pointer text-violet-300">Voir le dossier détaillé</summary>
                <dl className="mt-4 grid gap-4 md:grid-cols-2">
                  <div><dt className="text-gray-500">Type d’activité</dt><dd className="text-gray-200">{request.business_type || "—"}</dd></div>
                  <div><dt className="text-gray-500">Acheminé à</dt><dd className="text-gray-200">{request.routed_to || "—"}</dd></div>
                  <div><dt className="text-gray-500">Objectif</dt><dd className="whitespace-pre-wrap text-gray-200">{request.goal || "—"}</dd></div>
                  <div><dt className="text-gray-500">Exemples</dt><dd className="whitespace-pre-wrap text-gray-200">{request.examples || "—"}</dd></div>
                  <div><dt className="text-gray-500">Notification opérateur</dt><dd className="text-gray-200">{request.notification_status}</dd></div>
                  <div><dt className="text-gray-500">Accusé client</dt><dd className="text-gray-200">{request.client_notification_status}</dd></div>
                  <div className="md:col-span-2">
                    <dt className="text-gray-500">Paiements Stripe ({request.payments.length})</dt>
                    <dd className="mt-2 space-y-2">
                      {request.payments.map((payment) => (
                        <div key={payment.stripe_checkout_session_id} className="break-all rounded-lg border border-gray-700 bg-gray-800 p-3 text-gray-200">
                          <p>{payment.status} · Stripe : {payment.payment_status} · {payment.amount_subtotal === null ? "Montant inconnu" : `${(payment.amount_subtotal / 100).toFixed(2)} ${payment.currency.toUpperCase()}`}</p>
                          <p className="font-mono text-xs">Session : {payment.stripe_checkout_session_id}</p>
                          <p className="font-mono text-xs">Intention : {payment.stripe_payment_intent_id || "en attente"}</p>
                        </div>
                      ))}
                    </dd>
                  </div>
                </dl>
              </details>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
