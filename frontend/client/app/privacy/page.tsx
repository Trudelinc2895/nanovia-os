import Link from "next/link";

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-gray-950 text-white py-16 px-4">
      <div className="max-w-3xl mx-auto prose prose-invert">
        <h1 className="text-4xl font-bold mb-2">Politique de confidentialité</h1>
        <p className="text-gray-400 mb-8">Dernière mise à jour : Avril 2026</p>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">1. Données collectées</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Informations de compte</strong> : nom, adresse email, mot de passe hashé.</li>
            <li><strong>Données de facturation</strong> : gérées par Stripe — nous ne stockons pas vos données de carte.</li>
            <li><strong>Données d'utilisation</strong> : nombre de messages, modules utilisés, horodatages.</li>
            <li><strong>Données techniques</strong> : adresse IP (logs sécurité), navigateur.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">2. Utilisation des données</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Fournir et améliorer le service Nanovia OS.</li>
            <li>Traiter les paiements via Stripe.</li>
            <li>Envoyer des notifications de compte (emails transactionnels uniquement).</li>
            <li>Sécuriser le service (détection de fraude, rate limiting).</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibond mb-3">3. Partage des données</h2>
          <p className="text-gray-300 mb-3">Nous ne vendons jamais vos données. Partage limité à :</p>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Stripe</strong> : traitement des paiements.</li>
            <li><strong>Resend</strong> : envoi des emails transactionnels.</li>
            <li><strong>OpenAI</strong> : traitement des requêtes AI (sans données personnelles identifiables).</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">4. Vos droits (RGPD)</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li><strong>Accès</strong> : exportez toutes vos données depuis le dashboard → Paramètres.</li>
            <li><strong>Suppression</strong> : supprimez votre compte depuis le dashboard → Paramètres → Supprimer mon compte.</li>
            <li><strong>Rectification</strong> : modifiez vos informations depuis le profil.</li>
            <li><strong>Portabilité</strong> : export JSON disponible.</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">5. Sécurité</h2>
          <ul className="text-gray-300 list-disc pl-6 space-y-2">
            <li>Mots de passe hashés avec Argon2id.</li>
            <li>Communications chiffrées en HTTPS/TLS.</li>
            <li>2FA disponible (TOTP RFC 6238).</li>
            <li>Secrets TOTP chiffrés au repos (Fernet AES-128).</li>
          </ul>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">6. Cookies</h2>
          <p className="text-gray-300">Nous utilisons des cookies de session strictement nécessaires au fonctionnement du service. Aucun cookie publicitaire ou de tracking tiers.</p>
        </section>

        <section className="mb-8">
          <h2 className="text-2xl font-semibold mb-3">7. Contact DPO</h2>
          <p className="text-gray-300">
            Pour toute question : <Link href="/contact" className="text-indigo-400 underline">Formulaire de contact</Link>
          </p>
        </section>

        <div className="mt-12 pt-8 border-t border-gray-800 flex gap-6">
          <Link href="/terms" className="text-indigo-400 underline">Conditions d'utilisation</Link>
          <Link href="/" className="text-gray-400 underline">Retour à l'accueil</Link>
        </div>
      </div>
    </div>
  );
}
