"""Logika spotkań: CRUD, polecenia (AI i ręczne) oraz obliczenia.

Wzorzec: router -> TEN serwis -> repository -> SQLAlchemy.
Każda zmiana uczestników przechodzi przez people.apply_actions — jedno źródło prawdy.
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.meeting import Meeting
from app.repositories import meeting as repo
from app.schemas.analysis import Analysis
from app.schemas.commands import Action, InterpretOut, MeetingUpdate
from app.schemas.meeting import Criteria, MeetingCreate, MeetingOut, MeetingSummary, Participant
from app.services import agent, geocode, people, solve
from app.services.errors import CommandError, IncompleteError, NotFoundError
from app.services.providers import Provider

DEMO_FILE = Path(__file__).resolve().parent.parent / "data" / "demo_meeting.json"


# ---------- CRUD ----------

def list_meetings(db: Session) -> list[MeetingSummary]:
    return [
        MeetingSummary(
            id=m.id, title=m.title, participant_count=len(m.participants),
            has_analysis=m.last_analysis is not None, updated_at=m.updated_at,
        )
        for m in repo.list_all(db)
    ]


def create_meeting(db: Session, data: MeetingCreate) -> MeetingOut:
    meeting = repo.create(db, title=data.title, participants=[], criteria=Criteria().model_dump(), last_analysis=None)
    return to_out(meeting)


def get_meeting(db: Session, meeting_id: int) -> MeetingOut:
    return to_out(_load(db, meeting_id))


def update_meeting(db: Session, meeting_id: int, data: MeetingUpdate) -> MeetingOut:
    """Ręczna edycja: tytuł i/lub akcje (te same co z AI). Błąd -> 422, nic nie zapisane."""
    meeting = _load(db, meeting_id)
    fields: dict = {}
    if data.title is not None:
        fields["title"] = data.title
    if data.actions:
        fields.update(_run(meeting, data.actions)[0])
    # Analizy nie kasujemy: build_result() oznaczy ją jako nieaktualną (stale),
    # gdy zmieni się start lub transport — UI pokaże wtedy „Przelicz”.
    return to_out(repo.update(db, meeting, **fields))


def delete_meeting(db: Session, meeting_id: int) -> None:
    repo.delete(db, _load(db, meeting_id))


# ---------- polecenie tekstowe ----------

def interpret(db: Session, meeting_id: int, text: str) -> InterpretOut:
    meeting = _load(db, meeting_id)
    command, source, warnings = agent.interpret(text, _participants(meeting), Criteria(**meeting.criteria))

    applied: list[str] = []
    question = command.question
    reply = command.reply or "Gotowe."
    if command.actions:
        try:
            fields, applied, more = _run(meeting, command.actions)
            warnings += more
            meeting = repo.update(db, meeting, **fields)
        except CommandError as exc:  # całe polecenie odrzucone — baza bez zmian
            reply = str(exc)
            question = str(exc) if exc.needs_answer else question
    elif not question:
        reply = command.reply or "Nic nie zmieniam."

    return InterpretOut(
        meeting=to_out(meeting), reply=reply, applied=applied,
        question=question, warnings=warnings, source=source,
    )


def _run(meeting: Meeting, actions: list[Action]) -> tuple[dict, list[str], list[str]]:
    """Wykonuje akcje na kopii stanu i zwraca pola do zapisania (wszystko albo nic)."""
    new_people, criteria, applied, warnings = people.apply_actions(
        _participants(meeting), Criteria(**meeting.criteria), actions, geocode.search
    )
    fields = {"participants": [p.model_dump(mode="json") for p in new_people], "criteria": criteria.model_dump()}
    return fields, applied, warnings


# ---------- obliczenia ----------

def solve_meeting(db: Session, meeting_id: int, provider: Provider) -> MeetingOut:
    meeting = _load(db, meeting_id)
    participants = _participants(meeting)
    problems = solve.readiness_problems(participants)
    if problems:
        raise IncompleteError(problems)

    alpha = Criteria(**meeting.criteria).alpha
    stored = Analysis(**meeting.last_analysis) if meeting.last_analysis else None
    fresh = stored is not None and stored.provider == provider.name and stored.fingerprint == solve.fingerprint(participants)
    analysis = stored if fresh else solve.compute_analysis(participants, provider, alpha, previous=stored)

    # Komentarz AI odświeżamy tylko przy nowej analizie albo innym α.
    if not fresh or (agent.enabled() and analysis.comment_alpha != alpha):
        result = solve.build_result(analysis, participants, alpha)
        analysis.comment = agent.explain(result, participants)
        analysis.comment_alpha = alpha if analysis.comment else None
        meeting = repo.update(db, meeting, last_analysis=analysis.model_dump(mode="json"))
    return to_out(meeting)


# ---------- demo ----------

def seed_demo(db: Session) -> None:
    """Pusta baza + nagrany plik -> spotkanie demo działające bez sieci."""
    if repo.count(db) == 0 and DEMO_FILE.exists():
        repo.create(db, **json.loads(DEMO_FILE.read_text("utf-8")))


# ---------- pomocnicze ----------

def to_out(meeting: Meeting) -> MeetingOut:
    participants = _participants(meeting)
    criteria = Criteria(**meeting.criteria)
    result = None
    if meeting.last_analysis:
        result = solve.build_result(Analysis(**meeting.last_analysis), participants, criteria.alpha)
    return MeetingOut(
        id=meeting.id, title=meeting.title, participants=participants, criteria=criteria,
        result=result, created_at=meeting.created_at, updated_at=meeting.updated_at,
    )


def _load(db: Session, meeting_id: int) -> Meeting:
    meeting = repo.get(db, meeting_id)
    if meeting is None:
        raise NotFoundError(f"Spotkanie {meeting_id} nie istnieje.")
    return meeting


def _participants(meeting: Meeting) -> list[Participant]:
    return [Participant(**p) for p in meeting.participants]
