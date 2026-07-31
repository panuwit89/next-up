import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The build lands in ../static, which main.py mounts. Routing is hash-based
// (#/anime, #/finance/NVDA) so the server only ever serves "/" — no SPA
// catch-all is needed and /api, /webhook, /health can never be shadowed.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
});
