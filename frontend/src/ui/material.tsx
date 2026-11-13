// Materiał szkła: dwie rzeczy, których nie da się zrobić samym CSS.
//  1. <LensDefs/> — filtr SVG (turbulencja + displacement) używany jako backdrop-filter
//     na małych, „soczewkowych” elementach (pole poleceń, wyspa sesji). Tło za nimi
//     lekko faluje jak za ryflowanym szkłem. Tylko Chromium (flaga data-lens w <html>);
//     gdzie indziej zostaje samo rozmycie.
//  2. usePointerLight() — jeden globalny listener ustawia --mx/--my na szkle pod kursorem,
//     CSS rysuje z tego połysk. Bez re-renderów Reacta, jedna aktualizacja na klatkę.
import { useEffect } from "react";

export function LensDefs() {
  return (
    <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden>
      <filter id="lens" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.006 0.035" numOctaves="2" seed="11" result="ripples" />
        <feDisplacementMap in="SourceGraphic" in2="ripples" scale="22" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
  );
}

export function usePointerLight() {
  useEffect(() => {
    let frame = 0;
    const onMove = (e: PointerEvent) => {
      if (e.pointerType === "touch") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const glass = (e.target as Element | null)?.closest?.<HTMLElement>(".glass");
        if (!glass) return;
        const r = glass.getBoundingClientRect();
        glass.style.setProperty("--mx", `${e.clientX - r.left}px`);
        glass.style.setProperty("--my", `${e.clientY - r.top}px`);
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => { window.removeEventListener("pointermove", onMove); cancelAnimationFrame(frame); };
  }, []);
}
