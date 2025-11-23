/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    extend: {
      colors: {
        // Cursor-inspired minimal dark theme
        cursor: {
          bg: "#1e1e1e",
          surface: "#252526",
          surfaceHover: "#2d2d30",
          border: "#3e3e42",
          borderLight: "#464647",
          text: "#cccccc",
          textMuted: "#858585",
          textDim: "#6a6a6a",
          accent: "#007acc",
          accentHover: "#0098ff",
          success: "#4ec9b0",
          warning: "#dcdcaa",
          error: "#f48771",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
        mono: [
          "SF Mono",
          "Monaco",
          "Inconsolata",
          "Fira Code",
          "Consolas",
          "monospace",
        ],
      },
      fontSize: {
        xs: ["11px", { lineHeight: "1.4" }],
        sm: ["13px", { lineHeight: "1.5" }],
        base: ["14px", { lineHeight: "1.6" }],
        lg: ["16px", { lineHeight: "1.6" }],
      },
    },
  },
  plugins: [],
};
