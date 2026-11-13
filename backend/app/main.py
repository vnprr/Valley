"""Punkt wejścia FastAPI: CORS, obsługa błędów domenowych, tabele, dane demo."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import meetings
from app.services.errors import CommandError, ExternalServiceError, IncompleteError, NotFoundError
from app.services.meetings import seed_demo

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)  # MVP: bez Alembica, jedna tabela
    if get_settings().seed_demo:
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(title="Common Ground API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(meetings.router)


@app.exception_handler(NotFoundError)
def _not_found(_: Request, exc: NotFoundError):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(IncompleteError)
def _incomplete(_: Request, exc: IncompleteError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "problems": exc.problems})


@app.exception_handler(CommandError)
def _command(_: Request, exc: CommandError):
    return JSONResponse(status_code=422, content={"detail": str(exc), "problems": [str(exc)]})


@app.exception_handler(ExternalServiceError)
def _external(_: Request, exc: ExternalServiceError):
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "routing": "geoapify" if s.geoapify_api_key else "osrm",
        "ai": "openrouter" if s.openrouter_api_key else "rules",
        "model": s.openrouter_model if s.openrouter_api_key else None,
    }


# Zbudowany frontend (npm run build) serwowany z tego samego adresu — jedna komenda do demo.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
