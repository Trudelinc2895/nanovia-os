import Link from "next/link";

export default function TermsPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-invert">
        <h1 className="text-4xl font-bold mb-2">Conditions d'utilisation</h1>
        <p className="text-gray-400 mb-8">Dernière mise à jour : Avril 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">1. Acceptation des conditions</h2>
          <p className="text-gray-300">En accédant à TKVerse, vous acceptez ces conditions. Si vous n'êtes pas d'accord, n'utilisez pas le service.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">2. Description du service</h2>
          <p className="text-gray-300">TKVerse (KT Monetization OS) est une plateforme SaaS offrant des modules d'automatisation IA pour les créateurs et entrepreneurs. Les fonctionnalités disponibles dépendent du plan souscrit.</p>
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
            <li>Les abonnements sont facturés mensuellement ou annuellement selon votre choix.</li>
            <li>Aucun remboursement après 14 jours d'utilisation effective.</li>
            <li>La période d'essai gratuit (14 jours) ne nécessite pas de carte bancaire.</li>
            <li>Les prix peuvent évoluer avec préavis de 30 jours.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">5. Propriété intellectuelle</h2>
          <p className="text-gray-300">Le contenu généré par les modules IA vous appartient. Le code, les algorithmes et l'interface TKVerse restent la propriété exclusive de KT Monetization Inc.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">6. Limitation de responsabilité</h2>
          <p className="text-gray-300">TKVerse est fourni "tel quel". Nous ne garantissons pas des résultats spécifiques. La responsabilité totale ne peut excéder les frais payés dans les 3 derniers mois.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">7. Contact</h2>
          <p className="text-gray-300">
            Questions : <Link href="/contact" className="text-indigo-400 underline">Formulaire de contact</Link>
          </p>
        </section>

        <div className="mt-12 pt-8 border-t border-gray-800 flex gap-6">
          <Link href="/privacy" className="text-indigo-400 underline">Politique de confidentialité</Link>
          <Link href="/" className="text-gray-400 underline">Retour à l'accueil</Link>
        </div>
      </div>
    </div>
  );
}
