import Link from "next/link";

export default function NotFound() {
  return (
    <main className="min-h-screen bg-gray-950 text-white flex flex-col items-center justify-center px-6">
      <div className="text-center max-w-md">
        <div className="text-8xl font-extrabold text-violet-400 mb-4">404</div>
        <h1 className="text-2xl font-bold mb-3">Page introuvable</h1>
        <p className="text-gray-400 mb-8">
          Cette page n&apos;existe pas ou a été déplacée.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/"
            className="bg-violet-600 hover:bg-violet-500 text-white font-semibold px-6 py-3 rounded-lg transition"
          >
            Retour à l&apos;accueil
          </Link>
          <Link
            href="/dashboard"
            className="bg-gray-800 hover:bg-gray-700 text-white font-semibold px-6 py-3 rounded-lg transition border border-gray-700"
          >
            Dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
