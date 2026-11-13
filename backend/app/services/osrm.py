"""Dostawca bez kluczy API — do lokalnego uruchomienia i prezentacji.

- kawiarnie: migawka OpenStreetMap (app/data/warsaw_cafes.json, licencja ODbL),
- czasy: publiczny OSRM FOSSGIS (routing.openstreetmap.de).

Uwaga: OSRM IGNORUJE nazwę profilu w ścieżce URL (/foot/, /driving/) — profil
zależy od danych, z którymi uruchomiono instancję. FOSSGIS ma osobne instancje
routed-foot / routed-bike / routed-car i to ich wybór decyduje o sieci tras
(sprawdzone: ta sama para punktów daje różne czasy, dystanse i przebiegi).

Dane są realne (prawdziwe lokale i trasy po sieci dróg), ale publiczny serwer
ma limity — w produkcji użyj Geoapify (GEOAPIFY_API_KEY).
"""

import json
from functools import lru_cache
from pathlib import Path

import httpx

from app.schemas.analysis import Place
from app.schemas.meeting import Point, Transport
from app.services.errors import ExternalServiceError
from app.services.providers import Rect, http_error_message

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "warsaw_cafes.json"
PROFILES = {
    "walk": "routed-foot/table/v1/foot",
    "bike": "routed-bike/table/v1/bike",
    "car": "routed-car/table/v1/driving",
}


@lru_cache
def _snapshot() -> list[Place]:
    return [Place(**p) for p in json.loads(SNAPSHOT.read_text("utf-8"))["places"]]


class OsrmProvider:
    name = "osrm"
    places_credits = 0  # lokalna migawka OSM
    max_parallel = 1  # publiczny serwer odpowiada 429 na równoległe zapytania

    def credits(self, sources: int, targets: int) -> int:
        return 0  # publiczny serwer — bez opłat, ale z limitami szybkości

    def __init__(self, base_url: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def find_cafes(self, rect: Rect) -> list[Place]:
        lon_min, lat_min, lon_max, lat_max = rect
        return [p for p in _snapshot() if lon_min <= p.lon <= lon_max and lat_min <= p.lat <= lat_max]

    def travel_times(self, origins: list[Point], places: list[Place], transport: Transport):
        coords = ";".join(f"{p.lon:.6f},{p.lat:.6f}" for p in [*origins, *places])
        n = len(origins)
        params = {
            "sources": ";".join(str(i) for i in range(n)),
            "destinations": ";".join(str(i) for i in range(n, n + len(places))),
            "annotations": "duration",
        }
        url = f"{self.base_url}/{PROFILES[transport]}/{coords}"
        try:
            response = httpx.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise ExternalServiceError(http_error_message("OSRM", exc)) from exc
        if data.get("code") != "Ok":
            raise ExternalServiceError(f"OSRM zwrócił błąd: {data.get('code')}")
        return [[None if t is None else float(t) for t in row] for row in data["durations"]]
