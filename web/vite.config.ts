import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";

// Vite config for SIMRAI web UI, running on http://localhost:5658
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5658,
  },
  build: {
    outDir: "dist",
  },
});


