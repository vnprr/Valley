import "@fontsource/instrument-serif/400.css";
import "@fontsource/instrument-serif/400-italic.css";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles/app.css";

// Refrakcja (SVG w backdrop-filter) działa tylko w Chromium — w innych przeglądarkach
// zostaje czyste rozmycie. Flaga w <html> pozwala CSS wybrać wariant bez zgadywania.
if ("chrome" in window || /Chrom(e|ium)\//.test(navigator.userAgent)) document.documentElement.dataset.lens = "";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
