"""Izolowana baza w pamięci, sztuczny dostawca tras i geokoder. Testy nie wychodzą do sieci."""

import os

# Prawdziwe klucze zapamiętujemy tylko dla test_live.py (uruchamianego z LIVE=1).
LIVE_KEYS = {k: os.environ.get(k, "") for k in ("GEOAPIFY_API_KEY", "OPENROUTER_API_KEY", "OPENROUTER_MODEL")}

# Zanim zaimportujemy aplikację: żadnych prawdziwych kluczy ani pliku bazy.
os.environ.update(OPENROUTER_API_KEY="", GEOAPIFY_API_KEY="", SEED_DEMO="false", DATABASE_URL="sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.schemas.analysis import Place
from app.schemas.meeting import StartProposal
from app.services import geocode
from app.services.errors import ExternalServiceError
from app.services.providers import get_provider

REAL_GEOCODE = geocode.search  # dla test_live.py
SPEED = {"walk": 80.0, "bike": 250.0, "car": 500.0}  # metry na minutę (tylko w testach!)


class FakeProvider:
    """Przewidywalny dostawca: 64 kawiarnie w siatce 8 × 8, czas = odległość / prędkość."""

    name = "fake"
    places_credits = 1
    max_parallel = 1

    def __init__(self):
        self.calls = {"cafes": 0, "times": 0, "cells": 0}
        self.fail = False
        self.unreachable: set[str] = set()  # id miejsc bez trasy

    def find_cafes(self, rect):
        self.calls["cafes"] += 1
        if self.fail:
            raise ExternalServiceError("Geoapify: brak połączenia (ConnectError)")
        lon0, lat0, lon1, lat1 = rect
        return [
            Place(id=f"c{i}{j}", name=f"Kawiarnia {i}{j}",
                  lon=lon0 + (lon1 - lon0) * (i + 0.5) / 8, lat=lat0 + (lat1 - lat0) * (j + 0.5) / 8)
            for i in range(8) for j in range(8)
        ]

    def travel_times(self, origins, places, transport):
        self.calls["times"] += 1
        self.calls["cells"] += len(origins) * len(places)
        rows = []
        for o in origins:
            row = []
            for p in places:
                meters = (((p.lon - o.lon) * 68_000) ** 2 + ((p.lat - o.lat) * 111_000) ** 2) ** 0.5
                row.append(None if p.id in self.unreachable else meters / SPEED[transport] * 60)
            rows.append(row)
        return rows

    def credits(self, sources, targets):
        return max(sources, targets) * min(sources, targets, 10)


def fake_geocode(query: str):
    known = {"mokotów": StartProposal(lat=52.1937, lon=21.0444, label="Mokotów, Warszawa")}
    return known.get(query.lower())


@pytest.fixture
def provider():
    return FakeProvider()


@pytest.fixture
def client(provider, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_db():
        with TestSession() as db:
            yield db

    monkeypatch.setattr(geocode, "search", fake_geocode)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_provider] = lambda: provider
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def meeting(client):
    return client.post("/api/meetings", json={"title": "Test"}).json()


def act(client, mid, *actions, status=200):
    """PATCH z akcjami — ta sama ścieżka, której używa UI i AI."""
    response = client.patch(f"/api/meetings/{mid}", json={"actions": list(actions)})
    assert response.status_code == status, response.text
    return response.json()


def add_ready_people(client, mid):
    return act(
        client, mid,
        {"type": "add_participant", "name": "Ola", "transport": "bike"},
        {"type": "add_participant", "name": "Paweł", "transport": "walk"},
        {"type": "add_participant", "name": "Kasia", "transport": "car"},
        *[
            {"type": "set_start", "ref": name, "point": point}
            for name, point in [
                ("Ola", {"lat": 52.2297, "lon": 21.0122}),
                ("Paweł", {"lat": 52.2400, "lon": 20.9900}),
                ("Kasia", {"lat": 52.2000, "lon": 21.0500}),
            ]
        ],
    )
