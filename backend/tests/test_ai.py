"""Ścieżka AI: PydanticAI (prawdziwy, z FunctionModel zamiast sieci) -> walidacja -> executor -> baza.

To NIE jest dowód działania OpenRouter — ten jest w test_live.py (wymaga klucza).
Tu sprawdzamy, że odpowiedź modelu w naszym schemacie zostaje poprawnie zapisana.
"""

import json

import pytest
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from app.config import Settings
from app.services import agent
from tests.conftest import act


@pytest.fixture
def model(monkeypatch):
    """Ustawia „odpowiedź modelu”. Zapamiętuje prompt, żeby sprawdzić, co widzi AI."""
    seen = {}

    def use(reply):
        def fn(messages, info):
            seen["prompt"] = messages[-1].parts[-1].content
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, str):
                return ModelResponse(parts=[TextPart(reply)])
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, reply)])

        monkeypatch.setattr(agent, "get_settings", lambda: Settings(openrouter_api_key="test"))
        monkeypatch.setattr(agent, "_model", lambda: FunctionModel(fn))
        return seen

    return use


def say(client, mid, text):
    out = client.post(f"/api/meetings/{mid}/interpret", json={"text": text}).json()
    return out, client.get(f"/api/meetings/{mid}").json()["participants"]


def test_ai_sees_ids_and_its_actions_are_saved(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Adam"})
    adam = client.get(f"/api/meetings/{meeting['id']}").json()["participants"][0]
    seen = model({"actions": [
        {"type": "remove_participant", "ref": adam["id"]},
        {"type": "add_participant", "name": "Kasia", "transport": "bike"},
    ], "reply": "Usuwam Adama i dodaję Kasię."})

    out, people = say(client, meeting["id"], "Usuń Adama i dodaj Kasię")
    assert adam["id"] in seen["prompt"]  # AI dostaje stabilne id
    assert out["source"] == "ai" and out["warnings"] == []
    assert [(p["name"], p["transport"]) for p in people] == [("Kasia", "bike")]


def test_ai_partial_update_keeps_other_fields(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 30})
    ola = client.get(f"/api/meetings/{meeting['id']}").json()["participants"][0]
    model({"actions": [{"type": "update_participant", "ref": ola["id"], "transport": "car"}]})
    _, people = say(client, meeting["id"], "Ola jednak autem")
    assert (people[0]["transport"], people[0]["max_minutes"], people[0]["id"]) == ("car", 30, ola["id"])


def test_ai_question_changes_nothing(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    model({"actions": [], "question": "Kogo mam usunąć?"})
    out, people = say(client, meeting["id"], "Usuń kogoś")
    assert out["question"] == "Kogo mam usunąć?" and len(people) == 1


def test_ai_invalid_action_is_rejected_atomically(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    model({"actions": [
        {"type": "add_participant", "name": "Kasia"},
        {"type": "remove_participant", "ref": "nieistniejące-id"},
    ]})
    out, people = say(client, meeting["id"], "Dodaj Kasię i usuń Zenona")
    assert [p["name"] for p in people] == ["Ola"] and out["applied"] == []


def test_ai_coordinates_are_not_accepted(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola"})
    ola = client.get(f"/api/meetings/{meeting['id']}").json()["participants"][0]
    # set_start nie należy do akcji AI -> PydanticAI odrzuca odpowiedź, działa parser reguł
    model({"actions": [{"type": "set_start", "ref": ola["id"], "point": {"lat": 52.2, "lon": 21.0}}]})
    out, people = say(client, meeting["id"], "Ola startuje stąd")
    assert people[0]["start"] is None
    assert out["source"] == "rules" and "niezgodną ze schematem" in out["warnings"][0]


@pytest.mark.parametrize("error,message", [
    (ModelHTTPError(401, "m"), "odrzucił klucz (401)"),
    (ModelHTTPError(403, "m"), "limit klucza"),
    (ModelHTTPError(429, "m"), "przeciążony (429)"),
])
def test_ai_failures_are_diagnosable(client, meeting, model, error, message):
    model(error)
    out, people = say(client, meeting["id"], "Będziemy we czwórkę")
    assert out["source"] == "rules" and message in out["warnings"][0]
    assert len(people) == 4  # parser reguł wykonał polecenie


def test_ai_garbage_text_falls_back(client, meeting, model):
    model("to nie jest JSON")
    out, _ = say(client, meeting["id"], "Dodaj Pawła")
    assert out["source"] == "rules" and out["warnings"]


def test_prompt_contains_full_state(client, meeting, model):
    act(client, meeting["id"], {"type": "add_participant", "name": "Ola", "transport": "bike", "max_minutes": 25})
    seen = model({"actions": []})
    say(client, meeting["id"], "cokolwiek")
    state = json.loads(seen["prompt"].split("Stan spotkania:\n")[1].split("\n\nPolecenie")[0])
    assert state["uczestnicy"][0] | {"id": "?"} == {
        "id": "?", "name": "Ola", "transport": "bike", "max_minutes": 25, "start": None, "start_proposal": None,
        "pusta": False,
    }


def _result(winner="Velvet"):
    from datetime import UTC, datetime

    from app.schemas.analysis import Place, PlaceScore, Result, Usage

    recs = [PlaceScore(place=Place(id=n, name=n, lat=52.2, lon=21.0), times_min={"a": 10}, mean_min=m,
                       max_min=x, score=s, feasible=True) for n, m, x, s in [(winner, 15, 18, 16.5), ("Kumple", 12, 25, 18.5)]]
    return Result(stale=False, provider="fake", computed_at=datetime.now(UTC), alpha=0.5, recommendations=recs,
                  candidates=recs, surface={}, summary="", usage=Usage())


def test_explain_prompt_names_the_winner_and_formula(model):
    seen = model("Velvet wygrywa, bo najdłuższy dojazd to tylko 18 min.")
    assert agent.explain(_result(), []) == "Velvet wygrywa, bo najdłuższy dojazd to tylko 18 min."
    assert "ZWYCIĘZCA: Velvet — score 16.5" in seen["prompt"]


def test_explain_that_contradicts_ranking_is_dropped(model):
    model("Najlepsze są Kumple, bo mają najniższą średnią.")
    assert agent.explain(_result(), []) is None


def test_empty_model_setting_falls_back_to_default():
    from app.config import DEFAULT_MODEL

    assert Settings(openrouter_model="").openrouter_model == DEFAULT_MODEL
    assert Settings(openrouter_model="  ").openrouter_model == DEFAULT_MODEL
