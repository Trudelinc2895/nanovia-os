/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}","./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: { extend: { colors: { brand: { DEFAULT: "#7c3aed", dark: "#5b21b6", light: "#a78bfa" } } } },
  plugins: [],
};
