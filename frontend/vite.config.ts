import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// W trybie dev /api trafia do FastAPI — bez problemów z CORS i bez wpisywania adresów.
export default defineConfig({
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1500 }, // MapLibre to ~1 MB — świadomie jeden pakiet
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
