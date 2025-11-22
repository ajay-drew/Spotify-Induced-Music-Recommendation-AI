/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx,jsx,js}"],
  theme: {
    extend: {
      colors: {
        // Pastel pixels palette (kept for compatibility)
        pastelSky: "#a5b4fc",
        pastelMint: "#a7f3d0",
        pastelPeach: "#fed7aa",
        pastelRose: "#fecaca",
        pastelLavender: "#e9d5ff",
        pastelInk: "#0f172a",
        // Mario-inspired palette
        mario: {
          red: "#E6372F", // Mario red
          brick: "#C87928", // bricks
          gold: "#F7C344", // coin
          pipe: "#3FAC3B", // pipe green
          sky: "#96D7FF", // sky blue
          cloud: "#FFFFFF", // cloud white
          dark: "#1A1A1A", // text/base
          panel: "#EDE3D8", // light panel tint for contrast
        },
      },
      fontFamily: {
        pixel: ["'Press Start 2P'", "system-ui", "sans-serif"],
      },
      boxShadow: {
        "pixel-soft": "0 0 0 2px rgba(15,23,42,0.35)",
      },
      borderRadius: {
        pixel: "0.35rem",
      },
    },
  },
  plugins: [],
};


