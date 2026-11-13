"""Analiza: surowe dane z routingu (zapisywane) i wynik (liczony przy odczycie).

Zmiana α albo limitu czasu przelicza ranking z zapisanej macierzy `times_s`
— bez ponownego odpytywania API tras.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class Place(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    address: str | None = None


class RouteRow(BaseModel):
    """Czasy jednej osoby (dostawca + transport + start) do kolejnych miejsc."""

    fetched_at: datetime
    times: dict[str, float | None]  # id miejsca -> sekundy, None = brak trasy


class Usage(BaseModel):
    """Koszt obliczenia — do kontroli limitów (Geoapify free: 3000 kredytów/dzień)."""

    places_requests: int = 0
    matrix_requests: int = 0
    matrix_cells: int = 0  # pobrane pary osoba–miejsce
    reused_cells: int = 0  # pary wzięte z cache
    credits: int = 0  # szacunek wg cennika Geoapify (OSRM: 0)
    pool_size: int = 0  # ile kawiarni było w puli przed preselekcją
    duration_ms: int = 0


class Analysis(BaseModel):
    """To, co trafia do kolumny `last_analysis`."""

    provider: str  # "geoapify" | "osrm"
    computed_at: datetime
    fingerprint: str  # skrót startów i transportów -> czy wynik jest aktualny
    participant_ids: list[str]
    places: list[Place]
    times_s: list[list[float | None]]  # [uczestnik][miejsce], None = brak trasy
    route_cache: dict[str, RouteRow] = Field(default_factory=dict)  # klucz: dostawca:transport:start
    usage: Usage = Field(default_factory=Usage)
    comment: str | None = None  # komentarz AI z chwili obliczenia
    comment_alpha: float | None = None  # dla jakiego α powstał komentarz


class PlaceScore(BaseModel):
    place: Place
    times_min: dict[str, float | None]  # id uczestnika -> minuty
    mean_min: float | None
    max_min: float | None
    score: float | None
    feasible: bool
    reason: str | None = None  # dlaczego odrzucone


class Result(BaseModel):
    stale: bool  # start/transport/skład zmieniony po obliczeniu -> „Przelicz”
    provider: str
    computed_at: datetime
    alpha: float
    recommendations: list[PlaceScore]  # do 3 najlepszych, oddalonych od siebie
    candidates: list[PlaceScore]  # wszyscy sprawdzeni kandydaci
    surface: dict  # GeoJSON dla trybu VALLEY (przybliżenie)
    summary: str  # deterministyczne wyjaśnienie z liczb
    comment: str | None = None  # komentarz AI (jeśli pasuje do bieżącego α)
    usage: Usage
