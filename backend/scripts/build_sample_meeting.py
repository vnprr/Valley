"""Buduje przykładowe spotkanie (dane startowe aplikacji) z PRAWDZIWYM zapytaniem do dostawcy tras.

    cd backend && python -m scripts.build_sample_meeting

Wynik trafia do app/data/demo_meeting.json i jest wgrywany do pustej bazy przy
starcie. Dzięki temu aplikacja ma gotowe dane przykładowe także bez sieci
(macierz czasów jest zapisana, suwak α przelicza ranking lokalnie).
"""

import json

from app.schemas.meeting import Participant, Point
from app.services.meetings import DEMO_FILE
from app.services.people import assign_colors
from app.services.providers import get_provider
from app.services.solve import compute_analysis

PEOPLE = [  # punkty startowe wskazane ręcznie na mapie
    Participant(id="demo-ola", name="Ola", transport="bike", start=Point(lat=52.1934, lon=21.0347)),   # Mokotów
    Participant(id="demo-pawel", name="Paweł", transport="walk", start=Point(lat=52.2330, lon=20.9876)),  # Wola
    Participant(id="demo-kasia", name="Kasia", transport="car", start=Point(lat=52.2549, lon=21.0453)),  # Praga
    Participant(id="demo-ja", name="Ja", transport="bike", start=Point(lat=52.2687, lon=20.9842)),     # Żoliborz
]


def main() -> None:
    provider = get_provider()
    participants = assign_colors(PEOPLE)
    analysis = compute_analysis(participants, provider, alpha=0.5)
    data = {
        "title": "Demo · kawa w 4 osoby",
        "participants": [p.model_dump(mode="json") for p in participants],
        "criteria": {"alpha": 0.5},
        "last_analysis": analysis.model_dump(mode="json"),
    }
    DEMO_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    print(f"Zapisano {DEMO_FILE} — {len(analysis.places)} kandydatów, dostawca: {provider.name}")


if __name__ == "__main__":
    main()
