// Mapa w tle całej aplikacji. Komponent tylko RYSUJE stan przekazany z App
// i zgłasza zdarzenia (klik, przeciągnięcie) przez callbacki.
import * as maplibregl from "maplibre-gl";
import type { Map, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
// MapLibre 6 szuka workera obok własnego pliku (import.meta.url). Vite w dev
// przenosi bibliotekę do node_modules/.vite/deps/, gdzie workera nie ma → 404.
// Jawny URL działa i w dev, i w buildzie.
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { useEffect, useRef, useState } from "react";
import { initialOf } from "../status";
import type { Participant, Point, Result } from "../api/types";
import { addAppLayers, animateValley, candidatesGeoJSON, linksGeoJSON, setData } from "./layers";
import { STYLE_URL, WARSAW, applyMapTheme } from "./theme";

maplibregl.setWorkerUrl(workerUrl);

export type ViewMode = "city" | "valley";

interface Props {
  meetingId: number | null;
  participants: Participant[];
  result: Result | null;
  selectedPid: string | null;
  selectedPlaceId: string | null;
  mode: ViewMode;
  picking: string | null;
  onPick: (point: Point) => void;
  onSelectParticipant: (id: string) => void;
  onSelectPlace: (id: string) => void;
  onMoveStart: (id: string, point: Point) => void;
}

export function MapView(props: Props) {
  const { meetingId, participants, result, selectedPid, selectedPlaceId, mode, picking } = props;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<Map | null>(null);
  const people = useRef(new globalThis.Map<string, Marker>());
  const spots = useRef<Marker[]>([]);
  const ghosts = useRef<Marker[]>([]); // propozycje startu z geokodera (do zatwierdzenia)
  const handlers = useRef(props); // zawsze aktualne callbacki dla zdarzeń mapy
  handlers.current = props;
  const [ready, setReady] = useState(false);

  // 1. Inicjalizacja (raz).
  useEffect(() => {
    const map = new maplibregl.Map({
      container: container.current!,
      style: STYLE_URL,
      ...WARSAW,
      maxPitch: 75,
      // Obrót jak w programie 3D: kierunek zależy tylko od ruchu myszy w poziomie,
      // nie od tego, czy kursor jest nad czy pod środkiem ('circular' odwraca kierunek).
      dragRotate: { around: "center", movement: "linear" },
      attributionControl: { compact: true },
    });
    mapRef.current = map;
    map.on("load", () => {
      applyMapTheme(map);
      addAppLayers(map);
      setReady(true);
    });
    map.on("click", (e) => {
      if (handlers.current.picking) handlers.current.onPick({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    });
    map.on("click", "candidates", (e) => {
      const id = e.features?.[0]?.properties?.id;
      if (id && !handlers.current.picking) handlers.current.onSelectPlace(String(id));
    });
    return () => map.remove();
  }, []);

  // 2. Znaczniki uczestników (kolor = kolor karty, można przeciągać).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const markers = people.current;
    for (const [id, marker] of markers) {
      if (!participants.some((p) => p.id === id && p.start)) {
        marker.remove();
        markers.delete(id);
      }
    }
    for (const p of participants) {
      if (!p.start) continue;
      let marker = markers.get(p.id);
      if (!marker) {
        const el = document.createElement("div");
        el.className = "pin";
        el.innerHTML = "<i></i><span></span>";
        el.addEventListener("click", (ev) => {
          ev.stopPropagation();
          handlers.current.onSelectParticipant(p.id);
        });
        const createdMarker = new maplibregl.Marker({ element: el, draggable: true, anchor: "center" })
          .setLngLat([p.start.lon, p.start.lat])
          .addTo(map);
        createdMarker.on("dragend", () => {
          const { lat, lng } = createdMarker.getLngLat();
          handlers.current.onMoveStart(p.id, { lat, lon: lng });
        });
        marker = createdMarker;
        markers.set(p.id, createdMarker);
      }
      marker.setLngLat([p.start.lon, p.start.lat]);
      const el = marker.getElement();
      el.style.setProperty("--c", p.color ?? "#ffc72e");
      el.classList.toggle("is-selected", p.id === selectedPid);
      el.querySelector("span")!.textContent = initialOf(p.name);
      el.title = p.name;
    }
  }, [participants, selectedPid]);

  // 2b. Propozycje startu: przerywany znacznik — to jeszcze NIE jest start.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    ghosts.current.forEach((m) => m.remove());
    ghosts.current = participants.filter((p) => p.start_proposal).map((p) => {
      const el = document.createElement("div");
      el.className = "pin is-proposal";
      el.innerHTML = "<span></span><label></label>";
      el.style.setProperty("--c", p.color ?? "#ffc72e");
      el.querySelector("span")!.textContent = initialOf(p.name);
      el.querySelector("label")!.textContent = `${p.name}: ${p.start_proposal!.label.split(",")[0]}?`;
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        handlers.current.onSelectParticipant(p.id);
      });
      return new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([p.start_proposal!.lon, p.start_proposal!.lat])
        .addTo(map);
    });
  }, [participants]);

  // 3. Wyniki: top 3 jako znaczniki, reszta kandydatów jako kropki, linie do wybranego.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    spots.current.forEach((m) => m.remove());
    spots.current = [];
    const recs = result?.recommendations ?? [];
    recs.forEach((rec, i) => {
      const el = document.createElement("div");
      el.className = `spot${rec.place.id === selectedPlaceId ? " is-selected" : ""}${result?.stale ? " is-stale" : ""}`;
      el.innerHTML = `<b><span>${i + 1}</span></b><label></label><i></i>`; // tarcza z numerem, trzonek, cień na gruncie
      el.querySelector("label")!.textContent = rec.place.name;
      el.addEventListener("click", (ev) => {
        ev.stopPropagation();
        handlers.current.onSelectPlace(rec.place.id);
      });
      spots.current.push(new maplibregl.Marker({ element: el, anchor: "bottom" }).setLngLat([rec.place.lon, rec.place.lat]).addTo(map));
    });
    setData(map, "candidates", candidatesGeoJSON(result, new Set(recs.map((r) => r.place.id))));
    setData(map, "links", linksGeoJSON(participants, result, selectedPlaceId));
    setData(map, "valley", result?.surface ?? { type: "FeatureCollection", features: [] });
  }, [ready, result, selectedPlaceId, participants]);

  // 4. Kadr: po otwarciu spotkania, nowym obliczeniu i nowej propozycji startu
  //    obejmij starty, propozycje i rekomendacje.
  const proposals = participants.map((p) => (p.start_proposal ? `${p.start_proposal.lat},${p.start_proposal.lon}` : "")).join("|");
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const pts = [
      ...participants.filter((p) => p.start).map((p) => [p.start!.lon, p.start!.lat]),
      ...participants.filter((p) => p.start_proposal).map((p) => [p.start_proposal!.lon, p.start_proposal!.lat]),
      ...(result?.recommendations ?? []).map((r) => [r.place.lon, r.place.lat]),
    ] as [number, number][];
    if (pts.length < 2) {
      map.flyTo(pts.length
        ? { center: pts[0], zoom: 14, pitch: WARSAW.pitch, padding: framePadding(), duration: 1600 }
        : { ...WARSAW, duration: 1600 });
      return;
    }
    const bounds = pts.reduce((b, p) => b.extend(p), new maplibregl.LngLatBounds(pts[0], pts[0]));
    map.fitBounds(bounds, {
      padding: framePadding(),
      pitch: mode === "valley" ? 62 : 55,
      bearing: WARSAW.bearing,
      duration: 1600,
      maxZoom: 14.5,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, meetingId, result?.computed_at, proposals]);

  // 5. CITY ↔ VALLEY: budynki znikają, dolina „wyrasta”.
  const shownValley = useRef(false);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const wantValley = mode === "valley" && !!result;
    if (wantValley === shownValley.current) return;
    shownValley.current = wantValley;
    if (wantValley) {
      map.setLayoutProperty("valley", "visibility", "visible");
      map.setLayoutProperty("buildings-3d", "visibility", "none");
      animateValley(map, 0, 1);
      map.easeTo({ pitch: 64, duration: 900 });
    } else {
      map.setLayoutProperty("buildings-3d", "visibility", "visible");
      animateValley(map, 1, 0, () => map.setLayoutProperty("valley", "visibility", "none"));
    }
  }, [ready, mode, result]);

  // 6. Tryb wybierania startu: kursor-celownik.
  useEffect(() => {
    mapRef.current?.getCanvas().style.setProperty("cursor", picking ? "crosshair" : "");
  }, [picking]);

  return (
    <>
      <div ref={container} className="map" />
      <div className="map-vignette" />
    </>
  );
}

/** Miejsce na mapie, którego nie zasłaniają panele (desktop: boki, telefon: dolny panel). */
function framePadding() {
  if (window.innerWidth <= 1100) {
    return { top: 80, bottom: Math.round(window.innerHeight * 0.44) + 90, left: 40, right: 40 };
  }
  return { top: 120, bottom: 150, left: 400, right: 410 };
}
