"""Wejście funkcji Vercel: ten sam FastAPI co lokalnie (backend/app), bez zmian w logice.

Zmiany tylko środowiskowe: backend dokładamy do sys.path, a SQLite ląduje w /tmp
(jedyny zapisywalny katalog funkcji). Baza jest więc efemeryczna — po recyklingu
instancji wraca spotkanie demo. Do trwałego wdrożenia ustaw DATABASE_URL na Postgresa.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/common_ground.db")

from app.main import app  # noqa: E402,F401
