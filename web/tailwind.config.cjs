/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    extend: {
      colors: {
        // Misty, minimal light theme based on provided palette
        cursor: {
          bg: "#E8F4F8",           // mist background
          surface: "#FFFFFF",      // card surfaces
          surfaceHover: "#F1F7FA", // hover state for cards/buttons
          border: "#A0DCE8",       // serenity border
          borderLight: "#A0DCE8",
          text: "#212529",         // deep gray body
          textMuted: "#6B7280",    // muted gray
          textDim: "#9CA3AF",      // dimmer gray
          headline: "#175E63",     // adjusted deep lagoon for headings
          accent: "#14C4B8",       // electric teal CTA
          accentHover: "#00E5D8",  // vivid cyan hover
          success: "#22C55E",
          warning: "#EAB308",
          error: "#EF4444",
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
