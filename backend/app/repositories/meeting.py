"""Dostęp do bazy. Tylko zapytania SQLAlchemy — zero logiki biznesowej."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.meeting import Meeting


def list_all(db: Session) -> list[Meeting]:
    return list(db.scalars(select(Meeting).order_by(Meeting.updated_at.desc())))


def count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Meeting)) or 0


def get(db: Session, meeting_id: int) -> Meeting | None:
    return db.get(Meeting, meeting_id)


def create(db: Session, **fields) -> Meeting:
    meeting = Meeting(**fields)
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


def update(db: Session, meeting: Meeting, **fields) -> Meeting:
    # Kolumny JSON zawsze podmieniamy całym nowym obiektem — SQLAlchemy
    # nie wykrywa zmian „w środku” listy/słownika.
    for key, value in fields.items():
        setattr(meeting, key, value)
    db.commit()
    db.refresh(meeting)
    return meeting


def delete(db: Session, meeting: Meeting) -> None:
    db.delete(meeting)
    db.commit()
