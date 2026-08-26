/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Outfit", "Segoe UI Variable", "Segoe UI", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["DM Mono", "Cascadia Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
