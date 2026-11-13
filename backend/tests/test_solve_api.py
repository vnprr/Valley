"""Obliczenia: kompletność, ranking, oszczędność zapytań, cache i awarie usług."""

from datetime import UTC, datetime, timedelta

from app.models.meeting import Meeting
from tests.conftest import act, add_ready_people


def solve(client, mid):
    response = client.post(f"/api/meetings/{mid}/solve")
    assert response.status_code == 200, response.text
    return response.json()["result"]


def test_incomplete_meeting_returns_problems(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    response = client.post(f"/api/meetings/{meeting['id']}/solve")
    assert response.status_code == 422
    problems = response.json()["problems"]
    assert any("od 2 do 6" in p for p in problems)
    assert any("Ola: wybierz punkt startowy" in p for p in problems)


def test_solve_returns_three_recommendations_within_budget(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    result = solve(client, meeting["id"])
    assert len(result["recommendations"]) == 3
    # z 64 kawiarni w puli dokładne trasy liczymy tylko dla 32 kandydatów
    assert len(result["candidates"]) == 32
    assert result["usage"]["pool_size"] == 64
    # jedna macierz na środek transportu; 3 osoby × 32 miejsca
    assert provider.calls["times"] == 3 and provider.calls["cells"] == 96
    assert result["usage"]["credits"] == 1 + 3 * 32  # Places + 3 macierze 1 × 32
    assert all(len(r["times_min"]) == 3 for r in result["recommendations"])


def test_repeated_solve_makes_no_requests(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    solve(client, meeting["id"])
    assert provider.calls["cafes"] == 1 and provider.calls["times"] == 3


def test_alpha_change_reranks_without_routing(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    fast = act(client, meeting["id"], {"type": "update_criteria", "alpha": 0})["result"]
    fair = act(client, meeting["id"], {"type": "update_criteria", "alpha": 1})["result"]
    assert fast["alpha"] == 0 and fair["alpha"] == 1
    assert fair["recommendations"][0]["max_min"] <= fast["recommendations"][0]["max_min"]
    assert provider.calls["times"] == 3


def test_rename_does_not_invalidate_routes(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    out = act(client, meeting["id"], {"type": "update_participant", "ref": "Ola", "name": "Aleksandra"})
    assert out["result"]["stale"] is False
    solve(client, meeting["id"])
    assert provider.calls["times"] == 3


def test_moving_one_person_refetches_only_their_row(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    stale = act(client, meeting["id"], {"type": "set_start", "ref": "Ola", "point": {"lat": 52.2299, "lon": 21.0124}})
    assert stale["result"]["stale"] is True

    cells_before = provider.calls["cells"]
    result = solve(client, meeting["id"])
    assert result["stale"] is False
    fetched = provider.calls["cells"] - cells_before
    assert fetched < 96  # nie wszystko od nowa
    assert result["usage"]["reused_cells"] >= 2 * 32 - 8  # wiersze Pawła i Kasi w większości z cache


def test_transport_change_refetches_that_person(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    act(client, meeting["id"], {"type": "update_participant", "ref": "Ola", "transport": "walk"})
    result = solve(client, meeting["id"])
    assert result["usage"]["reused_cells"] > 0  # Paweł i Kasia nie są liczeni od zera
    assert result["usage"]["matrix_cells"] >= 32  # nowy profil Oli = nowy wiersz


def test_cache_distinguishes_providers(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    provider.name = "inny-dostawca"
    solve(client, meeting["id"])
    assert provider.calls["times"] == 6  # inny dostawca = brak trafień w cache


def test_expired_cache_is_refetched(client, meeting, provider):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    # postarzamy wpisy cache o 2 dni i wymuszamy nowe liczenie zmianą startu Oli
    from app.database import get_db

    session = next(client.app.dependency_overrides[get_db]())
    m = session.get(Meeting, meeting["id"])
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    analysis = dict(m.last_analysis)
    analysis["route_cache"] = {k: {**v, "fetched_at": old} for k, v in analysis["route_cache"].items()}
    m.last_analysis = analysis
    session.commit()
    act(client, meeting["id"], {"type": "set_start", "ref": "Ola", "point": {"lat": 52.2299, "lon": 21.0124}})
    result = solve(client, meeting["id"])
    assert result["usage"]["reused_cells"] == 0


def test_unreachable_places_are_never_recommended(client, meeting, provider):
    provider.unreachable = {f"c{i}{j}" for i in range(8) for j in range(8) if (i + j) % 2}
    add_ready_people(client, meeting["id"])
    result = solve(client, meeting["id"])
    assert all(r["place"]["id"] not in provider.unreachable for r in result["recommendations"])
    assert any(c["reason"] and "brak trasy" in c["reason"] for c in result["candidates"])


def test_no_solution_is_reported(client, meeting):
    add_ready_people(client, meeting["id"])
    solve(client, meeting["id"])
    result = act(client, meeting["id"], {"type": "update_participant", "ref": "Paweł", "max_minutes": 5},
                 {"type": "update_participant", "ref": "Kasia", "max_minutes": 5})["result"]
    assert result["recommendations"] == []
    assert "Żadne z 32" in result["summary"]


def test_provider_failure_returns_502(client, meeting, provider):
    provider.fail = True
    add_ready_people(client, meeting["id"])
    response = client.post(f"/api/meetings/{meeting['id']}/solve")
    assert response.status_code == 502
    assert "Geoapify" in response.json()["detail"]
