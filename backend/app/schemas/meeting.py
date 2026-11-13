"""Schematy spotkania i karty uczestnika (walidacja wejścia i kształt odpowiedzi)."""

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.schemas.analysis import Result

Transport = Literal["walk", "bike", "car"]

MIN_PARTICIPANTS = 2
MAX_PARTICIPANTS = 6

# Obszar demonstracyjny: Warszawa (lon_min, lat_min, lon_max, lat_max).
AREA = (20.88, 52.15, 21.15, 52.32)


class Point(BaseModel):
    lat: float = Field(ge=AREA[1], le=AREA[3])
    lon: float = Field(ge=AREA[0], le=AREA[2])


class StartProposal(Point):
    """Punkt znaleziony przez geokoder dla opisu słownego („z Mokotowa”).
    Staje się startem dopiero po zatwierdzeniu przez użytkownika."""

    label: str = Field(max_length=160)


class Participant(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])  # stabilne, niezależne od imienia
    name: str = Field(min_length=1, max_length=40)
    color: str | None = None  # nadawany przez serwis
    transport: Transport | None = None
    start: Point | None = None
    start_proposal: StartProposal | None = None
    max_minutes: int | None = Field(None, ge=5, le=240)


class Criteria(BaseModel):
    # 0 = liczy się tylko średni czas (szybkość), 1 = tylko najdłuższy (sprawiedliwość).
    alpha: float = Field(0.5, ge=0, le=1)


class MeetingCreate(BaseModel):
    title: str = Field("Nowe spotkanie", min_length=1, max_length=120)


class MeetingSummary(BaseModel):
    id: int
    title: str
    participant_count: int
    has_analysis: bool
    updated_at: datetime


class MeetingOut(BaseModel):
    id: int
    title: str
    participants: list[Participant]
    criteria: Criteria
    result: Result | None  # wyliczany przy odczycie z zapisanej macierzy czasów
    created_at: datetime
    updated_at: datetime
