"""Konfiguracja z backend/.env (pydantic-settings). Zmienne środowiskowe mają pierwszeństwo.

Brak kluczy NIE blokuje aplikacji:
- bez GEOAPIFY_API_KEY  -> kawiarnie z migawki OSM + czasy z publicznego OSRM,
- bez OPENROUTER_API_KEY -> prosty parser reguł (ograniczone możliwości).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ścieżka bezwzględna: .env działa niezależnie od katalogu, z którego startuje uvicorn.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_MODEL = "openai/gpt-4.1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    database_url: str = "sqlite:///./common_ground.db"
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    geoapify_api_key: str = ""
    openrouter_api_key: str = ""
    # Zmierzone na baterii 30 poleceń (tests/test_live.py): gpt-4.1 90/90 w 3 przebiegach,
    # ~0,0044 USD i ~1,7 s na polecenie. gpt-4.1-mini taniej, ale 1–3 błędy na 30.
    openrouter_model: str = DEFAULT_MODEL

    # Publiczny OSRM (FOSSGIS): osobne instancje routed-foot / routed-bike / routed-car.
    osrm_url: str = "https://routing.openstreetmap.de"
    http_timeout_s: float = 20.0

    # Ilu kandydatów dostaje dokładną macierz czasów (koszt Geoapify ≈ osoby × kandydaci).
    max_candidates: int = 32
    # Ważność zapisanych czasów tras.
    route_cache_ttl_hours: int = 24

    # Wgraj spotkanie demonstracyjne z nagranym wynikiem, gdy baza jest pusta.
    seed_demo: bool = True

    @field_validator("openrouter_model")
    @classmethod
    def _model_or_default(cls, value: str) -> str:
        # Puste „OPENROUTER_MODEL=” w .env nie może dać modelu bez nazwy.
        return value.strip() or DEFAULT_MODEL


@lru_cache
def get_settings() -> Settings:
    return Settings()
