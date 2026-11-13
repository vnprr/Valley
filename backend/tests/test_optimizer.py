from app.schemas.analysis import Place
from app.services import optimizer

# A, B daleko od siebie; C tuż obok A (50 m). D: brak trasy dla Oli.
PLACES = [
    Place(id="A", name="A", lat=52.20, lon=21.00), Place(id="B", name="B", lat=52.23, lon=21.03),
    Place(id="C", name="C", lat=52.2004, lon=21.0004), Place(id="D", name="D", lat=52.25, lon=21.05),
]
IDS = ["p1", "p2"]
NAMES = {"p1": "Ola", "p2": "Paweł"}
#            A        B        C        D
TIMES = [[2 * 60, 20 * 60, 3 * 60, None],      # Ola
         [40 * 60, 25 * 60, 41 * 60, 10 * 60]]  # Paweł


def scored(alpha, limits=None):
    return optimizer.score_places(PLACES, TIMES, IDS, NAMES, limits or {}, alpha)


def ids(items):
    return [s.place.id for s in items]


def test_scores_for_alpha_0_half_1():
    by_id = {s.place.id: s.score for s in scored(0.0)}
    assert by_id["A"] == 21.0 and by_id["B"] == 22.5  # średnie
    by_id = {s.place.id: s.score for s in scored(0.5)}
    assert by_id["A"] == 30.5 and by_id["B"] == 23.75  # 0.5·średnia + 0.5·max
    by_id = {s.place.id: s.score for s in scored(1.0)}
    assert by_id["A"] == 40.0 and by_id["B"] == 25.0  # najdłuższy czas


def test_alpha_zero_prefers_lowest_mean_and_one_prefers_fairest():
    assert ids(optimizer.top(scored(0.0)))[0] == "A"
    assert ids(optimizer.top(scored(1.0)))[0] == "B"


def test_top_skips_near_duplicates():
    # C ma drugi najlepszy score przy α=0, ale leży 50 m od A — nie jest prawdziwą alternatywą
    assert ids(optimizer.top(scored(0.0), n=2)) == ["A", "B"]


def test_top_fills_up_when_no_distant_alternatives():
    assert len(optimizer.top(scored(0.0), n=3)) == 3


def test_unreachable_place_is_rejected_not_estimated():
    d = next(s for s in scored(0.5) if s.place.id == "D")
    assert not d.feasible and d.score is None and "Ola" in d.reason


def test_hard_time_limit_rejects_candidate():
    result = scored(0.0, limits={"p2": 30})
    assert ids(optimizer.top(result)) == ["B"]
    assert "Paweł" in next(s for s in result if s.place.id == "A").reason


def test_no_solution_message():
    assert "Żadne z 4" in optimizer.summarize([], NAMES, 0.5, checked=4)


def test_summary_mentions_worst_traveller_and_subset():
    text = optimizer.summarize(optimizer.top(scored(1.0)), NAMES, 1.0, checked=4)
    assert text.startswith("B:") and "Paweł" in text and "z 4 sprawdzonych" in text
