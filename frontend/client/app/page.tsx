import DemoPilotSection from "./demo-pilot-section";
import Link from "next/link";

const STRIPE_PAYMENT_LINK = "https://buy.stripe.com/eVqaEZ2vF03j0De6bC1ZS02";

const offerItems = [
  "Diagnostic rapide de l'entreprise",
  "Choix d'une seule tache repetitive a automatiser",
  "Configuration d'un assistant IA Nanovia",
  "1 workflow concret",
  "30 jours d'acces",
  "Support leger par courriel ou message",
];

const problems = [
  "Des messages clients reviennent sans cesse.",
  "Le contenu commercial prend trop de temps a preparer.",
  "Les suivis et relances se perdent dans le quotidien.",
];

const solutions = [
  "Un assistant IA configure pour ton entreprise.",
  "Un seul workflow clair, centre sur une vraie tache repetitive.",
  "Un resultat livrable en 30 jours, sans refaire toute ta structure.",
];

const useCases = [
  "Repondre plus vite aux messages clients",
  "Generer des publications commerciales",
  "Resumer des documents ou notes vocales",
  "Preparer des messages de suivi et de vente",
];

const concreteExamples = [
  {
    title: "Exemple 1 — Reponse client",
    before: "Salut, combien ca coute, vous etes dispo quand, pis comment je reserve?",
    after:
      "Bonjour, merci pour votre message. Pour vous donner une estimation claire, pouvez-vous nous preciser le service souhaite, votre secteur et le moment ideal pour vous? Nous vous repondrons rapidement avec les prochaines etapes.",
  },
  {
    title: "Exemple 2 — Notes desordonnees vers publication",
    before: "promo ete, nouveaux clients, service rapide, residentiel, rabais bienvenue, appeler ou ecrire",
    after:
      "Cet ete, simplifiez-vous la vie avec notre service residentiel rapide et fiable. Les nouveaux clients profitent d'un rabais de bienvenue. Contactez-nous des aujourd'hui pour reserver votre place.",
  },
  {
    title: "Exemple 3 — Suivi prospect",
    before: "client interesse la semaine passee, pas repondu encore, relancer poliment, offrir disponibilite",
    after:
      "Bonjour, je me permets de faire un suivi concernant votre demande. Nous avons encore quelques disponibilites cette semaine et je peux vous aider a choisir l'option la plus adaptee a votre besoin. Souhaitez-vous que je vous envoie les prochaines etapes?",
  },
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
            <a href="#demo" className="transition hover:text-white">
              Démo
            </a>
            <a href="#prix" className="transition hover:text-white">
              Prix
            </a>
          </div>
          <Link
            href="/contact"
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-violet-500"
          >
            Demarrer
          </Link>
        </div>
      </nav>

      <section id="accueil" className="mx-auto max-w-5xl px-6 pb-20 pt-24 text-center">
        <div className="mb-6 inline-flex rounded-full border border-violet-500/30 bg-violet-500/10 px-4 py-1.5 text-sm text-violet-300">
          Nanovia Pro Pilot — 297 CAD / 30 jours
        </div>
        <h1 className="mx-auto max-w-4xl text-4xl font-extrabold leading-tight md:text-6xl">
          Automatise une tache repetitive de ton entreprise avec Nanovia.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-gray-300">
          Je configure pour vous un assistant IA Nanovia qui automatise une tache repetitive
          en 30 jours : reponses clients, contenu, resumes, suivis ou messages commerciaux.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/contact"
            className="rounded-xl bg-violet-600 px-8 py-4 text-lg font-bold text-white transition hover:bg-violet-500"
          >
            Demarrer mon pilot Nanovia
          </Link>
          <a
            href={STRIPE_PAYMENT_LINK}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-xl border border-violet-500 bg-violet-500/10 px-8 py-4 text-lg font-bold text-violet-100 transition hover:bg-violet-500/20"
          >
            Payer 297 CAD et demarrer
          </a>
          <a
            href="#prix"
            className="rounded-xl border border-gray-700 bg-gray-900 px-8 py-4 text-lg font-semibold text-white transition hover:border-violet-500"
          >
            Voir le prix
          </a>
        </div>
        <p className="mt-5 text-sm text-gray-500">
          Une seule offre. Une seule promesse. Un seul objectif : livrer un resultat concret.
        </p>
      </section>

      <section className="border-y border-gray-800 bg-gray-900/40 px-6 py-20">
        <div className="mx-auto grid max-w-6xl gap-6 lg:grid-cols-2">
          <div className="rounded-3xl border border-gray-800 bg-gray-950 p-8">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Probleme</p>
            <h2 className="mt-3 text-3xl font-bold">Tu perds du temps sur des taches qui reviennent toujours.</h2>
            <div className="mt-6 space-y-3">
              {problems.map((item) => (
                <div key={item} className="rounded-2xl border border-gray-800 bg-gray-900 p-4 text-sm text-gray-200">
                  {item}
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-3xl border border-violet-500/30 bg-violet-500/10 p-8">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Solution</p>
            <h2 className="mt-3 text-3xl font-bold">Nanovia transforme une tache repetitive en workflow IA simple.</h2>
            <div className="mt-6 space-y-3">
              {solutions.map((item) => (
                <div key={item} className="rounded-2xl border border-violet-500/20 bg-black/20 p-4 text-sm text-violet-100">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="offre" className="px-6 py-20">
        <div className="mx-auto grid max-w-6xl gap-10 lg:grid-cols-[1.1fr_0.9fr]">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Offre</p>
            <h2 className="mt-3 text-3xl font-bold md:text-4xl">Nanovia Pro Pilot — 297 CAD / 30 jours</h2>
            <p className="mt-5 max-w-2xl text-gray-300">
              Une offre assistee pour PME locales, travailleurs autonomes et petites entreprises
              de services. On choisit une seule tache repetitive, puis on la transforme en flux IA
              simple et utile.
            </p>
            <p className="mt-4 text-sm text-gray-400">
              Apres le pilot : <span className="font-semibold text-white">79 CAD / mois</span>
            </p>
          </div>

          <div className="rounded-3xl border border-violet-500/30 bg-violet-500/10 p-8">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Ce qui est inclus</p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              {offerItems.map((item) => (
                <div key={item} className="rounded-2xl border border-violet-500/20 bg-black/20 p-4 text-sm text-violet-100">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-gray-800 bg-gray-900/40 px-6 py-20">
        <div className="mx-auto max-w-5xl">
          <div className="text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Exemples de taches automatisables</p>
            <h2 className="mt-3 text-3xl font-bold md:text-4xl">Des cas simples, concrets et vendables.</h2>
          </div>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {useCases.map((item) => (
              <div key={item} className="rounded-2xl border border-gray-800 bg-gray-950 p-5 text-sm text-gray-200">
                {item}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="demo" className="mx-auto max-w-6xl px-6 py-20">
        <div className="mb-12 text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Démo</p>
          <h2 className="mt-3 text-3xl font-bold md:text-4xl">Démo Nanovia Pro Pilot</h2>
          <p className="mx-auto mt-4 max-w-2xl text-gray-400">
            Voyez comment Nanovia transforme un message client brouillon en reponse professionnelle.
          </p>
        </div>
        <DemoPilotSection />
        <div className="mt-16">
          <div className="mx-auto max-w-3xl text-center">
            <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Exemples concrets</p>
            <h3 className="mt-3 text-3xl font-bold md:text-4xl">
              Trois transformations simples qui donnent envie de passer a l'action.
            </h3>
            <p className="mt-4 text-gray-400">
              Voici trois cas d'usage vendables pour montrer comment Nanovia structure une tache repetitive.
            </p>
          </div>
          <div className="mt-10 grid gap-6 lg:grid-cols-3">
            {concreteExamples.map((example) => (
              <article key={example.title} className="rounded-3xl border border-gray-800 bg-gray-900 p-6">
                <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">{example.title}</p>
                <div className="mt-6 rounded-2xl border border-red-500/20 bg-red-500/5 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-red-200">Avant</p>
                  <p className="mt-2 text-sm text-gray-300">{example.before}</p>
                </div>
                <div className="mt-4 rounded-2xl border border-green-500/20 bg-green-500/5 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.2em] text-green-200">Apres</p>
                  <p className="mt-2 text-sm text-gray-100">{example.after}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="prix" className="border-y border-gray-800 bg-gray-900/40 px-6 py-20">
        <div className="mx-auto max-w-4xl text-center">
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-violet-300">Prix</p>
          <h2 className="mt-3 text-3xl font-bold md:text-4xl">Une offre claire pour demarrer vite</h2>
          <div className="mt-10 rounded-3xl border border-violet-500/30 bg-gray-950 p-10">
            <p className="text-sm uppercase tracking-[0.25em] text-gray-400">Offre obligatoire</p>
            <div className="mt-3 text-4xl font-extrabold text-white">Nanovia Pro Pilot — 297 CAD / 30 jours</div>
            <p className="mt-2 text-lg text-gray-300">Une seule offre, un seul workflow, un seul objectif concret.</p>
            <div className="mx-auto mt-8 h-px max-w-md bg-gray-800" />
            <p className="mt-8 text-sm uppercase tracking-[0.25em] text-gray-400">Abonnement</p>
            <div className="mt-3 text-3xl font-bold text-violet-300">Apres le pilot : 79 CAD / mois</div>
            <p className="mt-3 text-gray-400">
              Si le pilot aide vraiment l'entreprise, on poursuit sur un abonnement simple.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href="/contact"
                className="inline-flex rounded-xl bg-violet-600 px-8 py-4 text-lg font-bold text-white transition hover:bg-violet-500"
              >
                Demarrer mon pilot Nanovia
              </Link>
              <a
                href={STRIPE_PAYMENT_LINK}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex rounded-xl border border-violet-500 bg-violet-500/10 px-8 py-4 text-lg font-bold text-violet-100 transition hover:bg-violet-500/20"
              >
                Payer 297 CAD et demarrer
              </a>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-4xl px-6 py-20 text-center">
        <h2 className="text-3xl font-bold md:text-4xl">Démarrer</h2>
        <p className="mx-auto mt-4 max-w-2xl text-gray-400">
          Si une tache repetitive vous fait perdre du temps chaque semaine, Nanovia Pro Pilot sert
          a la simplifier rapidement sans repartir de zero.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/contact"
            className="rounded-xl bg-violet-600 px-8 py-4 text-lg font-bold text-white transition hover:bg-violet-500"
          >
            Demarrer mon pilot Nanovia
          </Link>
          <a
            href="mailto:nanovia@duck.com"
            className="rounded-xl border border-gray-700 px-8 py-4 text-lg font-semibold text-white transition hover:border-violet-500"
          >
            nanovia@duck.com
          </a>
        </div>
      </section>
    </main>
  );
}
