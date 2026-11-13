"""Jedna tabela: spotkanie. Uczestnicy, kryteria i analiza to kolumny JSON.

Dlaczego JSON, a nie osobne tabele? Uczestnicy nie istnieją poza spotkaniem,
zawsze czytamy i zapisujemy ich razem — osobna tabela dodałaby tylko joiny.
Strukturę pilnują schematy Pydantic (app/schemas).
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _now() -> datetime:
    return datetime.now(UTC)


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    participants: Mapped[list] = mapped_column(JSON, default=list)
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    last_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
