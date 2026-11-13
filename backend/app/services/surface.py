"""Powierzchnia „doliny” dla trybu VALLEY (GeoJSON pod MapLibre fill-extrusion).

To WIZUALIZACJA PRZYBLIŻONA, nie mapa rzeczywistych czasów:
- komórka zawierająca sprawdzone miejsce dostaje jego dokładny score (najlepszy w komórce),
- pozostałe komórki: interpolacja IDW ze score sprawdzonych, wykonalnych miejsc,
- komórki dalej niż RADIUS od każdego sprawdzonego miejsca pomijamy — nie udajemy wiedzy.
IDW to średnia ważona, więc nigdy nie spada poniżej najlepszego score: dno doliny
leży zawsze w komórce zwycięskiego miejsca. Rekomendacje pochodzą wyłącznie z optimizer.py.
"""

import math

from app.schemas.analysis import PlaceScore

GRID = 24  # 24 × 24 komórki
POWER = 2  # wykładnik IDW
RADIUS_CELLS = 2.5  # zasięg „wiedzy” wokół sprawdzonego miejsca


def build_surface(scored: list[PlaceScore]) -> dict:
    known = [(s.place.lon, s.place.lat, s.score) for s in scored if s.score is not None]
    if len(known) < 3:
        return {"type": "FeatureCollection", "features": []}

    lon_min, lat_min, lon_max, lat_max = _bbox(known)
    lo, hi = min(v for *_, v in known), max(v for *_, v in known)
    span = (hi - lo) or 1.0
    dx, dy = (lon_max - lon_min) / GRID, (lat_max - lat_min) / GRID
    kx = math.cos(math.radians((lat_min + lat_max) / 2))  # stopnie lon -> „równe” odległości
    radius2 = (RADIUS_CELLS * max(dx * kx, dy)) ** 2

    features = []
    for gx in range(GRID):
        for gy in range(GRID):
            x0, y0 = lon_min + gx * dx, lat_min + gy * dy
            inside = [v for x, y, v in known if x0 <= x < x0 + dx and y0 <= y < y0 + dy]
            cx, cy = x0 + dx / 2, y0 + dy / 2
            if inside:
                value = min(inside)
            elif min(((x - cx) * kx) ** 2 + (y - cy) ** 2 for x, y, _ in known) > radius2:
                continue
            else:
                value = _idw(cx, cy, known, kx)
            features.append({
                "type": "Feature",
                "properties": {"value": round(value, 1), "t": round((value - lo) / span, 3), "measured": bool(inside)},
                "geometry": {"type": "Polygon", "coordinates": [[
                    [x0, y0], [x0 + dx * 0.94, y0], [x0 + dx * 0.94, y0 + dy * 0.94], [x0, y0 + dy * 0.94], [x0, y0],
                ]]},  # 6% przerwy między komórkami daje efekt „pikseli” 3D
            })
    return {"type": "FeatureCollection", "features": features, "min": lo, "max": hi}


def _idw(x, y, known, kx) -> float:
    num = den = 0.0
    for px, py, value in known:
        w = 1 / (((x - px) * kx) ** 2 + (y - py) ** 2) ** (POWER / 2)
        num += w * value
        den += w
    return num / den


def _bbox(known, pad=0.08):
    xs, ys = [k[0] for k in known], [k[1] for k in known]
    px, py = (max(xs) - min(xs)) * pad or 0.01, (max(ys) - min(ys)) * pad or 0.01
    return min(xs) - px, min(ys) - py, max(xs) + px, max(ys) + py
