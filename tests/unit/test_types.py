"""Unit tests for the Persona model + prompt slots."""

import pytest

from cogno_persona import PROMPT_SLOTS, Persona, PersonaPrompts, SelectionResult


def test_prompt_slots_constant():
    assert PROMPT_SLOTS == ("system", "scope", "limits", "voice")


def test_prompts_get_valid_and_invalid():
    p = PersonaPrompts(system="s", scope="sc", limits="l", voice="v")
    assert p.get("system") == "s"
    assert p.get("voice") == "v"
    with pytest.raises(KeyError):
        p.get("unknown")


def test_persona_defaults():
    p = Persona(persona_id="X")
    assert p.description == "" and p.version == "current"
    assert p.allowed_modules == [] and p.custom_rules == ""
    assert p.primary_module is None
    assert p.prompt("system") == ""


def test_persona_primary_module_and_prompt(sample_persona):
    assert sample_persona.primary_module == "veterinary"
    assert sample_persona.prompt("scope") == "Allow pet questions only."


def test_persona_round_trips_dict():
    p = Persona(persona_id="VET", allowed_modules=["veterinary"],
                prompts=PersonaPrompts(system="hi"))
    data = p.model_dump()
    restored = Persona(**data)
    assert restored == p
    assert restored.prompt("system") == "hi"


def test_selection_result_defaults():
    r = SelectionResult(persona_id="BASE")
    assert r.matched is False and r.score == 0.0 and r.scores == []
