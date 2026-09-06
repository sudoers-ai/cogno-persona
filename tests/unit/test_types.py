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


# ── `domains`: the subject a persona OWNS, declared ──────────────────────────────


def test_a_persona_that_declares_no_domain_owns_none():
    """The default is the honest reading of an unanswered question."""
    p = Persona(persona_id="X")
    assert p.domains == []
    assert p.owned_domains == frozenset()


def test_a_persona_with_no_modules_can_own_a_domain():
    """THE property. Ownership is DECLARED, never inferred from the tool binding.

    A prompts-only persona — one that interviews or advises for a living — binds no
    module. Under the inferred rule it owned nothing, so a request squarely inside its
    subject resolved to no owner and the persona was reachable only by NAME.
    """
    p = Persona(persona_id="INTERVIEWER", domains=["MARKETING"])
    assert p.allowed_modules == [] and p.primary_module is None
    assert p.owned_domains == frozenset({"MARKETING"})


def test_domains_are_normalised_at_the_door():
    """Case, padding and repeats are spelling, not meaning — order is kept."""
    p = Persona(persona_id="X", domains=("  marketing ", "MARKETING", "", "Finance"))
    assert p.domains == ["MARKETING", "FINANCE"]


def test_a_single_domain_string_is_not_exploded():
    """A bare string is one value, not a sequence of characters."""
    p = Persona(persona_id="X", domains=["MARKETING"])
    assert p.domains == ["MARKETING"]
    with pytest.raises(Exception):
        Persona(persona_id="X", domains="MARKETING")


def test_owned_domains_cannot_disagree_with_domains():
    """One definition: the set is derived from the normalised list, not re-derived."""
    p = Persona(persona_id="X", domains=["marketing", "finance", "MARKETING"])
    assert p.owned_domains == set(p.domains)


def test_two_personas_may_declare_the_same_domain():
    """This lib holds the declaration; arbitrating an ambiguous owner is the host's
    catalogue question, and a lib must not refuse a host's catalogue over a rule only
    the host can state."""
    a = Persona(persona_id="A", domains=["MARKETING"])
    b = Persona(persona_id="B", domains=["MARKETING"])
    assert a.owned_domains == b.owned_domains == frozenset({"MARKETING"})


def test_domains_round_trip_through_a_dict():
    p = Persona(persona_id="X", domains=["MARKETING"], allowed_modules=["scheduler"])
    assert Persona(**p.model_dump()) == p


def test_a_set_of_domains_comes_out_in_a_stable_order():
    """A set's iteration order varies between processes; the same persona must not come
    out of two workers with its domains in two different orders."""
    raw = {"MARKETING", "FINANCE", "TECH", "HEALTH", "TRAVEL", "LAW"}
    from_set = Persona(persona_id="X", domains=raw).domains
    assert from_set == ["FINANCE", "HEALTH", "LAW", "MARKETING", "TECH", "TRAVEL"]
