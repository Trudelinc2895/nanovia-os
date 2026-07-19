import Link from "next/link";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-invert">
        <h1 className="text-4xl font-bold mb-2">Conditions d&apos;utilisation</h1>
        <p className="text-gray-400 mb-8">Dernière mise à jour : Juillet 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">1. Acceptation des conditions</h2>
          <p className="text-gray-300">En accédant à Nanovia OS, vous acceptez ces conditions. Si vous n&apos;êtes pas d&apos;accord, n&apos;utilisez pas le service.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">2. Description du service</h2>
          <p className="text-gray-300">Nanovia Pro Pilot est un service assisté visant à analyser et automatiser une tâche répétitive convenue avec le client, avec une livraison ciblée en 30 jours. Le résultat et le périmètre exacts dépendent du cas d&apos;usage accepté.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">3. Compte utilisateur</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Vous êtes responsable de la confidentialité de votre mot de passe.</li>
            <li>Un seul compte par personne physique ou morale.</li>
            <li>Vous devez avoir au moins 18 ans pour utiliser le service.</li>
            <li>Toute activité frauduleuse entraîne la suspension immédiate du compte.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">4. Facturation et remboursements</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Le Pro Pilot est facturé 297 $ CAD pour la période initiale de 30 jours.</li>
            <li>Le suivi optionnel à 79 $ CAD par mois est distinct et n&apos;est pas activé automatiquement.</li>
            <li>Les paiements sont traités de manière sécurisée par Stripe.</li>
            <li>Toute demande d&apos;annulation ou de remboursement est évaluée selon le travail déjà réalisé, le périmètre convenu et les lois applicables.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">5. Propriété intellectuelle</h2>
          <p className="text-gray-300">Le contenu généré par les modules IA vous appartient. Le code, les algorithmes et l&apos;interface Nanovia OS restent la propriété exclusive de Nanovia.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">6. Limitation de responsabilité</h2>
          <p className="text-gray-300">Nanovia OS est fourni &quot;tel quel&quot;. Nous ne garantissons pas des résultats spécifiques. La responsabilité totale ne peut excéder les frais payés dans les 3 derniers mois.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">7. Contact</h2>
          <p className="text-gray-300">
            Questions : <Link href="/contact" className="text-indigo-400 underline">Formulaire de contact</Link>
          </p>
        </section>

        <div className="mt-12 pt-8 border-t border-gray-800 flex gap-6">
          <Link href="/privacy" className="text-indigo-400 underline">Politique de confidentialité</Link>
          <Link href="/" className="text-gray-400 underline">Retour à l&apos;accueil</Link>
        </div>
      </div>
    </div>
  );
}
