"""Parser reguł (tryb bez AI) — od tekstu do zapisanych kart, przez ten sam executor."""

import pytest

from app.services.intent_rules import nominative, parse
from tests.conftest import act


def say(client, mid, text):
    response = client.post(f"/api/meetings/{mid}/interpret", json={"text": text})
    assert response.status_code == 200
    out = response.json()
    assert out["source"] == "rules"
    # zapis sprawdzamy osobnym odczytem z bazy, nie tylko odpowiedzią
    return out, client.get(f"/api/meetings/{mid}").json()["participants"]


def names(people):
    return [p["name"] for p in people]


def test_set_count(client, meeting):
    _, people = say(client, meeting["id"], "Będziemy we czwórkę")
    assert names(people) == ["Osoba 1", "Osoba 2", "Osoba 3", "Osoba 4"]
    assert all(p["start"] is None and p["transport"] is None for p in people)  # nic nie zmyślone


def test_add_two_with_inflection(client, meeting):
    _, people = say(client, meeting["id"], "Dodaj Olę i Pawła")
    assert names(people) == ["Ola", "Paweł"]


def test_add_after_count_adds_new_card(client, meeting):
    say(client, meeting["id"], "Będziemy we czwórkę")
    _, people = say(client, meeting["id"], "Dodaj Pawła")
    assert names(people)[-1] == "Paweł" and len(people) == 5


def test_patch_transport_of_existing(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Adam", "transport": "car", "max_minutes": 20})
    _, people = say(client, meeting["id"], "Adam jednak pójdzie pieszo")
    assert (people[0]["transport"], people[0]["max_minutes"]) == ("walk", 20)


def test_patch_two_fields(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike"})
    _, people = say(client, meeting["id"], "Zmień Oli transport na auto i limit na 25 minut")
    assert (people[0]["transport"], people[0]["max_minutes"]) == ("car", 25)


def test_remove_and_add_in_one_command(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Adam"}, {"type": "add_participant", "name": "Ola"})
    out, people = say(client, meeting["id"], "Usuń Adama i dodaj Kasię")
    assert names(people) == ["Ola", "Kasia"]
    assert out["applied"] == ["Usunięto: Adam", "Dodano: Kasia"]


def test_rename(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    _, people = say(client, meeting["id"], "Zmień imię Oli na Aleksandra")
    assert names(people) == ["Aleksandra"]


def test_negation_changes_nothing(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    out, people = say(client, meeting["id"], "Nie usuwaj Oli")
    assert names(people) == ["Ola"] and out["applied"] == []


def test_place_is_geocoded_into_proposal(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    _, people = say(client, meeting["id"], "Ola startuje z Mokotowa")
    assert people[0]["start"] is None
    assert people[0]["start_proposal"]["label"] == "Mokotów, Warszawa"


def test_name_claims_free_placeholder(client, meeting):
    say(client, meeting["id"], "Będziemy we czwórkę")
    _, people = say(client, meeting["id"], "Ola jedzie rowerem")
    assert names(people) == ["Ola", "Osoba 2", "Osoba 3", "Osoba 4"] and people[0]["transport"] == "bike"


def test_mixed_sentence(client, meeting):
    _, people = say(client, meeting["id"], "Jadę rowerem, Ola samochodem, a dwie pozostałe osoby idą pieszo")
    assert [(p["name"], p["transport"]) for p in people] == [
        ("Ja", "bike"), ("Ola", "car"), ("Osoba 3", "walk"), ("Osoba 4", "walk"),
    ]


def test_ambiguous_shrink_asks_and_keeps_people(client, meeting):
    act(client, meeting["id"], *[{"type": "add_participant", "name": n} for n in ("Ola", "Adam", "Kasia")])
    out, people = say(client, meeting["id"], "Będziemy we dwoje")
    assert out["question"] and "Kogo usunąć" in out["question"]
    assert len(people) == 3


def test_unknown_text_changes_nothing(client, meeting):
    out, people = say(client, meeting["id"], "Jaka będzie pogoda?")
    assert people == [] and out["applied"] == []


@pytest.mark.parametrize("form,expected", [("Pawła", "Paweł"), ("Olę", "Ola"), ("Kasię", "Kasia"), ("Adama", "Adam")])
def test_nominative(form, expected):
    assert nominative(form) == expected


def test_priority_words_set_alpha():
    assert parse("Zróbmy to sprawiedliwie", []).actions[0].alpha == 0.8


def test_clear_limit(client, meeting):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 30})
    _, people = say(client, meeting["id"], "Ola nie ma limitu czasu")
    assert (people[0]["max_minutes"], people[0]["transport"]) == (None, "bike")
