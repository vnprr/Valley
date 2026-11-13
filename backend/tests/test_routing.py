"""Dostawcy tras: właściwe profile, format współrzędnych, brak trasy, koszt, preselekcja."""

import httpx
import pytest

from app.schemas.analysis import Place
from app.schemas.meeting import Participant, Point
from app.services import geoapify, osrm
from app.services.solve import pick_candidates

A = Point(lat=52.2297, lon=21.0122)
PLACES = [Place(id="p1", name="X", lat=52.25, lon=21.04), Place(id="p2", name="Y", lat=52.24, lon=21.00)]


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake(method):
        def handler(*args, **kwargs):
            url = args[1] if method == "request" else args[0]
            calls.append({"url": url, **kwargs})
            if "routematrix" in str(url):
                body = {"sources_to_targets": [[
                    {"time": 600, "source_index": 0, "target_index": 0},
                    {"time": None, "distance": None, "source_index": 0, "target_index": 1},
                ]]}
            else:
                body = {"code": "Ok", "durations": [[600.0, None]]}
            return httpx.Response(200, json=body, request=httpx.Request("GET", "http://x"))
        return handler

    monkeypatch.setattr(httpx, "get", fake("get"))
    monkeypatch.setattr(httpx, "request", fake("request"))
    return calls


@pytest.mark.parametrize("transport,instance", [("walk", "routed-foot"), ("bike", "routed-bike"), ("car", "routed-car")])
def test_osrm_uses_separate_instance_per_transport(captured, transport, instance):
    # OSRM ignoruje profil w ścieżce — o sieci tras decyduje instancja (routed-foot/-bike/-car).
    times = osrm.OsrmProvider("https://routing.openstreetmap.de", 5).travel_times([A], PLACES, transport)
    assert f"/{instance}/table/v1/" in captured[0]["url"]
    assert "21.012200,52.229700" in captured[0]["url"]  # lon,lat
    assert times == [[600.0, None]]  # brak trasy zostaje brakiem, nie szacunkiem


@pytest.mark.parametrize("transport,mode", [("walk", "walk"), ("bike", "bicycle"), ("car", "drive")])
def test_geoapify_matrix_modes_and_lonlat(captured, transport, mode):
    times = geoapify.GeoapifyProvider("k", 5).travel_times([A], PLACES, transport)
    body = captured[0]["json"]
    assert body["mode"] == mode
    assert body["sources"] == [{"location": [21.0122, 52.2297]}]
    assert times == [[600.0, None]]


def test_geoapify_credit_formula():
    provider = geoapify.GeoapifyProvider("k", 5)
    assert provider.credits(4, 32) == 128  # max(S,T) × min(S,T,10)
    assert provider.credits(12, 32) == 320  # powyżej 10 źródeł mnożnik się nie zwiększa
    assert osrm.OsrmProvider("u", 5).credits(4, 32) == 0


def test_errors_do_not_leak_api_key(monkeypatch):
    def boom(*args, **kwargs):
        request = httpx.Request("POST", "https://api.geoapify.com/v1/routematrix?apiKey=SEKRET")
        raise httpx.HTTPStatusError("x", request=request, response=httpx.Response(401, request=request))

    monkeypatch.setattr(httpx, "request", boom)
    with pytest.raises(Exception) as err:
        geoapify.GeoapifyProvider("SEKRET", 5).travel_times([A], PLACES, "walk")
    assert "SEKRET" not in str(err.value) and "401" in str(err.value)


def _pool():
    return [Place(id=f"{i}-{j}", name="c", lon=20.95 + i * 0.005, lat=52.19 + j * 0.005) for i in range(30) for j in range(20)]


def test_preselection_limits_candidates_and_covers_area():
    people = [Participant(name="A", transport="walk", start=Point(lat=52.20, lon=20.96)),
              Participant(name="B", transport="car", start=Point(lat=52.28, lon=21.09))]
    chosen = pick_candidates(_pool(), people, 0.5, 32)
    assert len(chosen) == 32
    # różnorodność: kandydaci w każdej ćwiartce obszaru, nie tylko „po środku”
    quadrants = {(c.lon > 21.02, c.lat > 52.24) for c in chosen}
    assert len(quadrants) == 4


def test_preselection_finds_near_optimal_place():
    """Na danych syntetycznych (czas = odległość / prędkość) wybór 32 z 600 nie gubi optimum."""
    people = [Participant(name="A", transport="walk", start=Point(lat=52.20, lon=20.97)),
              Participant(name="B", transport="bike", start=Point(lat=52.27, lon=21.08))]

    def score(pl):
        speeds = {"walk": 4.8, "bike": 15.0}
        t = [((pl.lon - p.start.lon) ** 2 * 68 ** 2 + (pl.lat - p.start.lat) ** 2 * 111 ** 2) ** 0.5 / speeds[p.transport]
             for p in people]
        return 0.5 * sum(t) / 2 + 0.5 * max(t)

    pool = _pool()
    best = min(score(pl) for pl in pool)
    best_chosen = min(score(pl) for pl in pick_candidates(pool, people, 0.5, 32))
    assert best_chosen <= best * 1.01


def test_known_places_are_preferred_for_cache_reuse():
    people = [Participant(name="A", transport="walk", start=Point(lat=52.22, lon=21.00)),
              Participant(name="B", transport="walk", start=Point(lat=52.24, lon=21.03))]
    first = {c.id for c in pick_candidates(_pool(), people, 0.5, 32)}
    people[0].start = Point(lat=52.2205, lon=21.0005)  # drobne przesunięcie
    second = {c.id for c in pick_candidates(_pool(), people, 0.5, 32, known=first)}
    assert len(first & second) >= 30
