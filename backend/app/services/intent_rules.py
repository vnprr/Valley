"""Parser reguł — tryb BEZ AI (brak klucza lub awaria OpenRouter).

Zwraca ten sam MeetingCommand co agent, więc wykonuje go ten sam executor.
Rozumie krótkie, typowe polecenia:
  „we czwórkę”, „4 osoby”, „dodaj Olę i Pawła”, „usuń Adama i dodaj Kasię”,
  „Ola jedzie rowerem”, „zmień Oli transport na auto i limit na 25 minut”,
  „zmień imię Oli na Aleksandra”, „Ola startuje z Mokotowa”, „nie usuwaj Oli”.
Nie rozumie złożonych zdań ani kontekstu — od tego jest LLM.
"""

import re

from app.schemas.commands import (
    AddParticipant,
    ClearParticipantField,
    MeetingCommand,
    RemoveParticipant,
    SetParticipantCount,
    UpdateCriteria,
    UpdateParticipant,
)
from app.schemas.meeting import Participant
from app.services.people import PLACEHOLDER, stem

COUNT_WORDS = {
    "dwie": 2, "dwa": 2, "dwóch": 2, "dwoje": 2, "dwójkę": 2,
    "trzy": 3, "trzech": 3, "troje": 3, "trójkę": 3,
    "cztery": 4, "czterech": 4, "czworo": 4, "czwórkę": 4,
    "pięć": 5, "pięciu": 5, "pięcioro": 5, "piątkę": 5,
    "sześć": 6, "sześciu": 6, "sześcioro": 6, "szóstkę": 6,
}
NUM = r"(\d+|" + "|".join(COUNT_WORDS) + ")"
TRANSPORT = [  # kolejność ma znaczenie
    ("bike", r"rower"),
    ("car", r"samoch[oó]d|\baut(o|em)\b"),
    ("walk", r"piesz|piechot|spacer|\b(id(ę|zie|ą|ziemy)|pójd(ę|zie|ą|ziemy))\b"),
]
NAME = r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+"
STOP = {
    "ja", "my", "we", "w", "na", "a", "i", "oraz", "nie", "jednak", "też", "osoba", "osoby", "osób",
    "dodaj", "dopisz", "usuń", "wyrzuć", "skreśl", "zmień", "ustaw", "jadę", "idę", "jedzie", "idzie",
    "pójdzie", "startuje", "jestem", "mam", "będzie", "będą", "spotkanie", "kawa", "kawę", "limit",
    "max", "maks", "maksymalnie", "najwyżej", "pozostałe", "pozostali", "reszta", "transport", "imię",
}
# Imiona w mianowniku — pozwalają zamienić „Pawła” na „Paweł” przy dodawaniu.
NAMES = (
    "Ola Aleksandra Ala Anna Ania Asia Joanna Basia Barbara Kasia Katarzyna Ewa Magda Magdalena "
    "Marta Zosia Zofia Julia Maja Gosia Małgorzata Agnieszka Monika Natalia Karolina Ula Iza Ida "
    "Paweł Adam Piotr Marek Tomek Tomasz Michał Kuba Jakub Jan Janek Krzysiek Krzysztof Bartek "
    "Kamil Łukasz Mateusz Wojtek Wojciech Igor Filip Antek Antoni Szymon Olek Aleksander Maciek Ja"
).split()
# Dzielnice: dopełniacz („z Mokotowa”) -> mianownik dla geokodera.
DISTRICTS = {
    "mokotowa": "Mokotów", "woli": "Wola", "pragi": "Praga", "żoliborza": "Żoliborz",
    "ochoty": "Ochota", "ursynowa": "Ursynów", "bemowa": "Bemowo", "bielan": "Bielany",
    "śródmieścia": "Śródmieście", "targówka": "Targówek", "wilanowa": "Wilanów",
    "białołęki": "Białołęka", "wawra": "Wawer", "włoch": "Włochy", "ursusa": "Ursus",
    "rembertowa": "Rembertów", "wesołej": "Wesoła", "centrum": "Centrum",
}
VERBS = {"add": r"\b(dodaj|dopisz|dołącz)", "remove": r"\b(usuń|wyrzuć|skreśl)"}


def parse(text: str, people: list[Participant]) -> MeetingCommand:
    low = text.lower()
    command = MeetingCommand()

    count = _group_size(low)
    if count:
        command.actions.append(SetParticipantCount(count=count))
    if re.search(r"sprawiedliw", low):
        command.actions.append(UpdateCriteria(alpha=0.8))
    elif re.search(r"najszybciej|jak najkrócej", low):
        command.actions.append(UpdateCriteria(alpha=0.2))

    free = [p for p in people if PLACEHOLDER.match(p.name) and not p.transport]  # karty do „zajęcia”
    verb: str | None = None  # czasownik przechodzi na kolejne człony: „dodaj Olę i Pawła”
    target: str | None = None  # ostatnio wskazana osoba: „…na auto i limit na 25 minut”
    for clause in re.split(r"[,;.]|\s+(?:a|i|oraz)\s+", text):
        low_clause = clause.lower().strip()
        if not low_clause:
            continue
        if re.match(r"^(nie|bez)\b(?!.*limit)", low_clause):  # „nie usuwaj Oli” -> brak operacji
            verb = target = None
            continue
        verb = next((v for v, pattern in VERBS.items() if re.search(pattern, low_clause)), verb)
        names = _names(clause)

        if rename := re.search(r"imi\w*\s+(" + NAME + r")\s+na\s+(" + NAME + ")", clause):
            command.actions.append(UpdateParticipant(ref=rename.group(1), name=rename.group(2)))
            verb = None
            continue
        if verb == "remove" and names:
            command.actions += [RemoveParticipant(ref=n) for n in names]
            continue

        if re.search(r"\b(bez|nie ma|usuń)\s+limit", low_clause) and (names or target):
            command.actions.append(ClearParticipantField(ref=names[0] if names else target, field="max_minutes"))
            continue
        fields = _fields(clause)
        if verb == "add" and names:
            command.actions += [AddParticipant(name=nominative(n), **fields) for n in names]
            continue
        verb = None

        # „dwie pozostałe osoby idą pieszo” — karty bez imion
        group = re.search(NUM + r"\s+(?:\w+\s+)?(os[oó]b|osoby)", low_clause)
        if group and re.search(r"pozosta|inn[ei]|reszt", low_clause) and fields:
            for _ in range(_number(group.group(1))):
                card = free.pop(0) if free else None
                command.actions.append(UpdateParticipant(ref=card.id, **fields) if card else AddParticipant(**fields))
            continue

        if re.search(r"\b(ja|jadę|idę|pójdę|jestem)\b", low_clause):
            names.insert(0, "Ja")
        if not fields:
            continue
        if not names and target:
            command.actions.append(UpdateParticipant(ref=target, **fields))
            continue
        for name in names:
            target = name
            if any(stem(p.name) == stem(name) for p in people):
                command.actions.append(UpdateParticipant(ref=name, **fields))
            elif free:  # nowe imię zajmuje pierwszą wolną kartę „Osoba N”
                card = free.pop(0)
                target = card.id
                command.actions.append(UpdateParticipant(ref=card.id, name=nominative(name), **fields))
            else:
                command.actions.append(AddParticipant(name=nominative(name), **fields))

    command.reply = (
        "Tryb bez AI (parser reguł) — przygotowano zmiany."
        if command.actions else
        "Tryb bez AI nie rozpoznał polecenia. Spróbuj np. „dodaj Pawła” albo edytuj kartę ręcznie."
    )
    return command


def nominative(word: str) -> str:
    """„Pawła” -> „Paweł”, „Olę” -> „Ola” (słownik), inaczej proste reguły."""
    known = next((n for n in NAMES if stem(n) == stem(word)), None)
    if known:
        return known
    return word[:-1] + "a" if word.endswith("ę") else word


def _group_size(low: str) -> int | None:
    m = re.search(r"\bwe?\s+(dwójkę|dwoje|troje|trójkę|czwórkę|czworo|piątkę|pięcioro|szóstkę|sześcioro)\b", low)
    m = m or re.search(r"\b" + NUM + r"\s+(os[oó]b|osoby)", low)
    if m and not re.search(r"pozosta|inn[ei]|reszt", low[m.start(): m.end() + 20]):
        return _number(m.group(1))
    return None


def _fields(clause: str) -> dict:
    low = clause.lower()
    fields: dict = {}
    if transport := next((t for t, pattern in TRANSPORT if re.search(pattern, low)), None):
        fields["transport"] = transport
    if limit := re.search(r"(?:max|maks\w*|najwyżej|limit\w*)\s*(?:na|do)?\s*(\d+)\s*min", low):
        fields["max_minutes"] = min(max(int(limit.group(1)), 5), 240)
    if place := re.search(r"\b(?:z|ze|od)\s+(" + NAME + r"(?:\s+" + NAME + ")?)", clause):
        fields["place"] = DISTRICTS.get(place.group(1).lower(), place.group(1))
    return fields


def _names(clause: str) -> list[str]:
    place = re.search(r"\b(?:z|ze|od)\s+(" + NAME + r"(?:\s+" + NAME + ")?)", clause)
    skip = set(place.group(1).split()) if place else set()
    after_na = set(re.findall(r"\bna\s+(" + NAME + ")", clause))
    return [
        n for n in re.findall(r"\b" + NAME + r"\b", clause)
        if n.lower() not in STOP and n not in skip and n not in after_na
        and n.lower() not in COUNT_WORDS and not n.lower().endswith("my")
    ]


def _number(token: str) -> int:
    return int(token) if token.isdigit() else COUNT_WORDS[token]
