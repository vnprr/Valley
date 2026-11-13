"""Operacje na kartach uczestników — jedyne miejsce, które je zmienia.

Ten sam executor obsługuje polecenia AI, parser reguł i ręczną edycję kart.
Działa na kopii listy: jeśli którakolwiek akcja jest niepoprawna, rzuca
CommandError i nic nie zostaje zapisane (wszystko albo nic).
"""

import re
import unicodedata
from collections.abc import Callable

from app.schemas.commands import (
    Action,
    AddParticipant,
    ClearParticipantField,
    ConfirmStart,
    RemoveParticipant,
    SetParticipantCount,
    SetStart,
    UpdateCriteria,
    UpdateParticipant,
)
from app.schemas.meeting import MAX_PARTICIPANTS, Criteria, Participant, Point, StartProposal
from app.services.errors import CommandError

PALETTE = ["#ff6a3d", "#2fe3b4", "#ffc72e", "#ff78bd", "#8fe84a", "#6cb6ff"]
PLACEHOLDER = re.compile(r"^Osoba \d+$")

Geocoder = Callable[[str], StartProposal | None]


def apply_actions(
    people: list[Participant], criteria: Criteria, actions: list[Action], geocode: Geocoder
) -> tuple[list[Participant], Criteria, list[str], list[str]]:
    """Zwraca (karty, kryteria, opis wykonanych zmian, ostrzeżenia)."""
    people = [p.model_copy(deep=True) for p in people]
    criteria = criteria.model_copy()
    done: list[str] = []
    warnings: list[str] = []

    for action in actions:
        if isinstance(action, AddParticipant):
            if len(people) >= MAX_PARTICIPANTS:
                raise CommandError(f"Limit to {MAX_PARTICIPANTS} osób — nie dodano: {action.name or 'osoba'}.")
            if action.name and _matches(people, action.name):
                raise CommandError(f"{action.name} już jest na liście.")
            person = Participant(name=action.name or placeholder_name(people))
            people.append(person)
            warnings += _patch(person, action, geocode)
            done.append(f"Dodano: {person.name}")

        elif isinstance(action, UpdateParticipant):
            person = resolve(people, action.ref)
            old_name = person.name
            if action.name and action.name.lower() != person.name.lower() and _matches(people, action.name):
                raise CommandError(f"Imię {action.name} jest już zajęte.")
            warnings += _patch(person, action, geocode)
            done.append(f"Zmieniono: {old_name}" + (f" → {person.name}" if person.name != old_name else ""))

        elif isinstance(action, ClearParticipantField):
            person = resolve(people, action.ref)
            setattr(person, action.field, None)
            done.append(f"Wyczyszczono: {person.name} ({action.field})")

        elif isinstance(action, RemoveParticipant):
            person = resolve(people, action.ref)
            people = [p for p in people if p.id != person.id]
            done.append(f"Usunięto: {person.name}")

        elif isinstance(action, SetParticipantCount):
            people = _set_count(people, action.count)
            done.append(f"Liczba osób: {len(people)}")

        elif isinstance(action, ConfirmStart):
            person = resolve(people, action.ref)
            if person.start_proposal is None:
                raise CommandError(f"{person.name} nie ma propozycji startu do zatwierdzenia.")
            person.start = Point(lat=person.start_proposal.lat, lon=person.start_proposal.lon)
            person.start_proposal = None
            done.append(f"Zatwierdzono start: {person.name}")

        elif isinstance(action, SetStart):
            person = resolve(people, action.ref)
            person.start, person.start_proposal = action.point, None
            done.append(f"Start: {person.name}")

        elif isinstance(action, UpdateCriteria):
            criteria.alpha = action.alpha
            done.append(f"α = {action.alpha:.2f}")

    return assign_colors(people), criteria, done, warnings


def _patch(person: Participant, action: AddParticipant | UpdateParticipant, geocode: Geocoder) -> list[str]:
    """Częściowa aktualizacja: zmienia tylko pola podane w akcji."""
    if action.name:
        person.name = action.name
    if action.transport:
        person.transport = action.transport
    if action.max_minutes:
        person.max_minutes = action.max_minutes
    if action.place:
        proposal = geocode(action.place)
        if proposal is None:
            return [f"Nie znalazłem miejsca „{action.place}” — wskaż start {person.name} na mapie."]
        person.start_proposal = proposal
    return []


def _set_count(people: list[Participant], count: int) -> list[Participant]:
    if count > MAX_PARTICIPANTS:
        raise CommandError(f"W MVP maksymalnie {MAX_PARTICIPANTS} osób.")
    people = list(people)
    while len(people) < count:
        people.append(Participant(name=placeholder_name(people)))
    extra = len(people) - count
    if extra > 0:
        # Bez pytania usuwamy tylko puste karty zastępcze — nigdy osoby z danymi.
        empty = [p.id for p in reversed(people) if is_empty(p)][:extra]
        if len(empty) < extra:
            names = ", ".join(p.name for p in people if not is_empty(p))
            raise CommandError(
                f"Zmniejszenie do {count} usunęłoby osoby z danymi ({names}). Kogo usunąć?",
                needs_answer=True,
            )
        people = [p for p in people if p.id not in empty]
    return people


# ---------- rozpoznawanie osób: id -> imię -> odmiana ----------

def resolve(people: list[Participant], ref: str) -> Participant:
    """Znajduje kartę po id albo imieniu (także odmienionym: „Oli”, „Pawła”).
    Przy niejednoznaczności NIE zgaduje — rzuca pytanie."""
    for p in people:
        if p.id == ref:
            return p
    found = _matches(people, ref)
    if len(found) == 1:
        return found[0]
    if found:
        raise CommandError(
            f"„{ref}” pasuje do kilku osób: {', '.join(p.name for p in found)}. O kogo chodzi?",
            needs_answer=True,
        )
    raise CommandError(f"Nie ma na liście osoby „{ref}”.", needs_answer=True)


def _matches(people: list[Participant], ref: str) -> list[Participant]:
    key = _normalize(ref)
    exact = [p for p in people if _normalize(p.name) == key]
    by_stem = [p for p in people if stem(p.name) == stem(ref)]
    # Dokładne trafienie wygrywa tylko, gdy nikt inny nie ma tego samego rdzenia
    # (np. „Jana” przy osobach „Jan” i „Jana” jest niejednoznaczne).
    return exact if exact and len(by_stem) <= len(exact) else by_stem


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.strip().lower().replace("ł", "l"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    m = re.match(r"osob\w*\s*(?:nr\s*)?(\d+)$", text)  # „osobę 3” -> „osoba 3”
    return f"osoba {m.group(1)}" if m else text


def stem(name: str) -> str:
    """Prosty rdzeń polskiego imienia: Ola/Oli/Olę/Olą -> „ol”, Paweł/Pawła/Pawłem -> „pawl”."""
    word = _normalize(name)
    if word.startswith("osoba "):
        return word
    word = re.sub(r"(owi|ami|ach|em|om|ie|ia|ii|i|y|a|e|u|o)$", "", word)
    # ruchome „e”: Marek/Marka, Paweł/Pawła (tylko dłuższe rdzenie, żeby „Ewa” nie stała się „w”)
    return re.sub(r"e(?=[^aeiouy]$)", "", word) if len(word) > 3 else word


# ---------- pomocnicze ----------

def is_empty(p: Participant) -> bool:
    return bool(PLACEHOLDER.match(p.name)) and not (p.start or p.start_proposal or p.transport or p.max_minutes)


def placeholder_name(people: list[Participant]) -> str:
    n = len(people) + 1
    while any(p.name == f"Osoba {n}" for p in people):
        n += 1
    return f"Osoba {n}"


def assign_colors(people: list[Participant]) -> list[Participant]:
    """Każdy uczestnik ma inny kolor z palety; istniejące kolory się nie zmieniają."""
    used: set[str] = set()
    for p in people:
        if p.color in PALETTE and p.color not in used:
            used.add(p.color)
        else:
            p.color = None
    for p in people:
        if p.color is None:
            p.color = next(c for c in PALETTE if c not in used)
            used.add(p.color)
    return people
