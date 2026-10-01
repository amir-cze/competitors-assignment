/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#080b10",
          900: "#0c1118",
          800: "#131a24",
          700: "#1b2431",
          600: "#243044",
        },
        copper: {
          300: "#e8c39a",
          400: "#d4a574",
          500: "#c4894a",
        },
        paper: "#e8e2d6",
        mist: "#9aa6b5",
      },
      fontFamily: {
        serif: ["var(--font-serif)", "Georgia", "serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(255,255,255,0.04), 0 20px 40px -24px rgba(0,0,0,0.7)",
      },
    },
  },
  plugins: [],
};
