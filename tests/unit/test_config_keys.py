"""The property this feature exists for: ONE declaration, TWO readings — and the boundary.

A tenant declares a key once. A TOOL reads it by name (``config_values``) and the MODEL reads
it as prose (``render_config_keys``). If those are two implementations of one fact they will
drift, and the drift is invisible: the model quotes one hourly rate while the tool computes
with another, and nothing in either half looks wrong on its own.

So the readings are not two implementations. ``render_config_keys`` is EXPRESSED OVER
``config_values`` — it asks for the by-name mapping and renders what came back — and
``test_the_render_is_expressed_over_the_values`` proves it by monkeypatching the source and
watching the prompt follow. The parametrized twins below then walk a probe table and assert
both readings for every kept key and NEITHER reading for every dropped one.

The other half of the file is the BOUNDARY. A config key is a scalar; long content is
knowledge. The limit is enforced at the door, not advised in a comment, and the number is
measured — see ``cogno_persona.config_keys``' module docstring.
"""

import pytest

from cogno_persona import (
    CONFIG_DROP_REASONS,
    CONFIG_KEY_TYPES,
    MAX_CONFIG_KEYS,
    MAX_CONFIG_VALUE_CHARS,
    ConfigKey,
    Persona,
    compose_prompt,
    config_values,
    render_config_keys,
    sanitize_config_keys,
)
from cogno_persona import config_keys as ck


# ── the probe table ────────────────────────────────────────────────────────────────────────
#
# One entry per accepted TYPE, so a type added to the closed vocabulary without a value path or
# a render path fails ``test_the_probe_covers_every_declared_type`` rather than shipping half
# wired. The live worked example is first: the hourly rate a professor asks about, in the
# decimal form its tenant writes on its invoices.
KEPT = [
    ({"name": "PAY_RATE_PER_HOUR", "value": "120,00", "type": "number",
      "label": "Valor/hora do professor"}, "120,00"),
    ({"name": "COLUMN_HOURS", "value": "Carga Horária", "type": "text",
      "label": "Coluna da carga horária"}, "Carga Horária"),
    ({"name": "SEND_CALENDAR", "value": "true", "type": "boolean",
      "label": "Enviar convite de calendário"}, "true"),
]

DROPPED = [
    ({"name": "", "value": "x"}, "bad_name"),
    ({"name": "lower case", "value": "x"}, "bad_name"),
    ({"name": "OK", "value": "x", "type": "colour"}, "unknown_type"),
    ({"name": "OK", "value": "cento e vinte", "type": "number"}, "not_a_number"),
    ({"name": "OK", "value": "1.234,56", "type": "number"}, "not_a_number"),
    ({"name": "OK", "value": "talvez", "type": "boolean"}, "not_a_boolean"),
    ({"name": "OK", "value": "   "}, "empty_value"),
    ({"name": "OK", "value": "x" * (MAX_CONFIG_VALUE_CHARS + 1)}, "too_long"),
    ("not an object", "malformed"),
]


# ── the property ───────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("entry,value", KEPT, ids=[e[0]["name"] for e in KEPT])
def test_a_declared_key_is_read_BY_NAME_and_appears_in_the_PROMPT(entry, value):
    """The headline. ONE declaration goes in; both readings come out carrying it.

    Mutation: delete the ``config_values`` call from ``render_config_keys`` and return ``""``
    → the prompt assertion dies for all three. Delete the ``{key.name: key.value}``
    comprehension's body → both die, which is the point: there is one source.
    """
    kept, dropped = sanitize_config_keys([entry])
    assert dropped == (), f"the probe entry should be accepted, got {dropped}"

    # READING ONE — a tool asks by name.
    assert config_values(kept)[entry["name"].upper()] == value

    # READING TWO — the model reads prose.
    block = render_config_keys(kept)
    assert value in block, "the declared value never reached the prompt"
    assert entry["label"] in block, "the human label never reached the prompt"
    assert entry["name"].upper() in block, "the by-name handle is not shown beside the value"


@pytest.mark.parametrize("entry,reason", DROPPED,
                         ids=[f"{r}-{i}" for i, (_e, r) in enumerate(DROPPED)])
def test_a_refused_declaration_reaches_NEITHER_reading(entry, reason):
    """The inverse, and the reason one source matters: a drop must be total.

    A key refused by the door but still rendered would tell the model a value no tool can act
    on — the exact divergence the single source exists to prevent, arriving from the other
    end.
    """
    kept, dropped = sanitize_config_keys([entry])
    assert kept == (), "a refused declaration was kept"
    assert [d.reason for d in dropped] == [reason]
    assert dropped[0].reason in CONFIG_DROP_REASONS
    assert config_values(kept) == {}
    assert render_config_keys(kept) == ""


def test_the_render_is_expressed_over_the_values(monkeypatch):
    """STRUCTURAL, not behavioural: prove the prompt block reads the tool's mapping.

    Two assertions that a same-source claim needs and a value-equality test cannot make. First
    the CONTROL — with the real function, the key renders — because a test that only watches
    something disappear passes just as well when it was never there. Then the substitution: a
    ``config_values`` that hides the key must empty the prompt too.

    Mutation: make ``render_config_keys`` walk ``keys`` itself instead of calling
    ``config_values`` and this dies while every value-equality test above still passes — which
    is precisely the drift they cannot see.
    """
    kept, _ = sanitize_config_keys([KEPT[0][0]])
    assert "120,00" in render_config_keys(kept)          # control: it IS there to lose

    monkeypatch.setattr(ck, "config_values", lambda keys: {})
    assert render_config_keys(kept) == "", (
        "render_config_keys does not read config_values — the two readings are two "
        "implementations and will drift")


def test_the_probe_covers_every_declared_type():
    """Anti-staleness: a new type in the closed vocabulary must arrive with a probe row."""
    assert {e["type"] for e, _v in KEPT} == set(CONFIG_KEY_TYPES)


def test_the_probe_covers_every_drop_reason_the_door_can_reach():
    """Every reason a caller can trigger with one entry is exercised.

    ``duplicate`` and ``overflow`` need more than one entry, so they have tests of their own
    below rather than a probe row; this asserts the remainder are all covered.
    """
    covered = {r for _e, r in DROPPED} | {"duplicate", "overflow"}
    assert covered == set(CONFIG_DROP_REASONS)


# ── the boundary: a key is a scalar, long content is knowledge ─────────────────────────────

def test_the_length_boundary_is_enforced_not_advised():
    """At the limit it is kept; one character past it, it is dropped and NAMED.

    The boundary exists because a knowledge body in a config key is a knowledge body every turn
    pays for in full, in a field with no retrieval. Measured on the production row this feature
    came from: the longest declared value is 27 characters and configuration is 5.4% of the
    13 187-character blob it lives in. The other 94.6% is what a knowledge base is for.
    """
    at = {"name": "K", "value": "v" * MAX_CONFIG_VALUE_CHARS}
    over = {"name": "K", "value": "v" * (MAX_CONFIG_VALUE_CHARS + 1)}
    kept_at, dropped_at = sanitize_config_keys([at])
    assert len(kept_at) == 1 and dropped_at == ()
    kept_over, dropped_over = sanitize_config_keys([over])
    assert kept_over == ()
    assert dropped_over[0].name == "K" and dropped_over[0].reason == "too_long"


def test_an_over_long_value_is_dropped_alone_not_with_its_neighbours():
    """One bad key costs the tenant that key, never the persona's whole configuration."""
    kept, dropped = sanitize_config_keys([
        {"name": "GOOD", "value": "keep me"},
        {"name": "HUGE", "value": "x" * (MAX_CONFIG_VALUE_CHARS + 1)},
        {"name": "ALSO_GOOD", "value": "keep me too"},
    ])
    assert [k.name for k in kept] == ["GOOD", "ALSO_GOOD"]
    assert [(d.name, d.reason) for d in dropped] == [("HUGE", "too_long")]


# ── the door's remaining rules ─────────────────────────────────────────────────────────────

def test_the_first_declaration_of_a_name_wins():
    """Measured on the live row: every one of its 12 keys is declared TWICE.

    The prose parser this replaces took the first match, so taking the first here keeps a
    migrated tenant on the value it already had. The second is reported, not silently eaten.
    """
    kept, dropped = sanitize_config_keys([
        {"name": "RATE", "value": "120,00", "type": "number"},
        {"name": "RATE", "value": "999,00", "type": "number"},
    ])
    assert [(k.name, k.value) for k in kept] == [("RATE", "120,00")]
    assert [(d.name, d.reason) for d in dropped] == [("RATE", "duplicate")]


def test_a_duplicate_is_settled_before_the_cap():
    """A tenant who repeated a key must not lose a DIFFERENT one to the overflow.

    ``MAX_CONFIG_KEYS`` distinct names, each declared twice: all of them survive. Move the cap
    check above the duplicate check and the second half is refused as ``overflow`` instead.
    """
    entries = []
    for i in range(MAX_CONFIG_KEYS):
        entries += [{"name": f"K{i}", "value": "v"}] * 2
    kept, dropped = sanitize_config_keys(entries)
    assert len(kept) == MAX_CONFIG_KEYS
    assert {d.reason for d in dropped} == {"duplicate"}


def test_the_cap_refuses_the_overflow_and_names_it():
    entries = [{"name": f"K{i}", "value": "v"} for i in range(MAX_CONFIG_KEYS + 2)]
    kept, dropped = sanitize_config_keys(entries)
    assert len(kept) == MAX_CONFIG_KEYS
    assert [(d.name, d.reason) for d in dropped] == [
        (f"K{MAX_CONFIG_KEYS}", "overflow"), (f"K{MAX_CONFIG_KEYS + 1}", "overflow")]


def test_declaration_order_survives():
    """The prompt renders in declaration order, so it must be stable across workers."""
    entries = [{"name": n, "value": "v"} for n in ("ZED", "ALPHA", "MIDDLE")]
    kept, _ = sanitize_config_keys(entries)
    assert [k.name for k in kept] == ["ZED", "ALPHA", "MIDDLE"]
    assert list(config_values(kept)) == ["ZED", "ALPHA", "MIDDLE"]


@pytest.mark.parametrize("carrier", [None, "", "   ", [], ()])
def test_nothing_declared_is_not_an_error(carrier):
    assert sanitize_config_keys(carrier) == ((), ())
    assert render_config_keys(()) == "", "a heading over no keys is worse than silence"


@pytest.mark.parametrize("carrier", ['{"not": "a list"}', "not json at all", 42,
                                     '[' * 200, b"\xff\xfe"])
def test_an_unusable_carrier_costs_the_keys_and_never_raises(carrier):
    """PURE means PURE: a malformed column must not take the turn down with it."""
    kept, dropped = sanitize_config_keys(carrier)
    assert kept == () and [d.reason for d in dropped] == ["malformed"]


def test_a_json_array_string_is_the_accepted_column_shape():
    """The host stores this as text, the way ``onboarding_items`` already is."""
    kept, dropped = sanitize_config_keys(
        '[{"name": "PAY_RATE_PER_HOUR", "value": "120,00", "type": "number"}]')
    assert dropped == () and config_values(kept) == {"PAY_RATE_PER_HOUR": "120,00"}


def test_json_native_scalars_are_accepted_for_number_and_boolean():
    """An admin UI that sends 120 rather than "120" declared the same thing."""
    kept, dropped = sanitize_config_keys([
        {"name": "N", "value": 120, "type": "number"},
        {"name": "B", "value": True, "type": "boolean"},
    ])
    assert dropped == ()
    assert config_values(kept) == {"N": "120", "B": "true"}


def test_a_carrier_past_the_guard_is_refused_before_the_json_parser():
    kept, dropped = sanitize_config_keys("[" + "x" * ck.MAX_CONFIG_CARRIER_CHARS)
    assert kept == () and dropped[0].reason == "malformed"


# ── the typed accessors ────────────────────────────────────────────────────────────────────

def test_a_number_parses_with_either_decimal_separator():
    kept, _ = sanitize_config_keys([{"name": "A", "value": "120,00", "type": "number"},
                                    {"name": "B", "value": "120.00", "type": "number"},
                                    {"name": "C", "value": "-3", "type": "number"}])
    assert [k.as_number() for k in kept] == [120.0, 120.0, -3.0]


def test_an_accessor_off_its_own_type_answers_None_rather_than_guessing():
    kept, _ = sanitize_config_keys([{"name": "T", "value": "120,00", "type": "text"}])
    assert kept[0].as_number() is None and kept[0].as_boolean() is None


@pytest.mark.parametrize("raw,expected", [("true", True), ("sim", True), ("1", True),
                                          ("false", False), ("não", False), ("0", False)])
def test_a_boolean_reads_the_words_a_tenant_actually_types(raw, expected):
    kept, dropped = sanitize_config_keys([{"name": "B", "value": raw, "type": "boolean"}])
    assert dropped == () and kept[0].as_boolean() is expected


# ── the Persona door, and the prompt it composes ───────────────────────────────────────────

def test_the_persona_normalises_at_the_door_like_domains_does():
    """A Persona can never HOLD a key the admin API would refuse — one rule, two ends."""
    p = Persona(persona_id="X", config_keys=[
        {"name": "pay_rate_per_hour", "value": " 120,00 ", "type": "number"},
        {"name": "OK", "value": "cento e vinte", "type": "number"},
    ])
    assert [k.name for k in p.config_keys] == ["PAY_RATE_PER_HOUR"]
    assert p.config == {"PAY_RATE_PER_HOUR": "120,00"}


def test_a_persona_that_declares_nothing_is_untouched():
    p = Persona(persona_id="X", prompts={"system": "Do the thing."})
    assert p.config_keys == [] and p.config == {}
    assert compose_prompt(p, "system") == "Do the thing."


def test_the_declared_block_precedes_the_prose_block():
    """The prose must not be the LAST word about a key a tool also acts on.

    A persona part-migrated to declared keys carries the same fact twice for a while, and
    whichever section comes second reads as the correction of the first.
    """
    p = Persona(persona_id="X", prompts={"system": "Base."},
                custom_rules="PAY_RATE_PER_HOUR: 90,00",
                config_keys=[{"name": "PAY_RATE_PER_HOUR", "value": "120,00",
                              "type": "number"}])
    text = compose_prompt(p, "system")
    assert text.index("120,00") < text.index("90,00")


@pytest.mark.parametrize("slot", ["scope", "limits", "voice"])
def test_only_the_execution_slot_carries_the_block(slot):
    """Same placement rule ``custom_rules`` already has — one decision, not two."""
    p = Persona(persona_id="X", prompts={s: "text" for s in ("system", "scope",
                                                             "limits", "voice")},
                config_keys=[{"name": "K", "value": "v"}])
    assert "K" not in compose_prompt(p, slot)
    assert "K" in compose_prompt(p, "system")


def test_append_rules_False_suppresses_the_block_too():
    p = Persona(persona_id="X", prompts={"system": "Base."},
                config_keys=[{"name": "K", "value": "v"}])
    assert compose_prompt(p, "system", append_rules=False) == "Base."


def test_a_ConfigKey_instance_is_an_accepted_declaration():
    """Round trip: what came out of the door goes back in unchanged."""
    kept, _ = sanitize_config_keys([{"name": "K", "value": "v", "label": "Kay"}])
    again, dropped = sanitize_config_keys(list(kept))
    assert again == kept and dropped == ()
    assert isinstance(kept[0], ConfigKey)
