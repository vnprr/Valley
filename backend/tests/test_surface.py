from app.schemas.analysis import Place, PlaceScore
from app.services.surface import GRID, build_surface


def score(i, lat, lon, value):
    return PlaceScore(place=Place(id=str(i), name=str(i), lat=lat, lon=lon), times_min={},
                      mean_min=value, max_min=value, score=value, feasible=True)


POINTS = [score(0, 52.20, 21.00, 30), score(1, 52.22, 21.02, 12), score(2, 52.24, 21.00, 25), score(3, 52.21, 21.04, 40)]


def test_valley_floor_is_the_best_evaluated_place():
    surface = build_surface(POINTS)
    floor = min(surface["features"], key=lambda f: f["properties"]["value"])
    (x0, y0), _, (x1, y1), *_ = floor["geometry"]["coordinates"][0]
    assert floor["properties"]["value"] == 12 and floor["properties"]["measured"]
    assert x0 <= 21.02 <= x0 + (x1 - x0) / 0.94 and y0 <= 52.22 <= y0 + (y1 - y0) / 0.94


def test_cells_far_from_evaluated_places_are_not_drawn():
    assert 0 < len(build_surface(POINTS)["features"]) < GRID * GRID


def test_heights_are_normalized():
    ts = [f["properties"]["t"] for f in build_surface(POINTS)["features"]]
    assert min(ts) == 0 and max(ts) <= 1


def test_surface_needs_at_least_three_points():
    assert build_surface(POINTS[:2])["features"] == []
