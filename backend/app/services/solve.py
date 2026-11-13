"""Analiza spotkania: pula kawiarni -> preselekcja -> macierz czasów -> wynik.

    compute_analysis()  — DROGIE: odpytuje dostawcę (pula + brakujące czasy tras)
    build_result()      — TANIE: ranking i dolina z zapisanej macierzy

Oszczędność: dokładne czasy pobieramy tylko dla `max_candidates` kawiarni (domyślnie 32),
a nie dla całej puli. Preselekcja jest bezpłatna (geometria), ranking — wyłącznie z tras.
"""

import hashlib
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from app.config import get_settings
from app.schemas.analysis import Analysis, Place, Result, RouteRow, Usage
from app.schemas.meeting import AREA, MAX_PARTICIPANTS, MIN_PARTICIPANTS, Participant
from app.services import optimizer
from app.services.errors import IncompleteError
from app.services.providers import Provider, Rect
from app.services.surface import build_surface

GRID = 4  # różnorodność: najlepszy kandydat z każdej z 4 × 4 części obszaru

# Tylko do PRESELEKCJI (wybór, kogo zapytać o trasy). Nigdy nie pokazujemy tych liczb jako czasów.
SPEED_KMH = {"walk": 4.8, "bike": 15.0, "car": 22.0}
DETOUR = 1.35  # drogi są dłuższe niż linia prosta
KNOWN_BONUS = 0.85  # miejsca sprawdzone wcześniej mają lekką przewagę -> mniej nowych zapytań


def readiness_problems(participants: list[Participant]) -> list[str]:
    problems = []
    if not MIN_PARTICIPANTS <= len(participants) <= MAX_PARTICIPANTS:
        problems.append(f"Potrzeba od {MIN_PARTICIPANTS} do {MAX_PARTICIPANTS} osób.")
    for p in participants:
        if p.start is None:
            problems.append(f"{p.name}: " + ("zatwierdź proponowany start." if p.start_proposal else "wybierz punkt startowy na mapie."))
        if p.transport is None:
            problems.append(f"{p.name}: wybierz środek transportu.")
    return problems


def fingerprint(participants: list[Participant]) -> str:
    """Zmienia się, gdy zmieni się skład, start lub transport -> wynik nieaktualny.
    Imię, kolor i limit czasu NIE wpływają na trasy, więc ich tu nie ma."""
    return hashlib.sha1(json.dumps([[p.id, row_key("", p)] for p in participants]).encode()).hexdigest()[:16]


def row_key(provider: str, p: Participant) -> str:
    """Klucz cache wiersza czasów: dostawca + profil transportu + punkt startu."""
    start = f"{p.start.lat:.5f},{p.start.lon:.5f}" if p.start else "-"
    return f"{provider}:{p.transport}:{start}"


def compute_analysis(
    participants: list[Participant], provider: Provider, alpha: float, previous: Analysis | None = None
) -> Analysis:
    problems = readiness_problems(participants)
    if problems:
        raise IncompleteError(problems)
    started = time.perf_counter()
    settings = get_settings()
    usage = Usage()

    rect = search_rect([(p.start.lon, p.start.lat) for p in participants])
    pool = provider.find_cafes(rect)
    usage.places_requests, usage.pool_size = 1, len(pool)
    usage.credits += provider.places_credits
    known = {pl.id for pl in previous.places} if previous else set()
    places = pick_candidates(pool, participants, alpha, settings.max_candidates, known)
    if not places:
        raise IncompleteError(["Brak kawiarni w okolicy uczestników."])

    # Cache: wiersze z poprzedniej analizy, jeśli nie są przeterminowane.
    now = datetime.now(UTC)
    ttl = timedelta(hours=settings.route_cache_ttl_hours)
    cache = {k: r for k, r in (previous.route_cache if previous else {}).items() if now - _aware(r.fetched_at) < ttl}

    # Brakujące pary: jedno zapytanie na środek transportu, wysłane równolegle.
    jobs = []
    for transport in sorted({p.transport for p in participants}):
        group = [p for p in participants if p.transport == transport]
        rows = [cache.setdefault(row_key(provider.name, p), RouteRow(fetched_at=now, times={})) for p in group]
        usage.reused_cells += sum(pl.id in row.times for row in rows for pl in places)
        needy = [(p, row) for p, row in zip(group, rows) if any(pl.id not in row.times for pl in places)]
        if needy:
            targets = [pl for pl in places if any(pl.id not in row.times for _, row in needy)]
            jobs.append((transport, needy, targets))

    with ThreadPoolExecutor(max_workers=provider.max_parallel) as pool_exec:
        futures = [pool_exec.submit(provider.travel_times, [p.start for p, _ in needy], targets, transport)
                   for transport, needy, targets in jobs]
        for (_, needy, targets), future in zip(jobs, futures, strict=True):
            matrix = future.result()
            usage.matrix_requests += 1
            usage.matrix_cells += len(needy) * len(targets)
            usage.credits += provider.credits(len(needy), len(targets))
            for (_, row), times in zip(needy, matrix, strict=True):
                row.times.update({t.id: v for t, v in zip(targets, times, strict=True)})

    keys = [row_key(provider.name, p) for p in participants]
    ids = {pl.id for pl in places}
    usage.duration_ms = round((time.perf_counter() - started) * 1000)
    return Analysis(
        provider=provider.name,
        computed_at=now,
        fingerprint=fingerprint(participants),
        participant_ids=[p.id for p in participants],
        places=places,
        times_s=[[cache[k].times.get(pl.id) for pl in places] for k in keys],
        # zostają tylko wiersze obecnych osób i obecni kandydaci — JSON nie rośnie bez końca
        route_cache={k: RouteRow(fetched_at=cache[k].fetched_at, times={i: t for i, t in cache[k].times.items() if i in ids}) for k in keys},
        usage=usage,
    )


def build_result(analysis: Analysis, participants: list[Participant], alpha: float) -> Result:
    names = {p.id: p.name for p in participants}
    limits = {p.id: p.max_minutes for p in participants}
    scored = optimizer.score_places(
        analysis.places, analysis.times_s, analysis.participant_ids, names, limits, alpha
    )
    recs = optimizer.top(scored)
    same_alpha = analysis.comment_alpha is not None and abs(analysis.comment_alpha - alpha) < 1e-6
    return Result(
        stale=analysis.fingerprint != fingerprint(participants),
        provider=analysis.provider,
        computed_at=analysis.computed_at,
        alpha=alpha,
        recommendations=recs,
        candidates=scored,
        surface=build_surface([s for s in scored if s.feasible]),
        summary=optimizer.summarize(recs, names, alpha, checked=len(scored)),
        comment=analysis.comment if same_alpha else None,
        usage=analysis.usage,
    )


def search_rect(points: list[tuple[float, float]]) -> Rect:
    """Prostokąt obejmujący starty + margines 25% (min. ~1,2 km), przycięty do obszaru."""
    xs, ys = [x for x, _ in points], [y for _, y in points]
    pad_y = max((max(ys) - min(ys)) * 0.25, 0.011)
    pad_x = max((max(xs) - min(xs)) * 0.25, 0.011 / math.cos(math.radians(52.23)))
    return (
        max(min(xs) - pad_x, AREA[0]), max(min(ys) - pad_y, AREA[1]),
        min(max(xs) + pad_x, AREA[2]), min(max(ys) + pad_y, AREA[3]),
    )


def pick_candidates(
    pool: list[Place], participants: list[Participant], alpha: float, n: int, known: set[str] = frozenset()
) -> list[Place]:
    """Bezpłatna preselekcja z puli (np. 300 kawiarni) do `n` kandydatów:

    1. różnorodność — najlepszy wg heurystyki kandydat z każdej z 16 części obszaru,
       żeby nie pominąć np. drugiego brzegu Wisły tylko dlatego, że w linii prostej jest dalej;
    2. reszta miejsc — najlepsi wg heurystyki (linia prosta × objazd / typowa prędkość).
    Miejsca już sprawdzone (`known`) mają lekką przewagę, żeby po małej zmianie
    nie pobierać tras do zupełnie nowego zestawu.
    """
    if not pool:
        return []
    estimate = {pl.id: _estimate(pl, participants, alpha) * (KNOWN_BONUS if pl.id in known else 1) for pl in pool}
    ranked = sorted(pool, key=lambda pl: estimate[pl.id])

    lon_min = min(pl.lon for pl in pool)
    lat_min = min(pl.lat for pl in pool)
    w = (max(pl.lon for pl in pool) - lon_min) / GRID or 1e-9
    h = (max(pl.lat for pl in pool) - lat_min) / GRID or 1e-9
    chosen: dict[str, Place] = {}
    seen: set[tuple[int, int]] = set()
    for pl in ranked:  # pierwszy napotkany w komórce = najlepszy w tej komórce
        cell = _cell(pl, lon_min, lat_min, w, h)
        if cell not in seen:
            seen.add(cell)
            chosen[pl.id] = pl
    for pl in ranked:
        if len(chosen) >= n:
            break
        chosen.setdefault(pl.id, pl)
    return sorted(chosen.values(), key=lambda pl: estimate[pl.id])[:n]


def _estimate(place: Place, participants: list[Participant], alpha: float) -> float:
    minutes = [
        _km(p.start.lat, p.start.lon, place.lat, place.lon) * DETOUR / SPEED_KMH[p.transport] * 60
        for p in participants
    ]
    return (1 - alpha) * sum(minutes) / len(minutes) + alpha * max(minutes)


def _cell(pl: Place, lon_min: float, lat_min: float, w: float, h: float) -> tuple[int, int]:
    return (min(int((pl.lon - lon_min) / w), GRID - 1), min(int((pl.lat - lat_min) / h), GRID - 1))


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    kx = 111.32 * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon2 - lon1) * kx, (lat2 - lat1) * 110.57)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
