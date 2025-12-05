/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    extend: {
      colors: {
        // Themeable color tokens (light/dark via CSS variables in index.css)
        cursor: {
          bg: "var(--cursor-bg)",
          surface: "var(--cursor-surface)",
          surfaceHover: "var(--cursor-surface-hover)",
          border: "var(--cursor-border)",
          borderLight: "var(--cursor-border-light)",
          text: "var(--cursor-text)",
          textMuted: "var(--cursor-text-muted)",
          textDim: "var(--cursor-text-dim)",
          headline: "var(--cursor-headline)",
          accent: "var(--cursor-accent)",
          accentHover: "var(--cursor-accent-hover)",
          success: "var(--cursor-success)",
          warning: "var(--cursor-warning)",
          error: "var(--cursor-error)",
        },
      },
      fontFamily: {
        outfit: [
          "Outfit",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "Inter",
          "system-ui",
          "sans-serif",
        ],
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
