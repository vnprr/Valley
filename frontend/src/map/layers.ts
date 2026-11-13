// Źródła GeoJSON i warstwy aplikacji: dolina (VALLEY), połączenia i kandydaci.
import type { GeoJSONSource, Map } from "maplibre-gl";
import type { Participant, Result } from "../api/types";

const EMPTY: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };
export const VALLEY_MAX_M = 1000; // wysokość najwyższego „wzgórza” w metrach
// Rampa doliny: gdzie najlepiej -> gdzie najgorzej. Ta sama w legendzie (CSS --ramp w app.css).
export const VALLEY_RAMP = ["#3be8b0", "#c4f04c", "#ffb627", "#ff5a36", "#ff3d8b"];

export function addAppLayers(map: Map) {
  for (const id of ["valley", "links", "candidates"]) map.addSource(id, { type: "geojson", data: EMPTY });

  map.addLayer({
    id: "valley",
    type: "fill-extrusion",
    source: "valley",
    layout: { visibility: "none" },
    paint: {
      // t = 0 -> najlepiej (dno doliny, miętowy), t = 1 -> najgorzej (szczyt, różowy żar)
      "fill-extrusion-color": [
        "interpolate", ["linear"], ["get", "t"],
        0, VALLEY_RAMP[0], 0.3, VALLEY_RAMP[1], 0.62, VALLEY_RAMP[2], 0.85, VALLEY_RAMP[3], 1, VALLEY_RAMP[4],
      ],
      "fill-extrusion-height": 0,
      "fill-extrusion-opacity": 0.8,
    },
  });
  // Czarna obwódka pod kolorową linią zamiast poświaty: linia czytelna na każdym tle.
  map.addLayer({
    id: "links-casing",
    type: "line",
    source: "links",
    layout: { "line-cap": "round" },
    paint: { "line-color": "#050505", "line-width": 5, "line-opacity": 0.55 },
  });
  map.addLayer({
    id: "links",
    type: "line",
    source: "links",
    layout: { "line-cap": "round" },
    paint: { "line-color": ["get", "color"], "line-width": 2.2, "line-dasharray": [0.1, 2.2], "line-opacity": 1 },
  });
  map.addLayer({
    id: "candidates",
    type: "circle",
    source: "candidates",
    paint: {
      "circle-radius": ["case", ["get", "feasible"], 5, 3.5],
      "circle-color": ["case", ["get", "feasible"], "#f3ece0", "#4a4642"],
      "circle-stroke-color": "#050505",
      "circle-stroke-width": 1.5,
      "circle-opacity": 0.92,
    },
  });
}

export function setData(map: Map, id: string, data: GeoJSON.FeatureCollection) {
  (map.getSource(id) as GeoJSONSource | undefined)?.setData(data);
}

export function candidatesGeoJSON(result: Result | null, top: Set<string>): GeoJSON.FeatureCollection {
  if (!result) return EMPTY;
  return {
    type: "FeatureCollection",
    features: result.candidates
      .filter((c) => !top.has(c.place.id))
      .map((c) => ({
        type: "Feature",
        properties: { id: c.place.id, feasible: c.feasible },
        geometry: { type: "Point", coordinates: [c.place.lon, c.place.lat] },
      })),
  };
}

/** Linie „kto → dokąd” do zaznaczonego miejsca. To NIE są trasy, tylko powiązanie. */
export function linksGeoJSON(participants: Participant[], result: Result | null, placeId: string | null) {
  const place = result?.candidates.find((c) => c.place.id === placeId)?.place;
  if (!place || result?.stale) return EMPTY;
  return {
    type: "FeatureCollection",
    features: participants
      .filter((p) => p.start)
      .map((p) => ({
        type: "Feature",
        properties: { color: p.color ?? "#ffc72e" },
        geometry: { type: "LineString", coordinates: [[p.start!.lon, p.start!.lat], [place.lon, place.lat]] },
      })),
  } as GeoJSON.FeatureCollection;
}

/** Płynne „wyrastanie” doliny: mnożnik wysokości 0 → 1 (lub odwrotnie). */
export function animateValley(map: Map, from: number, to: number, done?: () => void) {
  const start = performance.now();
  const duration = 900;
  const step = (now: number) => {
    const k = Math.min((now - start) / duration, 1);
    const eased = 1 - Math.pow(1 - k, 3);
    const factor = from + (to - from) * eased;
    map.setPaintProperty("valley", "fill-extrusion-height", [
      "*", ["+", 30, ["*", ["get", "t"], VALLEY_MAX_M]], factor,
    ]);
    if (k < 1) requestAnimationFrame(step);
    else done?.();
  };
  requestAnimationFrame(step);
}
