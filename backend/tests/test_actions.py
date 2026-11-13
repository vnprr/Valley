"""Operacje na uczestnikach — wspólne dla AI i ręcznej edycji (PATCH z akcjami)."""

from app.schemas.meeting import Participant
from app.services.errors import CommandError
from app.services.people import resolve, stem
from tests.conftest import act

import pytest


def people(client, mid):
    return client.get(f"/api/meetings/{mid}").json()["participants"]


def test_add_many_in_one_command(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"}, {"type": "add_participant", "name": "Paweł"})
    assert [p["name"] for p in people(client, meeting["id"])] == ["Ola", "Paweł"]


def test_update_changes_only_given_fields_and_keeps_id(client, meeting):
    act(client, meeting["id"],
        {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 30},
        {"type": "set_start", "ref": "Ola", "point": {"lat": 52.23, "lon": 21.01}})
    before = people(client, meeting["id"])[0]

    act(client, meeting["id"], {"type": "update_participant", "ref": before["id"], "transport": "car"})
    after = people(client, meeting["id"])[0]
    assert after["transport"] == "car"
    assert {k: v for k, v in after.items() if k != "transport"} == {k: v for k, v in before.items() if k != "transport"}


def test_two_fields_at_once_and_explicit_clear(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 30})
    act(client, meeting["id"], {"type": "update_participant", "ref": "Oli", "transport": "car", "max_minutes": 25})
    ola = people(client, meeting["id"])[0]
    assert (ola["transport"], ola["max_minutes"]) == ("car", 25)

    act(client, meeting["id"], {"type": "clear_participant_field", "ref": "Ola", "field": "max_minutes"})
    ola = people(client, meeting["id"])[0]
    assert ola["max_minutes"] is None and ola["transport"] == "car"


def test_rename_keeps_identity(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike"})
    pid = people(client, meeting["id"])[0]["id"]
    act(client, meeting["id"], {"type": "update_participant", "ref": "Oli", "name": "Aleksandra"})
    ola = people(client, meeting["id"])[0]
    assert (ola["id"], ola["name"], ola["transport"]) == (pid, "Aleksandra", "bike")


def test_remove_named_person_directly(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Paweł", "transport": "walk"},
        {"type": "add_participant", "name": "Ola"})
    act(client, meeting["id"], {"type": "remove_participant", "ref": "Pawła"})
    assert [p["name"] for p in people(client, meeting["id"])] == ["Ola"]


def test_invalid_command_saves_nothing(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    # druga akcja wskazuje nieistniejącą osobę -> całość odrzucona, Kasia NIE zostaje dodana
    act(client, meeting["id"], {"type": "add_participant", "name": "Kasia"},
        {"type": "remove_participant", "ref": "Zenon"}, status=422)
    assert [p["name"] for p in people(client, meeting["id"])] == ["Ola"]


def test_limit_of_six(client, meeting):
    act(client, meeting["id"], {"type": "set_participant_count", "count": 6})
    act(client, meeting["id"], {"type": "add_participant", "name": "Siódmy"}, status=422)
    act(client, meeting["id"], {"type": "set_participant_count", "count": 7}, status=422)
    assert len(people(client, meeting["id"])) == 6


def test_count_grows_with_placeholders_and_keeps_named(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike"})
    names = [p["name"] for p in act(client, meeting["id"], {"type": "set_participant_count", "count": 4})["participants"]]
    assert names == ["Ola", "Osoba 2", "Osoba 3", "Osoba 4"]


def test_count_shrink_removes_only_empty_cards(client, meeting):
    act(client, meeting["id"], {"type": "set_participant_count", "count": 4})
    act(client, meeting["id"], {"type": "update_participant", "ref": "Osoba 1", "name": "Ola", "transport": "bike"})
    names = [p["name"] for p in act(client, meeting["id"], {"type": "set_participant_count", "count": 2})["participants"]]
    assert names == ["Ola", "Osoba 2"]


def test_count_shrink_asks_instead_of_deleting_named(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"}, {"type": "add_participant", "name": "Adam"},
        {"type": "add_participant", "name": "Kasia"})
    response = client.patch(f"/api/meetings/{meeting['id']}", json={"actions": [{"type": "set_participant_count", "count": 2}]})
    assert response.status_code == 422 and "Kogo usunąć" in response.json()["detail"]
    assert len(people(client, meeting["id"])) == 3


def test_duplicate_name_rejected(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    act(client, meeting["id"], {"type": "add_participant", "name": "Olę"}, status=422)


def test_place_becomes_proposal_and_needs_confirmation(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    ola = act(client, meeting["id"], {"type": "update_participant", "ref": "Ola", "place": "Mokotów"})["participants"][0]
    assert ola["start"] is None and ola["start_proposal"]["label"] == "Mokotów, Warszawa"

    ola = act(client, meeting["id"], {"type": "confirm_start", "ref": ola["id"]})["participants"][0]
    assert ola["start"] == {"lat": 52.1937, "lon": 21.0444} and ola["start_proposal"] is None


def test_reject_proposal_with_clear_action(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "place": "Mokotów"})
    ola = act(client, meeting["id"], {"type": "clear_participant_field", "ref": "Ola", "field": "start_proposal"})["participants"][0]
    assert ola["start_proposal"] is None and ola["start"] is None


def test_unknown_place_is_warning_not_guess(client, meeting):
    ola = act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "place": "Atlantyda"})["participants"][0]
    assert ola["start"] is None and ola["start_proposal"] is None


# ---------- rozpoznawanie osób ----------

@pytest.mark.parametrize("name,form", [
    ("Ola", "Oli"), ("Ola", "Olę"), ("Ola", "Olą"), ("Paweł", "Pawła"), ("Paweł", "Pawłem"),
    ("Adam", "Adama"), ("Adam", "Adamowi"), ("Kasia", "Kasię"), ("Marek", "Marka"), ("Osoba 3", "osobę 3"),
])
def test_polish_inflection_resolves(name, form):
    assert stem(name) == stem(form)
    assert resolve([Participant(name=name), Participant(name="Zenon")], form).name == name


def test_ambiguous_reference_asks():
    with pytest.raises(CommandError) as err:
        resolve([Participant(name="Jan"), Participant(name="Jana")], "Jana")
    assert err.value.needs_answer


def test_id_wins_over_name():
    ola = Participant(id="x1", name="Ola")
    assert resolve([Participant(name="x1"), ola], "x1") is ola
