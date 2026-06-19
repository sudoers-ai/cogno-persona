"""Unit tests for the pure prompt composer."""

from cogno_persona import CUSTOM_RULES_HEADER, Persona, compose_prompt, render


def test_render_substitutes_known_leaves_unknown():
    out = render("Hi {name}, balance {amount}, raw {json}", {"name": "Ana", "amount": "10"})
    assert out == "Hi Ana, balance 10, raw {json}"


def test_render_no_context_is_identity():
    assert render("untouched {x}") == "untouched {x}"


def test_compose_system_includes_rules_and_substitutes(sample_persona):
    out = compose_prompt(sample_persona, "system", context={"tenant_name": "PetCo"})
    assert "veterinary specialist for PetCo" in out
    assert CUSTOM_RULES_HEADER in out
    assert "confirm the pet's name" in out


def test_compose_with_base_prefix(sample_persona):
    out = compose_prompt(sample_persona, "system", base="GLOBAL RULES")
    assert out.startswith("GLOBAL RULES")
    assert "veterinary specialist" in out


def test_compose_non_system_slot_skips_rules(sample_persona):
    out = compose_prompt(sample_persona, "scope")
    assert out == "Allow pet questions only."
    assert CUSTOM_RULES_HEADER not in out  # rules only on the execution slot


def test_compose_append_rules_false(sample_persona):
    out = compose_prompt(sample_persona, "system", append_rules=False)
    assert CUSTOM_RULES_HEADER not in out


def test_compose_empty_slot():
    p = Persona(persona_id="X")  # all prompts empty
    assert compose_prompt(p, "voice") == ""
    assert compose_prompt(p, "system", base="only base") == "only base"


def test_compose_rules_skipped_when_no_rules(sample_persona):
    sample_persona.custom_rules = ""
    out = compose_prompt(sample_persona, "system")
    assert CUSTOM_RULES_HEADER not in out
