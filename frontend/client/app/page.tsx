import Link from "next/link";

const STRIPE_PAYMENT_LINK = "https://buy.stripe.com/eVqaEZ2vF03j0De6bC1ZS02";
const PUBLIC_EMAIL = "nanovia@duck.com";
const PUBLIC_EMAIL_LINK = `mailto:${PUBLIC_EMAIL}`;

const deliverables = [
  "Analyse d'une tache repetitive de votre entreprise",
  "Configuration d'un assistant IA adapte a votre realite",
  "Processus clair, documente et reutilisable",
  "Recommandations d'automatisation concretes",
  "Livraison d'un plan exploitable en 30 jours",
];

const audiences = [
  "Solopreneurs",
  "Petites entreprises",
  "Travailleurs autonomes",
  "Equipes qui perdent du temps sur des taches repetitives",
  "Entreprises qui veulent tester l'IA sans lancer un gros projet complexe",
];

const seriousnessItems = [
  "Aucun acces inutile a vos outils ou donnees",
  "Donnees limitees au besoin reel",
  "Travail documente et reutilisable",
  "Objectif : livrer un resultat concret, pas vendre du reve",
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-gray-950 text-white">
      <nav className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/95 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="text-xl font-bold text-violet-400">
            Nanovia
          </Link>
          <div className="hidden items-center gap-6 text-sm text-gray-300 md:flex">
            <a href="#accueil" className="transition hover:text-white">
              Accueil
            </a>
            <a href="#offre" className="transition hover:text-white">
              Offre
            </a>
            <a href="#prix" className="transition hover:text-white">
              Prix
            </a>
            <a href="#contact" className="transition hover:text-white">
              Contact
            </a>
          </div>
          <a
            href={STRIPE_PAYMENT_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-500"
          >
            Démarrer Pro Pilot
          </a>
        </div>
      </nav>

      <section id="accueil" className="mx-auto max-w-5xl px-6 pb-20 pt-24 text-center">
        <div className="mb-6 inline-flex rounded-full border border-violet-500/30 bg-violet-500/10 px-4 py-1.5 text-sm text-violet-300">
          Nanovia Pro Pilot
        </div>
        <h1 className="mx-auto max-w-4xl text-4xl font-extrabold leading-tight md:text-6xl">
          Nanovia Pro Pilot
        </h1>
        <p className="mx-auto mt-6 max-w-3xl text-lg text-gray-200">
          Automatisez une tache repetitive de votre entreprise avec un assistant IA configure pour vous.
        </p>
        <p className="mx-auto mt-4 max-w-3xl text-base text-gray-400 md:text-lg">
          En 30 jours, Nanovia vous aide a transformer une tache repetitive en processus assiste par IA,
          clair, documente et reutilisable.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <a
            href={STRIPE_PAYMENT_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-xl bg-violet-600 px-8 py-4 text-lg font-bold text-white transition hover:bg-violet-500"
          >
            Démarrer Pro Pilot
          </a>
          <a
            href={PUBLIC_EMAIL_LINK}
            className="rounded-xl border border-gray-700 bg-gray-900 px-8 py-4 text-lg font-semibold text-white transition hover:border-violet-500"
          >
            Écrire à Nanovia
          </a>
        </div>
        <p className="mt-5 text-sm text-gray-500">Paiement securise par Stripe.</p>
      </section>

      <section id="offre" className="border-y border-gray-800 bg-gray-900/40 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Ce que le client obtient</p>
            <h2 className="mt-3 text-3xl font-bold md:text-4xl">Un accompagnement simple, utile et livrable</h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {deliverables.map((item) => (
              <div key={item} className="rounded-2xl border border-gray-800 bg-gray-950 p-5 text-sm text-gray-200">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Pour qui</p>
            <h2 className="mt-3 text-3xl font-bold md:text-4xl">Pour les equipes qui veulent tester l'IA sans complexite</h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {audiences.map((item) => (
              <div key={item} className="rounded-2xl border border-gray-800 bg-gray-900 p-5 text-sm text-gray-200">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="prix" className="border-y border-gray-800 bg-gray-900/40 px-6 py-20">
        <div className="mx-auto max-w-4xl text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Prix</p>
          <h2 className="mt-3 text-3xl font-bold md:text-4xl">Une offre claire pour lancer Pro Pilot</h2>
          <div className="mt-10 rounded-3xl border border-violet-500/30 bg-gray-950 p-10">
            <p className="text-sm uppercase tracking-[0.25em] text-gray-400">Pro Pilot 30 jours</p>
            <div className="mt-3 text-4xl font-extrabold text-white">297 $ CAD</div>
            <p className="mt-3 text-lg text-gray-300">Paiement securise par Stripe</p>
            <div className="mx-auto mt-8 h-px max-w-md bg-gray-800" />
            <p className="mt-8 text-sm uppercase tracking-[0.25em] text-gray-400">Suivi optionnel ensuite</p>
            <div className="mt-3 text-3xl font-bold text-violet-300">79 $ CAD / mois</div>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <a
                href={STRIPE_PAYMENT_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex rounded-xl bg-violet-600 px-8 py-4 text-lg font-bold text-white transition hover:bg-violet-500"
              >
                Démarrer Pro Pilot
              </a>
              <a
                href={PUBLIC_EMAIL_LINK}
                className="inline-flex rounded-xl border border-gray-700 px-8 py-4 text-lg font-semibold text-white transition hover:border-violet-500"
              >
                Écrire à Nanovia
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Securite / serieux</p>
            <h2 className="mt-3 text-3xl font-bold md:text-4xl">Un cadre simple, prudent et documente</h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {seriousnessItems.map((item) => (
              <div key={item} className="rounded-2xl border border-gray-800 bg-gray-900 p-5 text-sm text-gray-200">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="contact" className="border-t border-gray-800 px-6 py-20 text-center">
        <div className="mx-auto max-w-3xl">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Contact</p>
          <h2 className="mt-3 text-3xl font-bold md:text-4xl">Parler a Nanovia avant ou apres le paiement</h2>
          <p className="mx-auto mt-4 max-w-2xl text-gray-400">
            Si vous voulez valider votre cas d'usage ou poser une question avant de commencer, ecrivez a Nanovia.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <a
              href={PUBLIC_EMAIL_LINK}
              className="rounded-xl border border-violet-500 bg-violet-500/10 px-8 py-4 text-lg font-semibold text-violet-100 transition hover:bg-violet-500/20"
            >
              {PUBLIC_EMAIL}
            </a>
            <Link
              href="/contact"
              className="rounded-xl border border-gray-700 px-8 py-4 text-lg font-semibold text-white transition hover:border-violet-500"
            >
              Formulaire de contact
            </Link>
          </div>
        </div>
      </section>
    </main>
  );
}
