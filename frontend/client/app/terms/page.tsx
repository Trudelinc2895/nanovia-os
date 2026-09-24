import Link from "next/link";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-invert">
        <h1 className="text-4xl font-bold mb-2">Conditions d&apos;utilisation</h1>
        <p className="text-gray-400 mb-8">Dernière mise à jour : 21 juillet 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">1. Acceptation des conditions</h2>
          <p className="text-gray-300">En commandant Nanovia Pro Pilot, vous acceptez ces conditions. Si vous n&apos;êtes pas d&apos;accord, ne finalisez pas le paiement et communiquez avec Nanovia.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">2. Description du service</h2>
          <p className="text-gray-300">Nanovia Pro Pilot est un service assisté de 30 jours visant une seule tâche répétitive convenue avec le client. La livraison peut inclure une analyse, la configuration d&apos;un assistant IA, un processus documenté et des recommandations d&apos;automatisation. Il ne s&apos;agit pas d&apos;une automatisation complète de l&apos;entreprise.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">3. Collaboration du client</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Fournir des informations exactes et les exemples nécessaires au mandat.</li>
            <li>Anonymiser les exemples et ne transmettre aucun secret ou renseignement sensible non requis.</li>
            <li>Valider la tâche choisie et répondre dans des délais raisonnables.</li>
            <li>Vérifier humainement les résultats produits avec l&apos;IA avant leur utilisation.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">4. Prix et paiement</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Le prix initial du Pilot est de 297 $ CAD pour 30 jours.</li>
            <li>Le suivi à 79 $ CAD par mois est optionnel et exige un accord distinct.</li>
            <li>Les paiements sont traités par Stripe; Nanovia ne stocke pas les numéros de carte.</li>
            <li>Les taxes et le montant total applicables doivent être affichés avant la confirmation du paiement.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">5. Démarrage, livraison et annulation</h2>
          <p className="text-gray-300">Le délai de 30 jours commence après la confirmation du périmètre et la réception des informations nécessaires. Les modalités particulières de livraison, d&apos;annulation et de remboursement sont confirmées par écrit avec la commande. Les droits impératifs prévus par la loi demeurent applicables.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">6. IA, propriété et responsabilité</h2>
          <p className="text-gray-300">Les sorties d&apos;IA peuvent contenir des erreurs et doivent être vérifiées. Le client conserve ses données et ses contenus; Nanovia conserve ses outils, méthodes et composants préexistants. Aucun résultat financier ou commercial précis n&apos;est garanti.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">7. Confidentialité et contact</h2>
          <p className="text-gray-300">
            Le traitement des renseignements personnels est décrit dans la <Link href="/privacy" className="text-indigo-400 underline">politique de confidentialité</Link>. Questions : <Link href="/contact" className="text-indigo-400 underline">formulaire de contact</Link>.
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
