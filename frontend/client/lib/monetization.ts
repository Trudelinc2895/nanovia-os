import monetizationCatalog from "../../../shared/catalog/monetization.json";

type MonetizationCatalog = typeof monetizationCatalog;

export type CatalogPlanSlug = keyof MonetizationCatalog["plans"];
export type CatalogModuleSlug = keyof MonetizationCatalog["modules"];
export type PlanBadgeVariant = "info" | "success" | "warning" | "danger";

const LEGACY_MODULE_SLUGS = Object.entries(monetizationCatalog.modules).reduce<Record<string, CatalogModuleSlug>>(
  (acc, [slug, entry]) => {
    if (entry.key && entry.key !== slug) {
      acc[entry.key] = slug as CatalogModuleSlug;
    }
    return acc;
  },
  {}
);

const MODULE_ICONS: Record<CatalogModuleSlug, string> = {
  operator: "🤖",
  content: "📢",
  micro_saas: "⚙️",
  ghost: "👻",
  decision: "🧠",
  knowledge: "📚",
  leverage: "📈",
  reverse: "🔬",
  offer: "🎯",
  execution: "⚡",
};

const PLAN_UI: Record<
  CatalogPlanSlug,
  {
    textClass: string;
    fillClass: string;
    badgeClass: string;
    badgeVariant: PlanBadgeVariant;
  }
> = {
  free: {
    textClass: "text-gray-400",
    fillClass: "bg-gray-500",
    badgeClass: "bg-gray-700 text-gray-300",
    badgeVariant: "info",
  },
  pro: {
    textClass: "text-violet-400",
    fillClass: "bg-purple-600",
    badgeClass: "bg-purple-700/60 text-purple-200",
    badgeVariant: "success",
  },
  business: {
    textClass: "text-yellow-400",
    fillClass: "bg-yellow-500",
    badgeClass: "bg-yellow-600/60 text-yellow-200",
    badgeVariant: "warning",
  },
};

export const PLAN_SLUGS = Object.keys(monetizationCatalog.plans) as CatalogPlanSlug[];
export const MODULE_SLUGS = Object.keys(monetizationCatalog.modules) as CatalogModuleSlug[];

export function normalizeModuleSlug(slug: string): string {
  return LEGACY_MODULE_SLUGS[slug] ?? slug;
}

export function getModuleIcon(slug: string): string {
  const canonicalSlug = normalizeModuleSlug(slug);
  return MODULE_ICONS[canonicalSlug as CatalogModuleSlug] ?? "🔷";
}

export function getModuleCatalogEntry(slug: string) {
  const canonicalSlug = normalizeModuleSlug(slug) as CatalogModuleSlug;
  const entry = monetizationCatalog.modules[canonicalSlug];
  if (!entry) {
    return null;
  }
  return {
    slug: canonicalSlug,
    ...entry,
  };
}

export function getModulePresentation(module: {
  slug: string;
  name?: string;
  description?: string;
  price_usd?: number;
}) {
  const catalogEntry = getModuleCatalogEntry(module.slug);
  return {
    slug: catalogEntry?.slug ?? normalizeModuleSlug(module.slug),
    name: catalogEntry?.name ?? module.name ?? normalizeModuleSlug(module.slug),
    description: catalogEntry?.description ?? module.description ?? "",
    priceUsd: catalogEntry?.price_usd ?? module.price_usd ?? 0,
    icon: getModuleIcon(module.slug),
  };
}

export function getPlanTextClass(plan: string): string {
  return PLAN_UI[plan as CatalogPlanSlug]?.textClass ?? PLAN_UI.free.textClass;
}

export function getPlanFillClass(plan: string): string {
  return PLAN_UI[plan as CatalogPlanSlug]?.fillClass ?? PLAN_UI.free.fillClass;
}

export function getPlanBadgeClass(plan: string): string {
  return PLAN_UI[plan as CatalogPlanSlug]?.badgeClass ?? PLAN_UI.free.badgeClass;
}

export function getPlanBadgeVariant(plan: string): PlanBadgeVariant {
  return PLAN_UI[plan as CatalogPlanSlug]?.badgeVariant ?? PLAN_UI.free.badgeVariant;
}

export function getPlanDisplayName(plan: string): string {
  return monetizationCatalog.plans[plan as CatalogPlanSlug]?.name ?? plan;
}
