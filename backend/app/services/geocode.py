"""Geokodowanie słownego opisu startu („Mokotów”) na propozycję punktu.

Wynik jest tylko PROPOZYCJĄ — użytkownik musi go zatwierdzić. Szukamy wyłącznie
w obszarze Warszawy; brak trafienia = None (nigdy nie zgadujemy współrzędnych).
Geoapify Geocoding (1 kredyt), bez klucza: Nominatim (OpenStreetMap).
"""

import logging
from functools import lru_cache

import httpx

from app.config import get_settings
from app.schemas.meeting import AREA, StartProposal

log = logging.getLogger(__name__)
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GEOAPIFY = "https://api.geoapify.com/v1/geocode/search"


@lru_cache(maxsize=256)
def search(query: str) -> StartProposal | None:
    settings = get_settings()
    text = f"{query.strip()}, Warszawa"
    try:
        if settings.geoapify_api_key:
            hit = _geoapify(text, settings.geoapify_api_key, settings.http_timeout_s)
        else:
            hit = _nominatim(text, settings.http_timeout_s)
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        log.warning("Geokodowanie nie powiodło się (%s): %s", query, exc.__class__.__name__)
        return None
    if hit is None:
        return None
    lat, lon, label = hit
    if not (AREA[1] <= lat <= AREA[3] and AREA[0] <= lon <= AREA[2]):
        return None  # trafienie poza obszarem demo
    return StartProposal(lat=lat, lon=lon, label=label[:160])


def _geoapify(text: str, key: str, timeout: float):
    params = {
        "text": text, "lang": "pl", "limit": 1, "format": "json",
        "filter": "rect:" + ",".join(map(str, AREA)), "apiKey": key,
    }
    response = httpx.get(GEOAPIFY, params=params, timeout=timeout)
    response.raise_for_status()
    results = response.json().get("results", [])
    return (results[0]["lat"], results[0]["lon"], results[0]["formatted"]) if results else None


def _nominatim(text: str, timeout: float):
    params = {
        "q": text, "format": "jsonv2", "limit": 1, "bounded": 1, "accept-language": "pl",
        "viewbox": f"{AREA[0]},{AREA[3]},{AREA[2]},{AREA[1]}",
    }
    # Zasady Nominatim wymagają identyfikującego User-Agenta.
    headers = {"User-Agent": "common-ground-mvp/0.2"}
    response = httpx.get(NOMINATIM, params=params, headers=headers, timeout=timeout)
    response.raise_for_status()
    results = response.json()
    return (float(results[0]["lat"]), float(results[0]["lon"]), results[0]["display_name"]) if results else None
