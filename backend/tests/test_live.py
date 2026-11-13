"""Testy PRAWDZIWYCH integracji — sieć i klucze, uruchamiane świadomie:

    LIVE=1 python -m pytest tests/test_live.py -v

Bez LIVE=1 są pomijane (zwykły `pytest` nie wychodzi do sieci).
Koszt jednego przebiegu: ~70 kredytów Geoapify i kilkanaście wywołań modelu.
"""

import os

import httpx
import pytest

from app.config import Settings
from app.schemas.meeting import Participant, Point
from app.services import agent, geocode
from app.services.geoapify import GeoapifyProvider
from app.services.osrm import OsrmProvider
from app.services.providers import get_provider
from tests.conftest import LIVE_KEYS, REAL_GEOCODE

pytestmark = pytest.mark.skipif(os.environ.get("LIVE") != "1", reason="ustaw LIVE=1, aby testować prawdziwe usługi")

A = Point(lat=52.2297, lon=21.0122)  # Rondo Dmowskiego
B = Point(lat=52.2549, lon=21.0453)  # Praga Północ — trasa przez Wisłę
needs_geoapify = pytest.mark.skipif(not LIVE_KEYS["GEOAPIFY_API_KEY"], reason="brak GEOAPIFY_API_KEY")
needs_openrouter = pytest.mark.skipif(not LIVE_KEYS["OPENROUTER_API_KEY"], reason="brak OPENROUTER_API_KEY")


def test_osrm_profiles_are_really_different():
    results = {}
    for instance, profile in [("routed-foot", "foot"), ("routed-bike", "bike"), ("routed-car", "driving")]:
        url = f"https://routing.openstreetmap.de/{instance}/route/v1/{profile}/{A.lon},{A.lat};{B.lon},{B.lat}"
        route = httpx.get(url, params={"overview": "full", "geometries": "geojson"}, timeout=30).json()["routes"][0]
        results[instance] = (route["duration"], route["distance"], len(route["geometry"]["coordinates"]))
    durations = [r[0] for r in results.values()]
    assert durations[0] > durations[1] > durations[2]  # pieszo > rower > auto
    assert len({round(r[1]) for r in results.values()}) == 3  # różne dystanse = różne sieci tras


@needs_geoapify
def test_geoapify_matrix_matches_routing_api_for_each_mode():
    provider = GeoapifyProvider(LIVE_KEYS["GEOAPIFY_API_KEY"], 30)
    place = [type("P", (), {"lon": B.lon, "lat": B.lat, "id": "b"})()]
    for transport, mode in [("walk", "walk"), ("bike", "bicycle"), ("car", "drive")]:
        matrix = provider.travel_times([A], place, transport)[0][0]
        route = httpx.get("https://api.geoapify.com/v1/routing", timeout=30, params={
            "waypoints": f"{A.lat},{A.lon}|{B.lat},{B.lon}", "mode": mode, "apiKey": LIVE_KEYS["GEOAPIFY_API_KEY"],
        }).json()["features"][0]["properties"]["time"]
        assert abs(matrix - route) / route < 0.02, transport


@needs_geoapify
def test_geoapify_geocoding(monkeypatch):
    monkeypatch.setattr(geocode, "get_settings", lambda: Settings(geoapify_api_key=LIVE_KEYS["GEOAPIFY_API_KEY"]))
    geocode.search.cache_clear()
    hit = geocode.search("Mokotów")
    assert hit and "Mokotów" in hit.label
    assert geocode.search("Rynek Główny Kraków") is None  # poza Warszawą


@needs_geoapify
def test_geoapify_solve_end_to_end(client, meeting):
    from app.main import app

    app.dependency_overrides[get_provider] = lambda: GeoapifyProvider(LIVE_KEYS["GEOAPIFY_API_KEY"], 30)
    client.patch(f"/api/meetings/{meeting['id']}", json={"actions": [
        {"type": "add_participant", "name": "Ola", "transport": "bike"},
        {"type": "add_participant", "name": "Adam", "transport": "walk"},
        {"type": "set_start", "ref": "Ola", "point": {"lat": A.lat, "lon": A.lon}},
        {"type": "set_start", "ref": "Adam", "point": {"lat": B.lat, "lon": B.lon}},
    ]})
    result = client.post(f"/api/meetings/{meeting['id']}/solve").json()["result"]
    usage = result["usage"]
    print("\nGeoapify /solve:", usage)
    assert result["provider"] == "geoapify" and len(result["recommendations"]) == 3
    assert usage["credits"] <= 1 + 2 * 32
    assert all(m is not None for r in result["recommendations"] for m in r["times_min"].values())


def test_osrm_solve_end_to_end():
    people = [Participant(name="Ola", transport="bike", start=A), Participant(name="Adam", transport="walk", start=B)]
    times = OsrmProvider("https://routing.openstreetmap.de", 30).travel_times([people[0].start], [B], "bike")
    assert times[0][0] and times[0][0] > 60


@needs_openrouter
def test_ai_manages_participants_through_api(client, meeting, monkeypatch):
    """Prawdziwy model: tekst -> akcje -> executor -> baza. Sprawdzamy ZAPISANY stan."""
    settings = Settings(
        openrouter_api_key=LIVE_KEYS["OPENROUTER_API_KEY"],
        openrouter_model=LIVE_KEYS["OPENROUTER_MODEL"] or Settings().openrouter_model,
    )
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    monkeypatch.setattr(geocode, "search", REAL_GEOCODE)  # prawdziwe geokodowanie
    mid = meeting["id"]

    def say(text):
        out = client.post(f"/api/meetings/{mid}/interpret", json={"text": text}).json()
        assert out["source"] == "ai", f"{text}: {out['warnings']}"
        people = client.get(f"/api/meetings/{mid}").json()["participants"]
        print(f"\n{text!r} -> {[(p['name'], p['transport'], p['max_minutes']) for p in people]}")
        return out, {p["name"]: p for p in people}

    _, people = say("Dodaj Olę i Pawła")
    assert set(people) == {"Ola", "Paweł"}
    ola_id = people["Ola"]["id"]

    _, people = say("Będziemy we czwórkę")
    assert len(people) == 4 and {"Ola", "Paweł"} <= set(people)

    _, people = say("Ola jedzie rowerem")
    assert people["Ola"]["transport"] == "bike" and len(people) == 4

    _, people = say("Zmień Oli transport na auto i limit na 25 minut")
    assert (people["Ola"]["transport"], people["Ola"]["max_minutes"]) == ("car", 25)

    _, people = say("Zmień imię Oli na Aleksandra")
    assert "Ola" not in people and people["Aleksandra"]["id"] == ola_id
    assert people["Aleksandra"]["transport"] == "car"  # inne pola bez zmian

    _, people = say("Nie usuwaj Aleksandry")
    assert len(people) == 4

    _, people = say("Usuń Pawła i dodaj Kasię")
    assert "Paweł" not in people and "Kasia" in people

    _, people = say("Kasia startuje z Mokotowa")
    proposal = people["Kasia"]["start_proposal"]
    assert people["Kasia"]["start"] is None and proposal and "Mokotów" in proposal["label"]

    _, people = say("Zatwierdź start Kasi")
    assert people["Kasia"]["start"] is not None


# ---------- bateria poleceń dla prawdziwego modelu ----------
# Każdy przypadek: stan początkowy -> polecenie -> sprawdzenie ZAPISANEGO stanu.

START = {"lat": 52.2297, "lon": 21.0122}
TEAM = [  # typowa grupa z częściowo wypełnionymi kartami
    {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 30},
    {"type": "set_start", "ref": "Ola", "point": START},
    {"type": "add_participant", "name": "Adam", "transport": "car"},
    {"type": "add_participant", "name": "Paweł", "transport": "walk"},
    {"type": "add_participant", "name": "Kasia"},
]
FOUR = [{"type": "set_participant_count", "count": 4}]


def _same(before, after, name, *changed):
    """Wszystkie pola osoby poza `changed` są bez zmian (prawdziwy PATCH)."""
    keep = {k: v for k, v in before[name].items() if k not in changed}
    return {k: v for k, v in after[name].items() if k not in changed} == keep


CASES = [
    ("liczba", [], "Spotykamy się w 4 osoby na kawę",
     lambda b, a, o: len(a) == 4 and all(p["transport"] is None and p["start"] is None for p in a.values())),
    ("mieszane", [], "Jadę rowerem, Ola samochodem, a dwie pozostałe osoby idą pieszo",
     lambda b, a, o: len(a) == 4 and a["Ja"]["transport"] == "bike" and a["Ola"]["transport"] == "car"
     and sorted(p["transport"] for n, p in a.items() if n not in ("Ja", "Ola")) == ["walk", "walk"]),
    ("dodaj-dwie", [], "Dodaj Olę i Pawła", lambda b, a, o: set(a) == {"Ola", "Paweł"}),
    ("imię-zajmuje-kartę", FOUR, "Ola jedzie rowerem",
     lambda b, a, o: len(a) == 4 and a["Ola"]["transport"] == "bike"),
    ("dodaj-do-czterech", FOUR, "Dodaj Pawła", lambda b, a, o: len(a) == 5 and "Paweł" in a),
    ("patch-transport", TEAM, "Adam jednak pójdzie pieszo",
     lambda b, a, o: a["Adam"]["transport"] == "walk" and _same(b, a, "Adam", "transport") and _same(b, a, "Ola")),
    ("patch-dwa-pola", TEAM, "Zmień Oli transport na auto i limit na 25 minut",
     lambda b, a, o: (a["Ola"]["transport"], a["Ola"]["max_minutes"]) == ("car", 25)
     and _same(b, a, "Ola", "transport", "max_minutes")),
    ("usuń", TEAM, "Usuń Pawła", lambda b, a, o: "Paweł" not in a and len(a) == 3),
    ("usuń-i-dodaj", TEAM, "Usuń Adama i dodaj Zosię", lambda b, a, o: "Adam" not in a and "Zosia" in a and len(a) == 4),
    ("zmień-imię", TEAM, "Zmień imię Oli na Aleksandra",
     lambda b, a, o: "Ola" not in a
     and {k: v for k, v in a["Aleksandra"].items() if k != "name"} == {k: v for k, v in b["Ola"].items() if k != "name"}),
    ("negacja", TEAM, "Nie usuwaj Oli", lambda b, a, o: a == b),
    ("lokalizacja", TEAM, "Ola startuje z Mokotowa",
     lambda b, a, o: a["Ola"]["start_proposal"] and "Mokotów" in a["Ola"]["start_proposal"]["label"]
     and a["Ola"]["start"] == b["Ola"]["start"]),
    ("lokalizacja-i-transport", TEAM, "Kasia jedzie z Ursynowa autem",
     lambda b, a, o: a["Kasia"]["transport"] == "car" and a["Kasia"]["start_proposal"]
     and "Ursynów" in a["Kasia"]["start_proposal"]["label"]),
    ("wyczyść-limit", TEAM, "Ola nie ma limitu czasu",
     lambda b, a, o: a["Ola"]["max_minutes"] is None and _same(b, a, "Ola", "max_minutes")),
    ("zmniejsz-pyta", TEAM, "Będziemy we trójkę", lambda b, a, o: a == b and o["question"]),
    ("wszyscy", TEAM, "Wszyscy jadą rowerem", lambda b, a, o: all(p["transport"] == "bike" for p in a.values())),
    ("dwie-osoby-naraz", TEAM, "Paweł i Kasia jadą autem",
     lambda b, a, o: a["Paweł"]["transport"] == "car" and a["Kasia"]["transport"] == "car" and _same(b, a, "Adam")),
    ("sprawiedliwie", TEAM, "Zależy nam, żeby nikt nie jechał długo", lambda b, a, o: o["meeting"]["criteria"]["alpha"] >= 0.7),
    ("szybko", TEAM, "Najważniejsze, żeby było jak najszybciej w sumie", lambda b, a, o: o["meeting"]["criteria"]["alpha"] <= 0.3),
    ("usuń-biernik", TEAM, "Usuń Olę", lambda b, a, o: "Ola" not in a and len(a) == 3),
    ("duplikat", TEAM, "Dodaj Olę", lambda b, a, o: list(a) == list(b)),
    ("nieznana-osoba", TEAM, "Usuń Zenona", lambda b, a, o: a == b),
    ("komunikacja-miejska", TEAM, "Kasia jedzie tramwajem", lambda b, a, o: a["Kasia"]["transport"] is None),
    ("zatwierdź-bez-propozycji", TEAM, "Zatwierdź start Kasi", lambda b, a, o: a == b),
    ("ponad-limit", [], "Będzie nas 8 osób", lambda b, a, o: len(a) <= 6),
    ("złożone", TEAM, "Adam i Paweł jadą rowerem, a Ola pieszo z limitem 20 minut",
     lambda b, a, o: a["Adam"]["transport"] == a["Paweł"]["transport"] == "bike"
     and (a["Ola"]["transport"], a["Ola"]["max_minutes"]) == ("walk", 20)),
    ("też-ale", TEAM, "Kasia też będzie jechała rowerem, ale max 40 minut",
     lambda b, a, o: (a["Kasia"]["transport"], a["Kasia"]["max_minutes"]) == ("bike", 40)),
    ("kontekst", TEAM, "Osoba, która jechała autem, jednak idzie pieszo",
     lambda b, a, o: a["Adam"]["transport"] == "walk" and _same(b, a, "Paweł")),
    ("dopełniacz-osoby", FOUR, "Osobie 2 ustaw rower", lambda b, a, o: a["Osoba 2"]["transport"] == "bike"),
    ("niejasne-nie-niszczy", TEAM, "Ola chyba nie da rady", lambda b, a, o: "Ola" in a or o["question"]),
]


@needs_openrouter
@pytest.mark.parametrize("case", CASES, ids=[c[0] for c in CASES])
def test_ai_command_battery(client, meeting, monkeypatch, case):
    _, setup, text, check = case
    settings = Settings(
        openrouter_api_key=LIVE_KEYS["OPENROUTER_API_KEY"],
        openrouter_model=LIVE_KEYS["OPENROUTER_MODEL"] or Settings().openrouter_model,
    )
    monkeypatch.setattr(agent, "get_settings", lambda: settings)
    monkeypatch.setattr(geocode, "search", REAL_GEOCODE)
    mid = meeting["id"]
    if setup:
        assert client.patch(f"/api/meetings/{mid}", json={"actions": setup}).status_code == 200
    before = {p["name"]: p for p in client.get(f"/api/meetings/{mid}").json()["participants"]}
    out = client.post(f"/api/meetings/{mid}/interpret", json={"text": text}).json()
    after = {p["name"]: p for p in client.get(f"/api/meetings/{mid}").json()["participants"]}
    print(f"\n{text!r}\n  reply={out['reply']!r} question={out['question']!r} applied={out['applied']} warn={out['warnings']}"
          f"\n  -> {[(n, p['transport'], p['max_minutes'], bool(p['start_proposal'])) for n, p in after.items()]}")
    assert out["source"] == "ai", out["warnings"]
    assert check(before, after, out)


@needs_openrouter
@pytest.mark.parametrize("alpha", [0.5, 1.0])
def test_ai_comment_names_the_real_winner(monkeypatch, alpha):
    """Pułapka z praktyki: zwycięzca ma wyższą średnią niż drugie miejsce, ale lepszy score."""
    from tests.test_ai import _result

    monkeypatch.setattr(agent, "get_settings", lambda: Settings(
        openrouter_api_key=LIVE_KEYS["OPENROUTER_API_KEY"],
        openrouter_model=LIVE_KEYS["OPENROUTER_MODEL"] or Settings().openrouter_model,
    ))
    result = _result("Velvet")
    result.alpha = alpha
    comment = agent.explain(result, [])
    print(f"\nα={alpha}: {comment}")
    assert comment is not None and "Velvet" in comment
