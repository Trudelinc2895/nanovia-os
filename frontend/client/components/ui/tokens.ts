/**
 * Design System Tokens — Nanovia
 * Palette Titanium/noir + accent bleu #4F8CFF
 *
 * Ces tokens sont la source de vérité.
 * tailwind.config.js les reflète via theme.extend pour que les classes Tailwind
 * soient disponibles dans toute l'app.
 */

export const colors = {
  // ── Fond ──────────────────────────────────────────────────────────────────
  bg: {
    base:     "#0D0F12", // fond principal (titanium/noir)
    surface:  "#13151A", // card, panneau
    elevated: "#1A1C23", // dropdown, tooltip, modal
  },

  // ── Bordures ──────────────────────────────────────────────────────────────
  border: {
    DEFAULT: "#1E2130",
    muted:   "#141620",
    strong:  "#2A2D3E",
  },

  // ── Accent principal — bleu ────────────────────────────────────────────────
  primary: {
    DEFAULT: "#4F8CFF",
    hover:   "#3D7AEE",
    muted:   "#4F8CFF1A", // fond translucide (badge, highlight)
    strong:  "#6BA3FF",   // texte sur fond sombre
  },

  // ── Texte ─────────────────────────────────────────────────────────────────
  text: {
    primary:   "#F1F5F9",
    secondary: "#8892A4",
    muted:     "#5A6478",
    inverse:   "#0D0F12",
  },

  // ── Sémantique ────────────────────────────────────────────────────────────
  success: {
    DEFAULT: "#22C55E",
    muted:   "#22C55E1A",
    text:    "#4ADE80",
  },
  warning: {
    DEFAULT: "#F59E0B",
    muted:   "#F59E0B1A",
    text:    "#FCD34D",
  },
  danger: {
    DEFAULT: "#EF4444",
    muted:   "#EF44441A",
    text:    "#F87171",
  },
  info: {
    DEFAULT: "#4F8CFF",
    muted:   "#4F8CFF1A",
    text:    "#6BA3FF",
  },
} as const;

export const radius = {
  sm:   "0.375rem", //  6px
  md:   "0.5rem",   //  8px
  lg:   "0.75rem",  // 12px
  xl:   "1rem",     // 16px
  "2xl":"1.25rem",  // 20px
  full: "9999px",
} as const;

export const fontSize = {
  xs:  "0.75rem",
  sm:  "0.875rem",
  base:"1rem",
  lg:  "1.125rem",
  xl:  "1.25rem",
  "2xl":"1.5rem",
  "3xl":"1.875rem",
} as const;

export const shadow = {
  primary: "0 0 0 3px rgba(79,140,255,0.25)",
  danger:  "0 0 0 3px rgba(239,68,68,0.25)",
} as const;

// Alias export for tailwind.config.js
const tokens = { colors, radius, fontSize, shadow };
export default tokens;
