"""Geoapify: Places API (kawiarnie) i Route Matrix API (czasy dojazdu).

Zweryfikowane na żywo: Route Matrix daje te same czasy co Routing API dla
walk / bicycle / drive; `location` to [lon, lat]; brak trasy = time null.
Koszt macierzy: max(S, T) × min(S, T, 10) kredytów; Places: 1 kredyt.
"""

import httpx

from app.schemas.analysis import Place
from app.schemas.meeting import Point, Transport
from app.services.errors import ExternalServiceError
from app.services.providers import Rect, http_error_message

PLACES_URL = "https://api.geoapify.com/v2/places"
MATRIX_URL = "https://api.geoapify.com/v1/routematrix"
MODES = {"walk": "walk", "bike": "bicycle", "car": "drive"}


class GeoapifyProvider:
    name = "geoapify"
    places_credits = 1
    max_parallel = 3  # plan darmowy: do 5 zapytań/s

    def __init__(self, api_key: str, timeout: float):
        self.api_key = api_key
        self.timeout = timeout

    def find_cafes(self, rect: Rect) -> list[Place]:
        params = {
            "categories": "catering.cafe",
            "filter": "rect:" + ",".join(f"{v:.5f}" for v in rect),
            "limit": 300,  # pula do bezpłatnej preselekcji w solve.py
            "apiKey": self.api_key,
        }
        data = self._request("GET", PLACES_URL, params=params)
        places = []
        for feature in data.get("features", []):
            p = feature.get("properties", {})
            if p.get("name") and p.get("lat") is not None:
                places.append(Place(
                    id=str(p.get("place_id", f"{p['lat']},{p['lon']}")), name=p["name"],
                    lat=p["lat"], lon=p["lon"], address=p.get("address_line2"),
                ))
        return places

    def travel_times(self, origins: list[Point], places: list[Place], transport: Transport):
        body = {
            "mode": MODES[transport],
            "sources": [{"location": [o.lon, o.lat]} for o in origins],
            "targets": [{"location": [p.lon, p.lat]} for p in places],
        }
        data = self._request("POST", MATRIX_URL, params={"apiKey": self.api_key}, json=body)
        times: list[list[float | None]] = [[None] * len(places) for _ in origins]
        for row in data.get("sources_to_targets", []):
            for cell in row:
                if cell and cell.get("time") is not None:
                    times[cell["source_index"]][cell["target_index"]] = float(cell["time"])
        return times

    def credits(self, sources: int, targets: int) -> int:
        return max(sources, targets) * min(sources, targets, 10)

    def _request(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = httpx.request(method, url, timeout=self.timeout, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(http_error_message("Geoapify", exc)) from exc
