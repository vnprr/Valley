// Paper Shaders używamy oszczędnie: tylko tam, gdzie materiał niesie znaczenie.
//  - Orb      — „żywy” wskaźnik AI w polu poleceń (przyspiesza, gdy model myśli),
//  - Mesh     — tło wybranej rekomendacji: kolory WSZYSTKICH uczestników zlane w jedno
//               (to jest wspólny grunt),
//  - Grain    — materiał przycisku „Znajdź miejsce”.
// Każdy shader to osobny kontekst WebGL, więc montujemy je warunkowo (nie w tle, nie dla
// wyłączonych przycisków) i ograniczamy liczbę pikseli. Przy `prefers-reduced-motion` stoją.
import { GrainGradient, MeshGradient } from "@paper-design/shaders-react";
import type { CSSProperties } from "react";

const still = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const speedOf = (v: number) => (still ? 0 : v);
const fill: CSSProperties = { position: "absolute", inset: 0, width: "100%", height: "100%" };

export const INK = ["#ff6a3d", "#2fe3b4", "#ffc72e", "#ff78bd", "#8fe84a", "#6cb6ff"];

export function Orb({ size = 28, speed = 0.35 }: { size?: number; speed?: number }) {
  return (
    <MeshGradient
      colors={["#ff6a3d", "#ffc72e", "#2fe3b4", "#ff78bd"]}
      distortion={0.9} swirl={0.5} grainMixer={0} grainOverlay={0}
      speed={speedOf(speed)} minPixelRatio={1} maxPixelCount={size * size * 4}
      style={{ width: size, height: size, borderRadius: "50%" }}
    />
  );
}

/** Zlane kolory uczestników; ciemna nakładka w CSS dba o czytelność tekstu. */
export function Mesh({ colors }: { colors: string[] }) {
  const palette = colors.length >= 2 ? colors : [...colors, "#ffc72e", "#ff6a3d"];
  return (
    <MeshGradient
      colors={palette.slice(0, 8)}
      distortion={0.85} swirl={0.35} grainMixer={0.25} grainOverlay={0.12}
      speed={speedOf(0.18)} minPixelRatio={1} maxPixelCount={420 * 220}
      style={fill}
    />
  );
}

export function Grain({ hot }: { hot: boolean }) {
  return (
    <GrainGradient
      colors={["#ff4d2e", "#ffb21f", "#ff5fa8"]} colorBack="#ffd23a"
      shape="wave" softness={0.75} intensity={0.45} noise={0.22}
      speed={speedOf(hot ? 1.1 : 0.12)} scale={1.4} minPixelRatio={1} maxPixelCount={520 * 120}
      style={fill}
    />
  );
}
