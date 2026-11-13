"""Agent AI (PydanticAI + OpenRouter): tekst -> MeetingCommand (lista typowanych akcji).

Agent dostaje aktualne karty z ich id i zwraca INTENCJE ZMIAN, nie nową listę osób.
Nic nie zapisuje — akcje wykonuje deterministycznie services/people.apply_actions.
Bez klucza (lub przy błędzie) działa parser reguł, a UI dostaje czytelny powód.
"""

import json
import logging
import os
from typing import Literal

from app.config import get_settings
from app.schemas.analysis import Result
from app.schemas.commands import MeetingCommand
from app.schemas.meeting import Criteria, Participant
from app.services import intent_rules
from app.services import people as people_service

log = logging.getLogger(__name__)
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

INSTRUCTIONS = """\
Jesteś interfejsem aplikacji szukającej sprawiedliwego miejsca spotkania w Warszawie.
Dostajesz stan spotkania (karty osób) i polecenie. Zwróć listę akcji do wykonania.
Wskazując osobę (ref), podaj jej name DOKŁADNIE tak, jak jest na liście (imiona są unikalne).
Sprawdź dwa razy, że ref to osoba, o której mówi polecenie.

AKCJE
- add_participant: nowa karta. name w mianowniku („Pawła” -> „Paweł”); bez imienia, gdy nie padło.
- update_participant: zmiana karty (ref = name z listy). Wypełnij WYŁĄCZNIE pola, które polecenie zmienia.
- clear_participant_field: usunięcie jednej wartości (np. limitu) — tylko na wyraźną prośbę.
- remove_participant: usunięcie osoby — tylko przy jednoznacznym poleceniu („usuń”, „nie będzie X”).
- set_participant_count: łączna liczba osób („we czwórkę” -> 4).
- confirm_start: użytkownik zatwierdza proponowany start (pole start_proposal).
- update_criteria: alpha. „Żeby nikt nie jechał długo”, „sprawiedliwie”, „równo” -> 0.8.
  „Jak najszybciej”, „najkrótszy łączny/średni czas” -> 0.2.

ZASADY
- Karta z "pusta": true to wolne miejsce („Osoba N”). Gdy polecenie opisuje osobę spoza listy
  (np. „Ola jedzie rowerem”), a jest pusta karta, użyj update_participant na pierwszej pustej
  karcie i nadaj name. Gdy pustych kart brak — add_participant.
- „Dodaj X” = ZAWSZE add_participant (nowa karta), nawet gdy są puste karty.
- Osoba o tym imieniu już jest na liście -> nie dodawaj jej drugi raz, napisz to w reply.
- Mniejsza liczba osób („we trójkę”) -> tylko set_participant_count. Nigdy sam nie wybieraj,
  kogo usunąć — system zapyta użytkownika.
- Osoba pisząca o sobie („jadę”, „idę”, „ja”) to karta „Ja”: zaktualizuj ją albo utwórz (name „Ja”).
- transport: walk / bike / car tylko, gdy padł wprost. Tramwaj, metro, autobus = brak wsparcia:
  nie ustawiaj transportu, napisz o tym w reply.
- Miejsce startu („z Ursynowa”, „startuje z Mokotowa”) -> pole place w mianowniku („Ursynów”).
  NIGDY nie podawaj współrzędnych. Można je łączyć z innymi polami w jednej akcji.
- „Wszyscy”, „każdy” = osobna akcja dla każdej karty.
- Negacja („nie usuwaj Oli”) = brak akcji.
- Domysły i niepewność („chyba”, „może”, „nie wiem czy”) -> nie zmieniaj nic, zadaj pytanie w question.
- Nieznana osoba albo nie wiadomo, o kogo chodzi -> pytanie w question, bez akcji.
- reply: jedno krótkie zdanie po polsku o tym, co zmieniasz.

PRZYKŁADY (karty: Ola rower; Adam auto; Osoba 3 pusta)
- „Zmień imię Oli na Aleksandra” -> update_participant(ref="Ola", name="Aleksandra") i NIC więcej
- „Ola nie ma limitu” -> clear_participant_field(ref="Ola", field="max_minutes")
- „Kasia jedzie z Ursynowa autem” -> update_participant(ref="Osoba 3", name="Kasia", transport="car", place="Ursynów")
- „Osoba, która jechała autem, idzie pieszo” -> update_participant(ref="Adam", transport="walk")
- „Jadę rowerem” -> update_participant(ref="Osoba 3", name="Ja", transport="bike")
- „Ola chyba nie da rady” -> actions=[], question="Czy usunąć Olę ze spotkania?"
- „Dodaj Pawła” -> add_participant(name="Paweł"); karta Osoba 3 zostaje pusta
- „Jadę rowerem, Ewa autem, a dwie pozostałe osoby pieszo” (brak pustych kart) -> add_participant(name="Ja",
  transport="bike"), add_participant(name="Ewa", transport="car"), add_participant(transport="walk") ×2
"""

EXPLAIN = """\
Napisz maksymalnie 2 krótkie zdania po polsku, dlaczego ZWYCIĘZCA jest najlepszy dla grupy.
Ranking ustala score = (1 − α)·średni czas + α·najdłuższy czas (niższy = lepszy); zwycięzca ma
najniższy score, nawet jeśli inne miejsce ma niższą średnią. Wymień zwycięzcę z nazwy.
Używaj WYŁĄCZNIE podanych liczb; nie wymyślaj żadnych faktów o miejscach."""


def enabled() -> bool:
    return bool(get_settings().openrouter_api_key)


def interpret(
    text: str, people: list[Participant], criteria: Criteria
) -> tuple[MeetingCommand, Literal["ai", "rules"], list[str]]:
    """Zwraca (polecenie, źródło, ostrzeżenia)."""
    if not enabled():
        return intent_rules.parse(text, people), "rules", []
    state = {
        "uczestnicy": [
            {
                "id": p.id, "name": p.name, "transport": p.transport, "max_minutes": p.max_minutes,
                "start": "ustawiony" if p.start else None,
                "start_proposal": p.start_proposal.label if p.start_proposal else None,
                "pusta": people_service.is_empty(p),
            }
            for p in people
        ],
        "alpha": criteria.alpha,
    }
    prompt = f"Stan spotkania:\n{json.dumps(state, ensure_ascii=False)}\n\nPolecenie:\n{text}"
    try:
        return _agent(MeetingCommand, INSTRUCTIONS).run_sync(prompt).output, "ai", []
    except Exception as exc:  # aplikacja ma działać dalej, ale powód musi być widoczny
        reason = describe_error(exc)
        log.warning("OpenRouter (%s): %s", get_settings().openrouter_model, reason)
        return intent_rules.parse(text, people), "rules", [f"AI niedostępne: {reason}. Użyto parsera reguł."]


def explain(result: Result, people: list[Participant]) -> str | None:
    """Komentarz AI do wyniku; None, gdy AI nie jest skonfigurowane lub zawiodło."""
    if not enabled() or not result.recommendations:
        return None
    names = {p.id: p.name for p in people}
    winner = result.recommendations[0].place.name
    lines = [
        f"{'ZWYCIĘZCA' if i == 0 else f'Miejsce {i + 1}'}: {r.place.name} — score {r.score}, "
        f"średnio {r.mean_min} min, najdłużej {r.max_min} min; "
        + ", ".join(f"{names.get(pid, pid)} {m} min" for pid, m in r.times_min.items())
        for i, r in enumerate(result.recommendations)
    ]
    prompt = f"α = {result.alpha:.2f}\n" + "\n".join(lines)
    try:
        comment = _agent(str, EXPLAIN).run_sync(prompt).output.strip()[:400]
    except Exception as exc:
        log.warning("OpenRouter (explain): %s", describe_error(exc))
        return None
    # Zabezpieczenie: komentarz, który nie mówi o faktycznym zwycięzcy, wprowadzałby w błąd.
    if winner.lower() not in comment.lower():
        log.warning("Komentarz AI pominięty — nie wskazuje zwycięzcy %r", winner)
        return None
    return comment


def describe_error(exc: Exception) -> str:
    """Zrozumiały powód awarii — bez treści klucza."""
    from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior

    if isinstance(exc, ModelHTTPError):
        return {
            401: "OpenRouter odrzucił klucz (401)",
            402: "brak środków na koncie OpenRouter (402)",
            403: "limit klucza OpenRouter wyczerpany lub model niedostępny (403)",
            404: f"model {get_settings().openrouter_model} nie istnieje (404)",
            429: "model chwilowo przeciążony (429)",
        }.get(exc.status_code, f"błąd OpenRouter ({exc.status_code})")
    if isinstance(exc, UnexpectedModelBehavior):
        return "model zwrócił odpowiedź niezgodną ze schematem"
    if exc.__class__.__name__ == "UserError":
        return f"błędna konfiguracja modelu ({exc})"
    if "timeout" in exc.__class__.__name__.lower():
        return "przekroczony czas odpowiedzi"
    return f"{exc.__class__.__name__}"


def _agent(output_type, instructions: str):
    from pydantic_ai import Agent

    return Agent(
        _model(), output_type=output_type, instructions=instructions, retries=2,
        model_settings={"timeout": 40, "temperature": 0},
    )


def _model():
    """Model OpenRouter. Testy podmieniają tę funkcję na FunctionModel z PydanticAI."""
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openrouter import OpenRouterProvider

    settings = get_settings()
    return OpenAIChatModel(settings.openrouter_model, provider=OpenRouterProvider(api_key=settings.openrouter_api_key))
