// Motyw mapy: czarna, neutralna baza (bez granatowego odcienia) + kolorowe budynki 3D
// z OpenFreeMap. Kolor niosą budynki, woda i parki — reszta jest grafitem, żeby budynki
// i znaczniki wyraźnie „świeciły” kolorem na prawdziwej czerni.
import type { Map } from "maplibre-gl";

export const STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
// Start nad Śródmieściem: zoom ≥ 13, bo od tego poziomu kafle zawierają budynki 3D.
export const WARSAW = { center: [21.006, 52.2297] as [number, number], zoom: 13.6, pitch: 60, bearing: -24 };

const BLACK = "#050505";

const PAINT: [string, string, unknown][] = [
  ["background", "background-color", BLACK],
  ["water", "fill-color", "#07191a"],
  ["waterway", "line-color", "#0d2a2b"],
  ["landuse_residential", "fill-color", "#0a0a0a"],
  ["landuse_park", "fill-color", "#08150d"],
  ["landcover_wood", "fill-color", "#08150d"],
  ["highway_path", "line-color", "#1b1a19"],
  ["highway_minor", "line-color", "#252321"],
  ["highway_major_casing", "line-color", BLACK],
  ["highway_major_inner", "line-color", "#3a3633"],
  ["highway_major_subtle", "line-color", "#2f2c2a"],
  ["highway_motorway_casing", "line-color", BLACK],
  ["highway_motorway_inner", "line-color", "#5a4a3a"],
  ["highway_motorway_subtle", "line-color", "#453a30"],
  ["railway", "line-color", "#2a2624"],
  ["railway_transit", "line-color", "#2a2624"],
  ["railway_minor", "line-color", "#1f1d1b"],
  ["aeroway-area", "fill-color", "#0c0c0c"],
  ["aeroway-runway", "line-color", "#1f1d1b"],
  ["aeroway-runway-casing", "line-color", "#141414"],
  ["aeroway-taxiway", "line-color", "#191817"],
];

export function applyMapTheme(map: Map) {
  for (const [id, prop, value] of PAINT) {
    if (map.getLayer(id)) map.setPaintProperty(id, prop as never, value as never);
  }
  for (const layer of map.getStyle().layers) {
    if (layer.type === "symbol") {
      map.setPaintProperty(layer.id, "text-color" as never, "#8d867c" as never);
      map.setPaintProperty(layer.id, "text-halo-color" as never, BLACK as never);
    }
  }
  if (map.getLayer("building")) map.setLayoutProperty("building", "visibility", "none");

  // Budynki 3D z wektorowych kafli OpenMapTiles (pole render_height).
  const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
  map.addLayer(
    {
      id: "buildings-3d",
      type: "fill-extrusion",
      source: "openmaptiles",
      "source-layer": "building",
      minzoom: 12,
      paint: {
        "fill-extrusion-color": [
          "interpolate", ["linear"], ["coalesce", ["get", "render_height"], 8],
          0, "#0e1d38", 30, "#15365c", 90, "#1f5f92", 200, "#3fb4ea",
        ],
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 8],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.9,
        "fill-extrusion-vertical-gradient": true,
      },
    },
    firstLabel,
  );

  try {
    map.setSky({
      "sky-color": BLACK,
      "horizon-color": "#1c1612",
      "fog-color": BLACK,
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.5,
      "fog-ground-blend": 0.35,
    });
  } catch {
    /* starsze GPU / wersje — mapa działa i bez nieba */
  }
}
