"""Wspólny interfejs dostawców danych geograficznych + wybór dostawcy.

Dostawca odpowiada na dwa pytania:
1. jakie kawiarnie są w prostokącie?              -> find_cafes(rect)
2. ile sekund jedzie każda osoba do każdego miejsca? -> travel_times(origins, places, transport)
oraz mówi, ile kosztuje macierz                     -> credits(sources, targets)
"""

from typing import Protocol

from app.config import get_settings
from app.schemas.analysis import Place
from app.schemas.meeting import Point, Transport

Rect = tuple[float, float, float, float]  # lon_min, lat_min, lon_max, lat_max


class Provider(Protocol):
    name: str
    places_credits: int  # koszt jednego zapytania o kawiarnie
    max_parallel: int  # ile macierzy można pobierać naraz

    def find_cafes(self, rect: Rect) -> list[Place]: ...

    def travel_times(
        self, origins: list[Point], places: list[Place], transport: Transport
    ) -> list[list[float | None]]: ...

    def credits(self, sources: int, targets: int) -> int: ...


def get_provider() -> Provider:
    """Zależność FastAPI. Z kluczem -> Geoapify (główny dostawca),
    bez klucza -> migawka OSM + publiczny OSRM (tryb demonstracyjny)."""
    settings = get_settings()
    if settings.geoapify_api_key:
        from app.services.geoapify import GeoapifyProvider

        return GeoapifyProvider(settings.geoapify_api_key, settings.http_timeout_s)
    from app.services.osrm import OsrmProvider

    return OsrmProvider(settings.osrm_url, settings.http_timeout_s)


def http_error_message(service: str, exc: Exception) -> str:
    """Czytelny opis błędu HTTP (bez adresu URL, który zawiera klucz API)."""
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        reason = {401: "odrzucony klucz API", 403: "brak dostępu lub limit", 429: "przekroczony limit zapytań — spróbuj za chwilę"}
        return f"{service}: HTTP {code} ({reason.get(code, 'błąd usługi')})"
    if isinstance(exc, httpx.TimeoutException):
        return f"{service}: przekroczony czas odpowiedzi"
    return f"{service}: brak połączenia ({exc.__class__.__name__})"
