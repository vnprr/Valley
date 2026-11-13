"""Ranking miejsc na podstawie macierzy czasów. Czysta matematyka, bez I/O.

    score(p) = (1 - α) · średni_czas(p) + α · najdłuższy_czas(p)

α = 0 -> wygrywa miejsce najszybsze „w sumie”,
α = 1 -> wygrywa miejsce, w którym najbardziej poszkodowana osoba jedzie najkrócej.
"""

import math

from app.schemas.analysis import Place, PlaceScore

TOP_N = 3
MIN_GAP_KM = 0.4  # rekomendacje mają być realnymi alternatywami, nie trzema lokalami z jednej ulicy


def score_places(
    places: list[Place],
    times_s: list[list[float | None]],
    participant_ids: list[str],
    names: dict[str, str],
    limits_min: dict[str, int | None],
    alpha: float,
) -> list[PlaceScore]:
    """Ocenia każde miejsce; zwraca listę posortowaną: najpierw wykonalne wg score."""
    scored = []
    for j, place in enumerate(places):
        minutes = {
            pid: None if times_s[i][j] is None else round(times_s[i][j] / 60, 1)
            for i, pid in enumerate(participant_ids)
        }
        scored.append(_score_one(place, minutes, names, limits_min, alpha))

    # Wykonalne rosnąco po score; niewykonalne na końcu.
    return sorted(scored, key=lambda s: (not s.feasible, s.score if s.score is not None else 1e9))


def _score_one(place, minutes, names, limits_min, alpha) -> PlaceScore:
    # 1) Brak trasy = miejsce niedostępne (nie zgadujemy czasu z linii prostej).
    unreachable = [names.get(pid, pid) for pid, m in minutes.items() if m is None]
    if unreachable:
        return PlaceScore(
            place=place, times_min=minutes, mean_min=None, max_min=None, score=None,
            feasible=False, reason="brak trasy: " + ", ".join(unreachable),
        )

    values = list(minutes.values())
    mean, worst = sum(values) / len(values), max(values)
    score = (1 - alpha) * mean + alpha * worst

    # 2) Twarde limity czasu uczestników odrzucają kandydata.
    over = [
        names.get(pid, pid)
        for pid, m in minutes.items()
        if limits_min.get(pid) is not None and m > limits_min[pid]
    ]
    return PlaceScore(
        place=place, times_min=minutes,
        mean_min=round(mean, 1), max_min=round(worst, 1), score=round(score, 2),
        feasible=not over, reason=("przekroczony limit: " + ", ".join(over)) if over else None,
    )


def top(scored: list[PlaceScore], n: int = TOP_N) -> list[PlaceScore]:
    """Najlepsze wykonalne miejsca oddalone od siebie o ≥ 400 m.
    Gdy takich zabraknie, uzupełniamy kolejnymi wg score."""
    feasible = [s for s in scored if s.feasible]
    picked: list[PlaceScore] = []
    for s in feasible:
        if len(picked) < n and all(_km(s.place, p.place) >= MIN_GAP_KM for p in picked):
            picked.append(s)
    for s in feasible:
        if len(picked) >= n:
            break
        if s not in picked:
            picked.append(s)
    return sorted(picked, key=lambda s: s.score)


def _km(a: Place, b: Place) -> float:
    kx = 111.32 * math.cos(math.radians((a.lat + b.lat) / 2))
    return math.hypot((a.lon - b.lon) * kx, (a.lat - b.lat) * 110.57)


def summarize(recs: list[PlaceScore], names: dict[str, str], alpha: float, checked: int = 0) -> str:
    """Krótkie, w 100% oparte na liczbach wyjaśnienie zwycięzcy."""
    if not recs:
        return f"Żadne z {checked} sprawdzonych miejsc nie spełnia limitów czasu wszystkich osób."
    best = recs[0]
    worst_pid = max(best.times_min, key=lambda pid: best.times_min[pid])
    focus = "szybkość" if alpha < 0.34 else "sprawiedliwość" if alpha > 0.66 else "balans"
    return (
        f"{best.place.name}: średnio {best.mean_min:.0f} min, najdłużej "
        f"{best.max_min:.0f} min ({names.get(worst_pid, worst_pid)}). Priorytet: {focus}. "
        f"Najlepsze z {checked} sprawdzonych kawiarni (nie z wszystkich w mieście)."
    )
