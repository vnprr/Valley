"""CRUD spotkań i walidacja wejścia."""

from tests.conftest import act


def test_crud_cycle(client):
    created = client.post("/api/meetings", json={"title": "Kawa"})
    assert created.status_code == 201
    mid = created.json()["id"]

    assert client.get(f"/api/meetings/{mid}").json()["title"] == "Kawa"
    assert [m["id"] for m in client.get("/api/meetings").json()] == [mid]
    assert client.patch(f"/api/meetings/{mid}", json={"title": "Kawa w piątek"}).json()["title"] == "Kawa w piątek"

    assert client.delete(f"/api/meetings/{mid}").status_code == 204
    assert client.get(f"/api/meetings/{mid}").status_code == 404


def test_new_participants_get_stable_ids_and_unique_colors(client, meeting):
    people = act(client, meeting["id"], *[{"type": "add_participant", "name": n} for n in "ABC"])["participants"]
    assert len({p["id"] for p in people}) == 3
    assert len({p["color"] for p in people}) == 3


def test_start_outside_warsaw_rejected(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    act(client, meeting["id"], {"type": "set_start", "ref": "Ola", "point": {"lat": 50.06, "lon": 19.94}}, status=422)


def test_alpha_must_be_between_0_and_1(client, meeting):
    act(client, meeting["id"], {"type": "update_criteria", "alpha": 1.5}, status=422)


def test_unknown_action_rejected(client, meeting):
    act(client, meeting["id"], {"type": "teleport", "ref": "x"}, status=422)
