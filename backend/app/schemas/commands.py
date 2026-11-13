"""Polecenia zmieniające spotkanie — wspólny język AI i ręcznej edycji kart.

Każda zmiana uczestników (z czatu albo z karty) to lista akcji wykonywana przez
ten sam deterministyczny executor: services/people.apply_actions.

Semantyka PATCH: pole pominięte (None) = bez zmian. Wyczyszczenie wartości to
odrębna akcja `clear_participant_field` (jedno pole). Osobna akcja zamiast listy
w `update_participant`, bo modele potrafiły „na wszelki wypadek” wypełniać taką
listę wszystkimi polami i kasowały dane. AI nie ma akcji ani pól ze współrzędnymi — lokalizację
opisuje słowami (`place`), a backend zamienia ją w propozycję do zatwierdzenia.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.meeting import MAX_PARTICIPANTS, MeetingOut, Point, Transport

Clearable = Literal["transport", "max_minutes", "start", "start_proposal"]


class _Fields(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=40, description="Imię w mianowniku")
    transport: Transport | None = Field(None, description="Tylko jeśli podano wprost")
    max_minutes: int | None = Field(None, ge=5, le=240, description="Limit czasu dojazdu")
    place: str | None = Field(None, max_length=80, description="Słowny opis miejsca startu, np. „Mokotów”")


class AddParticipant(_Fields):
    type: Literal["add_participant"] = "add_participant"


class UpdateParticipant(_Fields):
    type: Literal["update_participant"] = "update_participant"
    ref: str = Field(description="Imię uczestnika dokładnie jak na liście (lub jego id)")


class ClearParticipantField(BaseModel):
    """Usuwa JEDNĄ wartość, np. limit czasu — tylko na wyraźną prośbę."""

    type: Literal["clear_participant_field"] = "clear_participant_field"
    ref: str = Field(description="Imię uczestnika dokładnie jak na liście (lub jego id)")
    field: Clearable


class RemoveParticipant(BaseModel):
    type: Literal["remove_participant"] = "remove_participant"
    ref: str = Field(description="Imię uczestnika dokładnie jak na liście (lub jego id)")


class SetParticipantCount(BaseModel):
    type: Literal["set_participant_count"] = "set_participant_count"
    count: int = Field(ge=1, le=50)


class ConfirmStart(BaseModel):
    """Zatwierdza `start_proposal` jako punkt startu."""

    type: Literal["confirm_start"] = "confirm_start"
    ref: str = Field(description="Imię uczestnika dokładnie jak na liście (lub jego id)")


class UpdateCriteria(BaseModel):
    type: Literal["update_criteria"] = "update_criteria"
    alpha: float = Field(ge=0, le=1, description="0 = szybkość, 1 = sprawiedliwość")


class SetStart(BaseModel):
    """Tylko ręcznie (kliknięcie / przeciągnięcie na mapie) — niedostępne dla AI."""

    type: Literal["set_start"] = "set_start"
    ref: str
    point: Point


AiAction = Annotated[
    AddParticipant | UpdateParticipant | ClearParticipantField | RemoveParticipant | SetParticipantCount
    | ConfirmStart | UpdateCriteria,
    Field(discriminator="type"),
]
Action = Annotated[
    AddParticipant | UpdateParticipant | ClearParticipantField | RemoveParticipant | SetParticipantCount
    | ConfirmStart | UpdateCriteria | SetStart,
    Field(discriminator="type"),
]


class MeetingCommand(BaseModel):
    """Wynik agenta AI (i parsera reguł)."""

    actions: list[AiAction] = Field(default_factory=list)
    question: str | None = Field(None, description="Pytanie, gdy polecenie jest niejednoznaczne")
    reply: str = Field("", max_length=300, description="Krótka odpowiedź po polsku")

    @field_validator("question")
    @classmethod
    def _empty_question(cls, value: str | None) -> str | None:
        # Niektóre modele zwracają "none"/"null" zamiast pustej wartości.
        return None if value is None or value.strip().lower() in {"", "none", "null", "brak"} else value


class MeetingUpdate(BaseModel):
    """PATCH /meetings/{id}: tytuł i/lub lista akcji (wykonywana atomowo)."""

    title: str | None = Field(None, min_length=1, max_length=120)
    actions: list[Action] = Field(default_factory=list, max_length=4 * MAX_PARTICIPANTS)


class InterpretRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class InterpretOut(BaseModel):
    meeting: MeetingOut
    reply: str
    applied: list[str]  # co faktycznie zapisano, np. „Dodano: Paweł”
    question: str | None  # gdy trzeba doprecyzować — nic nie zostało zmienione
    warnings: list[str]
    source: Literal["ai", "rules"]
