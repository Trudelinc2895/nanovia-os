"use client";

import { useState } from "react";

const DEFAULT_MESSAGE =
  "Salut, je veux savoir vos prix, si vous êtes dispo cette semaine, pis comment ca marche pour reserver.";

const DEFAULT_RESPONSE =
  "Bonjour, merci pour votre message. Nous pouvons vous aider cette semaine selon les disponibilites. Pouvez-vous nous indiquer le service souhaite, votre secteur et le moment ideal pour vous ? Nous vous repondrons rapidement avec les prochaines etapes.";

function normalizeMessage(message: string): string {
  return message.replace(/\s+/g, " ").trim();
}

function extractContextSnippet(message: string): string {
  const normalizedMessage = normalizeMessage(message);
  const shortMessage = normalizedMessage.length > 120 ? `${normalizedMessage.slice(0, 117)}...` : normalizedMessage;

  return shortMessage.replace(/[.!?]+$/, "");
}

function generateExampleResponse(message: string): string {
  const trimmedMessage = normalizeMessage(message);

  if (!trimmedMessage) {
    return DEFAULT_RESPONSE;
  }

  const normalizedMessage = trimmedMessage.toLowerCase();
  const contextSnippet = extractContextSnippet(trimmedMessage);

  if (/probleme|probl[eè]me|plainte|remboursement|erreur|insatisfait|mecontent/.test(normalizedMessage)) {
    return `Bonjour, merci de nous avoir ecrit au sujet de "${contextSnippet}". Nous sommes desoles pour la situation et nous voulons vous aider a la regler rapidement. Pouvez-vous nous confirmer ce qui s'est passe, depuis quand le probleme est present et le resultat attendu? Des reception de ces details, nous reviendrons vers vous avec une solution claire et les prochaines etapes.`;
  }

  if (/prix|tarif|co[uû]t|combien/.test(normalizedMessage)) {
    return `Bonjour, merci pour votre message concernant "${contextSnippet}". Nous pouvons preparer une estimation claire, mais il nous faudrait d'abord le service souhaite, le volume approximatif et votre priorite. Avec ces informations, nous pourrons vous repondre avec une proposition adaptee et les options les plus pertinentes.`;
  }

  if (/r[eé]servation|r[eé]server/.test(normalizedMessage)) {
    return `Bonjour, merci pour votre demande concernant "${contextSnippet}". Nous pouvons vous accompagner pour planifier la reservation. Pour finaliser rapidement, pouvez-vous nous indiquer le service souhaite, la date visee et vos disponibilites? Nous vous confirmerons ensuite les prochaines etapes pour bloquer le bon moment.`;
  }

  if (/disponibilit[eé]|disponible|date|semaine|jour|jours|horaire|dispo|rendez-vous|rdv/.test(normalizedMessage)) {
    return `Bonjour, merci pour votre message. Nous avons bien note votre demande de disponibilite pour "${contextSnippet}". Pouvez-vous nous preciser la date souhaitee, votre secteur et le service a prevoir? Nous pourrons ensuite vous confirmer les plages possibles et la meilleure prochaine etape.`;
  }

  if (/document|r[eé]sum[eé]|notes|compte rendu|compte-rendu/.test(normalizedMessage)) {
    return `Bonjour, merci pour votre envoi. Nous avons bien recu votre demande au sujet de "${contextSnippet}". Nous pouvons vous aider a structurer ce document ou ce resume de facon claire et professionnelle. Si vous nous partagez le format souhaite et l'objectif final, nous pourrons vous preparer une version concise, utile et facile a exploiter.`;
  }

  if (/suivi|prospect|client|relance/.test(normalizedMessage)) {
    return `Bonjour, merci pour votre message. Nous avons bien pris en compte votre besoin lie a "${contextSnippet}". Nous pouvons vous aider a preparer un suivi professionnel et rassurant. Pour aller plus loin, pouvez-vous nous indiquer le contexte du prospect ou du client, ainsi que l'objectif du suivi souhaite?`;
  }

  return `Bonjour, merci pour votre message. Nous avons bien recu votre demande concernant "${contextSnippet}". Nous pouvons vous aider a reformuler cela de facon claire, professionnelle et utile pour votre client. Si vous nous confirmez votre objectif principal et le resultat attendu, nous vous guiderons vers la meilleure prochaine etape.`;
}

export default function DemoPilotSection() {
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [result, setResult] = useState("");
  const [hasGenerated, setHasGenerated] = useState(false);

  function handleGenerateClick() {
    setResult(generateExampleResponse(message));
    setHasGenerated(true);
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
      <article className="rounded-3xl border border-gray-800 bg-gray-900 p-6">
        <h3 className="text-xl font-bold text-white">Avant</h3>
        <p className="mt-4 rounded-2xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-gray-300">
          {DEFAULT_MESSAGE}
        </p>
      </article>

      <article className="rounded-3xl border border-gray-800 bg-gray-900 p-6">
        <h3 className="text-xl font-bold text-white">Apres</h3>
        <p className="mt-4 rounded-2xl border border-green-500/20 bg-green-500/5 p-4 text-sm text-gray-200">
          {DEFAULT_RESPONSE}
        </p>
      </article>

      <div className="rounded-3xl border border-violet-500/30 bg-violet-500/10 p-6 lg:col-span-2">
        <label htmlFor="demo-message" className="block text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">
          Collez un message client ici
        </label>
        <textarea
          id="demo-message"
          rows={4}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="mt-4 w-full rounded-2xl border border-gray-700 bg-gray-950 px-4 py-3 text-sm text-white focus:border-violet-500 focus:outline-none"
        />
        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <button
            type="button"
            onClick={handleGenerateClick}
            className="rounded-xl bg-violet-600 px-6 py-3 text-sm font-bold text-white transition hover:bg-violet-500"
          >
            Generer une reponse exemple
          </button>
          <p className="text-sm text-violet-100">Exemple genere localement — version pilot.</p>
        </div>
        <div className="mt-5 rounded-2xl border border-violet-500/20 bg-black/20 p-4" aria-live="polite">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-300">
            {hasGenerated ? "Resultat genere" : "Resultat"}
          </p>
          <p id="demo-result" className="mt-2 text-sm text-gray-100">
            {hasGenerated ? result : 'Cliquez sur "Generer une reponse exemple" pour afficher une reponse professionnelle.'}
          </p>
        </div>
      </div>
    </div>
  );
}
