/** @type {import('tailwindcss').Config} */
// Tailwind v3 (PostCSS-based) is used for the candidate app — unlike v4 it emits
// FLAT CSS (no native @layer / oklch()), keeping it within the Chromium 108 floor
// of the Electron kiosk (and Firefox ESR 115 / Chrome 109 on the Win7 exam
// machines). Tailwind v4 would need Chrome 111+/Firefox 128+ (AD-67).
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
