// Status karty uczestnika — jedna funkcja, żeby karta i mapa mówiły to samo.
import type { Participant, Result } from "./api/types";

export type Tone = "warn" | "ok" | "info" | "bad";

export function cardStatus(p: Participant, result: Result | null, placeId: string | null): { text: string; tone: Tone } {
  if (!p.start && p.start_proposal) return { text: "Zatwierdź start", tone: "info" };
  if (!p.start) return { text: "Uzupełnij start", tone: "warn" };
  if (!p.transport) return { text: "Wybierz transport", tone: "warn" };
  if (!result) return { text: "Gotowy", tone: "ok" };
  // Analiza nieaktualna (zmiana startu/transportu/składu) -> nie pokazujemy starego czasu.
  if (result.stale) return { text: "Przelicz", tone: "info" };
  const minutes = result.candidates.find((c) => c.place.id === placeId)?.times_min[p.id];
  if (minutes === undefined) return { text: "Przelicz", tone: "info" };
  if (minutes === null) return { text: "Brak trasy", tone: "bad" };
  const over = p.max_minutes != null && minutes > p.max_minutes;
  return { text: `Czas: ${Math.round(minutes)} min`, tone: over ? "bad" : "ok" };
}

/** Inicjał do awatara i znacznika: „Osoba 3” -> „3”, „Ola” -> „O”. */
export const initialOf = (name: string) => /^Osoba (\d+)$/.exec(name)?.[1] ?? (name.slice(0, 1).toUpperCase() || "·");
