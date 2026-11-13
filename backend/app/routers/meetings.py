"""7 endpointów. Router tylko przyjmuje żądanie i woła serwis."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.commands import InterpretOut, InterpretRequest, MeetingUpdate
from app.schemas.meeting import MeetingCreate, MeetingOut, MeetingSummary
from app.services import meetings as service
from app.services.providers import Provider, get_provider

router = APIRouter(prefix="/api/meetings", tags=["meetings"])


@router.get("", response_model=list[MeetingSummary])
def list_meetings(db: Session = Depends(get_db)):
    return service.list_meetings(db)


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
def create_meeting(data: MeetingCreate, db: Session = Depends(get_db)):
    return service.create_meeting(db, data)


@router.get("/{meeting_id}", response_model=MeetingOut)
def get_meeting(meeting_id: int, db: Session = Depends(get_db)):
    return service.get_meeting(db, meeting_id)


@router.patch("/{meeting_id}", response_model=MeetingOut)
def update_meeting(meeting_id: int, data: MeetingUpdate, db: Session = Depends(get_db)):
    """Tytuł i/lub akcje na uczestnikach — te same, które wykonuje AI."""
    return service.update_meeting(db, meeting_id, data)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(meeting_id: int, db: Session = Depends(get_db)):
    service.delete_meeting(db, meeting_id)


@router.post("/{meeting_id}/interpret", response_model=InterpretOut)
def interpret(meeting_id: int, data: InterpretRequest, db: Session = Depends(get_db)):
    """Lekkie: tekst -> zaktualizowane karty. Nie odpytuje routingu."""
    return service.interpret(db, meeting_id, data.text)


@router.post("/{meeting_id}/solve", response_model=MeetingOut)
def solve(
    meeting_id: int, db: Session = Depends(get_db), provider: Provider = Depends(get_provider)
):
    """Kosztowne: kawiarnie + macierz czasów + ranking (z cache, gdy nic się nie zmieniło)."""
    return service.solve_meeting(db, meeting_id, provider)
