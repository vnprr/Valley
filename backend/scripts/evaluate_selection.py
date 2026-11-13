"""Czy preselekcja 32 kandydatów nie gubi lepszych miejsc? Porównanie z całą pulą.

    cd backend && python -m scripts.evaluate_selection

Dla kilku scenariuszy liczy dokładne czasy (publiczny OSRM, bez kosztów) do WSZYSTKICH
kawiarni w puli i porównuje najlepszy wynik z puli z najlepszym wśród wybranych kandydatów.
"""

import time

from app.config import get_settings
from app.services.errors import ExternalServiceError
from app.schemas.meeting import Participant, Point
from app.services import optimizer
from app.services.osrm import OsrmProvider
from app.services.solve import pick_candidates, search_rect

SCENARIOS = {
    "demo: 4 osoby, mieszany transport": [
        ("Ola", "bike", 52.1934, 21.0347), ("Paweł", "walk", 52.2330, 20.9876),
        ("Kasia", "car", 52.2549, 21.0453), ("Ja", "bike", 52.2687, 20.9842),
    ],
    "Wisła: Wola vs Saska Kępa, pieszo": [
        ("Ola", "walk", 52.2330, 20.9700), ("Adam", "walk", 52.2330, 21.0600),
    ],
    "Wisła: Bielany rower vs Targówek rower vs Mokotów auto": [
        ("Ola", "bike", 52.2850, 20.9450), ("Adam", "bike", 52.2700, 21.0500),
        ("Kasia", "car", 52.1900, 21.0200),
    ],
}


def times_for(provider, people, places):
    """Macierz [osoba][miejsce] w kawałkach po 90 miejsc, z przerwami (limit serwera)."""
    rows = {p.id: [] for p in people}
    for i in range(0, len(places), 90):
        chunk = places[i:i + 90]
        for transport in {p.transport for p in people}:
            group = [p for p in people if p.transport == transport]
            for p, row in zip(group, _patient(provider, [p.start for p in group], chunk, transport)):
                rows[p.id] += row
            time.sleep(2)
    # kolejność w wierszach odpowiada `places`, bo kawałki idą po kolei dla każdej grupy
    return [rows[p.id] for p in people]


def _patient(provider, origins, places, transport, tries=5):
    """Publiczny OSRM odpowiada 429 przy szybkich zapytaniach — czekamy i ponawiamy."""
    for attempt in range(tries):
        try:
            return provider.travel_times(origins, places, transport)
        except ExternalServiceError:
            time.sleep(5 * (attempt + 1))
    raise ExternalServiceError("OSRM: wciąż 429 po kilku próbach")


def main() -> None:
    settings = get_settings()
    provider = OsrmProvider(settings.osrm_url, 60)
    for title, spec in SCENARIOS.items():
        people = [Participant(id=n, name=n, transport=t, start=Point(lat=la, lon=lo)) for n, t, la, lo in spec]
        pool = provider.find_cafes(search_rect([(p.start.lon, p.start.lat) for p in people]))
        times = times_for(provider, people, pool)
        print(f"\n{title}: pula {len(pool)} kawiarni")
        for alpha in (0.0, 0.5, 1.0):
            chosen = {pl.id for pl in pick_candidates(pool, people, alpha, settings.max_candidates)}
            scored = optimizer.score_places(pool, times, [p.id for p in people], {}, {}, alpha)
            feasible = [s for s in scored if s.feasible]
            best = feasible[0]
            best_chosen = next(s for s in feasible if s.place.id in chosen)
            rank = feasible.index(best_chosen) + 1
            gap = best_chosen.score - best.score
            print(f"  α={alpha:.1f}: najlepsze w puli {best.score:5.1f} ({best.place.name}) | "
                  f"najlepsze z {len(chosen)} wybranych {best_chosen.score:5.1f} — miejsce {rank}/{len(feasible)}, "
                  f"strata {gap:.1f} pkt ({gap / best.score:.1%})")


if __name__ == "__main__":
    main()
