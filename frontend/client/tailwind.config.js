/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        brand: { DEFAULT: "#7c3aed", dark: "#5b21b6", light: "#a78bfa" },
        "tk-dark":   "#0a0a0f",
        "tk-card":   "#111118",
        "tk-border": "#1e1e2e",
        "tk-blue":   "#0ea5e9",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
};
