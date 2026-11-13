import { defineConfig, devices } from "@playwright/test";

// Testy UI na prawdziwym backendzie (osobna baza e2e.db) i zbudowanym frontendzie.
// Domyślnie tryb bez AI (deterministyczny). E2E_AI=1 przekazuje klucz OpenRouter
// i testuje te same scenariusze z prawdziwym modelem.
// Uruchomienie: npm run build && npx playwright test
const ai = process.env.E2E_AI === "1";

export default defineConfig({
  testDir: "e2e",
  timeout: 120_000,
  workers: 1, // publiczny OSRM i darmowe modele mają limity zapytań
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:8010",
    launchOptions: { args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] },
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    command: "cd ../backend && rm -f e2e.db && .venv/bin/uvicorn app.main:app --port 8010",
    url: "http://127.0.0.1:8010/api/health",
    reuseExistingServer: false,
    env: {
      DATABASE_URL: "sqlite:///./e2e.db",
      SEED_DEMO: "true",
      GEOAPIFY_API_KEY: "", // trasy z darmowego OSRM — testy nie zużywają kredytów
      OPENROUTER_API_KEY: ai ? process.env.OPENROUTER_API_KEY ?? "" : "",
      ...(process.env.OPENROUTER_MODEL ? { OPENROUTER_MODEL: process.env.OPENROUTER_MODEL } : {}),
    },
  },
});
