/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Newsreader", "ui-serif", "Georgia", "serif"],
      },
      colors: {
        ink: {
          950: "#0b0f19",
          900: "#10141f",
          850: "#151a27",
          800: "#1b2130",
          700: "#262d3f",
          600: "#3a4258",
          500: "#5a6478",
          400: "#8890a3",
          300: "#b3bacb",
          200: "#dde1ea",
          100: "#f2f4f8",
        },
        brass: {
          950: "#2e2408",
          900: "#453612",
          800: "#5c481a",
          700: "#7a5f24",
          600: "#9c7a2f",
          500: "#c19a45",
          400: "#d9b568",
          300: "#e8cd8f",
          200: "#f2e2b8",
          100: "#f9f1de",
        },
      },
      boxShadow: {
        panel: "0 1px 2px rgba(0,0,0,0.3), 0 8px 24px -8px rgba(0,0,0,0.5)",
        bubble: "0 1px 1px rgba(0,0,0,0.15), 0 4px 12px -4px rgba(0,0,0,0.35)",
      },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        dot: {
          "0%, 80%, 100%": { transform: "scale(0.6)", opacity: "0.4" },
          "40%": { transform: "scale(1)", opacity: "1" },
        },
      },
      animation: {
        rise: "rise 0.32s cubic-bezier(0.16, 1, 0.3, 1) both",
        dot1: "dot 1.2s ease-in-out infinite",
        dot2: "dot 1.2s ease-in-out 0.15s infinite",
        dot3: "dot 1.2s ease-in-out 0.3s infinite",
      },
    },
  },
  plugins: [],
};
