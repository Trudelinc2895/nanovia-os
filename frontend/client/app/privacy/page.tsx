import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-invert">
        <h1 className="text-4xl font-bold mb-2">Politique de confidentialité</h1>
        <p className="text-gray-400 mb-8">Dernière mise à jour : 21 juillet 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">1. Données collectées</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Informations de compte</strong> : nom, adresse email, mot de passe hashé.</li>
            <li><strong>Demande Pro Pilot</strong> : entreprise, activité, tâche répétitive, exemples, objectif et urgence.</li>
            <li><strong>Données de facturation</strong> : gérées par Stripe — nous ne stockons pas vos données de carte.</li>
            <li><strong>Données d&apos;utilisation</strong> : nombre de messages, modules utilisés, horodatages.</li>
            <li><strong>Données techniques</strong> : adresse IP (logs sécurité), navigateur.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">2. Utilisation des données</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Qualifier, livrer et soutenir Nanovia Pro Pilot.</li>
            <li>Traiter les paiements via Stripe.</li>
            <li>Envoyer des notifications de compte (emails transactionnels uniquement).</li>
            <li>Sécuriser le service (détection de fraude, rate limiting).</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">3. Fournisseurs et communication</h2>
          <p className="text-gray-300 mb-3">Nous ne vendons jamais vos données. Partage limité à :</p>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Stripe</strong> : traitement des paiements.</li>
            <li><strong>Resend</strong> : transmission des demandes et emails transactionnels.</li>
            <li><strong>OpenAI ou un fournisseur IA configuré</strong> : traitement du contenu soumis à l&apos;assistant lorsque cela est nécessaire au service.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">4. Vos droits</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Accès</strong> : demander les renseignements personnels détenus à votre sujet.</li>
            <li><strong>Rectification</strong> : faire corriger des renseignements inexacts ou incomplets.</li>
            <li><strong>Retrait du consentement</strong> : retirer un consentement lorsque la loi le permet.</li>
            <li><strong>Suppression</strong> : demander la suppression des renseignements qui ne doivent plus être conservés.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">5. Sécurité</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Mots de passe hashés avec Argon2id.</li>
            <li>Communications chiffrées en HTTPS/TLS.</li>
            <li>Accès limité selon le besoin opérationnel.</li>
            <li>Collecte limitée aux renseignements nécessaires à la demande ou au service.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">6. Cookies</h2>
          <p className="text-gray-300">Nous utilisons des cookies de session strictement nécessaires au fonctionnement du service. Aucun cookie publicitaire tiers n&apos;est annoncé dans la version actuelle.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">7. Contact DPO</h2>
          <p className="text-gray-300">
            Pour toute question ou demande relative à vos renseignements : <Link href="/contact" className="text-indigo-400 underline">formulaire de contact</Link>.
          </p>
        </section>

        <div className="mt-12 pt-8 border-t border-gray-800 flex gap-6">
          <Link href="/terms" className="text-indigo-400 underline">Conditions d&apos;utilisation</Link>
          <Link href="/" className="text-gray-400 underline">Retour à l&apos;accueil</Link>
        </div>
      </div>
    </div>
  );
}
