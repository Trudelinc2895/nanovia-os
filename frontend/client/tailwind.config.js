/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        // ── Design System tokens ────────────────────────────────────────────
        // Fond Titanium/noir
        "bg-base":     "#0D0F12",
        "ui-surface":  "#13151A",
        "ui-elevated": "#1A1C23",

        // Bordures
        "ui-border":        "#1E2130",
        "ui-border-muted":  "#141620",
        "ui-border-strong": "#2A2D3E",

        // Accent principal — bleu
        primary: {
          DEFAULT: "#4F8CFF",
          hover:   "#3D7AEE",
          muted:   "#4F8CFF1A",
          strong:  "#6BA3FF",
        },

        // Texte
        "text-primary":   "#F1F5F9",
        "text-secondary": "#8892A4",
        "text-muted":     "#5A6478",
        "text-inverse":   "#0D0F12",

        // Sémantique
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

        // ── Alias legacy — rétrocompatibilité ───────────────────────────────
        brand:       { DEFAULT: "#4F8CFF", dark: "#3D7AEE", light: "#6BA3FF" },
        "tk-dark":   "#0D0F12",
        "tk-card":   "#13151A",
        "tk-border": "#1E2130",
        "tk-blue":   "#4F8CFF",
      },
      borderRadius: {
        sm:   "0.375rem",
        md:   "0.5rem",
        lg:   "0.75rem",
        xl:   "1rem",
        "2xl":"1.25rem",
        "3xl":"1.5rem",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
