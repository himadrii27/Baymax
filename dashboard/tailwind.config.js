/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bh: {
          red:        "#D63B3B",
          "red-dark": "#B02E2E",
          dark:       "#1a1a2e",
          "dark-2":   "#16213e",
          muted:      "#7a7a9a",
        },
      },
      animation: {
        "fade-in":  "fadeIn 0.3s ease-in-out",
        "slide-up": "slideUp 0.25s ease-out",
        blink:      "blink 1.2s infinite",
      },
      keyframes: {
        fadeIn:  { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: { "0%": { transform: "translateY(8px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
        blink:   { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.2" } },
      },
    },
  },
  plugins: [],
};
