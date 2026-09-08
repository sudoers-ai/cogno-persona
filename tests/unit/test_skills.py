"""The skill declaration layer: the catalog row, the two ports, and the two rules.

The mechanism only. Nothing here names a skill, because naming one would be the host's catalog
leaking into the library — and the tests are written so that a catalog of opaque tokens is
enough to measure every rule.

Two of these rules exist because a caller got them wrong in production, and both defects are
INVISIBLE to a test that only checks the happy path: a row deleted on disable (so "switched off"
and "never seeded" became the same state), and a full sync of the empty set (so a save from a tab
that never read the bindings wiped them). Each has its twin here, plus the control that shows the
test could tell the difference.
"""

from __future__ import annotations

import pytest

from cogno_persona.skills import (
    CORE_SCOPE,
    SKILL_TIERS,
    InMemoryPersonaSkillStore,
    InMemoryTenantSkillStore,
    PersonaSkillClearRefused,
    PersonaSkillStore,
    SkillInfo,
    TenantSkill,
    TenantSkillStore,
    refuses_clear,
    skill_tier,
)


# ── SkillInfo + skill_tier: one class, read once ─────────────────────────────────────────


@pytest.mark.parametrize("flags,expected", [
    ({"is_system": True}, "system"),
    ({"is_default": True}, "default"),
    ({"is_premium": True}, "premium"),
])
def test_exactly_one_flag_names_the_tier(flags, expected):
    assert skill_tier(SkillInfo(id="s", **flags)) == expected


def test_no_flag_at_all_is_unclassified():
    """A skill nobody classified. ``""`` and not a guess — and callers must read it as NOT
    system, which is the one answer an unclassified skill must never get by accident."""
    assert skill_tier(SkillInfo(id="s")) == ""


@pytest.mark.parametrize("flags", [
    {"is_default": True, "is_premium": True},
    {"is_system": True, "is_premium": True},
    {"is_system": True, "is_default": True},
    {"is_system": True, "is_default": True, "is_premium": True},
])
def test_two_flags_at_once_is_ALSO_unclassified(flags):
    """The failure a "is any flag set?" predicate would wave through. ``is_default`` and
    ``is_premium`` gate in OPPOSITE directions — one is opt-in, the other opt-in plus a paid
    plan — so a row carrying both is not "either", it is a mistake."""
    assert skill_tier(SkillInfo(id="s", **flags)) == ""


def test_the_tier_vocabulary_is_closed_and_skill_tier_can_only_answer_from_it():
    assert SKILL_TIERS == ("system", "default", "premium")
    for flags in ({"is_system": True}, {"is_default": True}, {"is_premium": True}, {}):
        assert skill_tier(SkillInfo(id="s", **flags)) in SKILL_TIERS + ("",)


def test_guest_capable_and_guest_by_default_are_independent():
    """Two questions, not one: does the toggle EXIST, and where does the seed LEAVE it.
    Collapsing them forces a false choice — hide a switch the admin should have, or hand out
    third-party data by default — and a catalog needs only one row of this shape to pay."""
    row = SkillInfo(id="s", guest_capable=True, guest_by_default=False)
    assert row.guest_capable is True and row.guest_by_default is False
    assert SkillInfo(id="s").guest_capable is True
    assert SkillInfo(id="s").guest_by_default is True


def test_a_catalog_row_is_frozen():
    with pytest.raises(Exception):
        SkillInfo(id="s").id = "other"          # type: ignore[misc]


# ── TenantSkill + its store: the row that survives being switched off ────────────────────


def test_a_decision_defaults_to_on_and_staff_only():
    row = TenantSkill(tenant_id="t", skill_id="s")
    assert row.enabled is True and row.can_guest is False


async def test_disable_KEEPS_the_row_instead_of_deleting_it():
    """The defect this field exists for: with deletion, "the admin turned this off" and "this
    was never seeded" are the same state in the store, so no backfill can tell them apart."""
    store = InMemoryTenantSkillStore()
    await store.enable("t", "s", can_guest=True)
    await store.disable("t", "s")
    rows = await store.list_skills("t")
    assert [(r.skill_id, r.enabled, r.can_guest) for r in rows] == [("s", False, True)]


async def test_the_control_forget_is_what_deletion_looks_like():
    """Without this row the one above would only prove that SOMETHING is stored. ``forget`` is
    the operation that really removes — and it is a seed's rollback, never an admin action."""
    store = InMemoryTenantSkillStore()
    await store.enable("t", "s")
    assert await store.forget("t", "s") is True
    assert await store.list_skills("t") == []
    assert await store.forget("t", "s") is False


async def test_disabling_a_skill_with_no_row_yet_still_records_the_decision():
    """The case a backfill exists for: the catalog gained a skill after this tenant was seeded.
    Recording nothing would let the next seed resurrect it."""
    store = InMemoryTenantSkillStore()
    assert await store.disable("t", "unseeded") is True
    rows = await store.list_skills("t")
    assert [(r.skill_id, r.enabled) for r in rows] == [("unseeded", False)]


async def test_disabling_twice_reports_no_change():
    store = InMemoryTenantSkillStore()
    await store.enable("t", "s")
    assert await store.disable("t", "s") is True
    assert await store.disable("t", "s") is False


@pytest.mark.parametrize("setup,call,changed", [
    (None, {"can_guest": False}, True),                        # newly enabled
    ({"disable": True}, {"can_guest": False}, True),           # re-enabled
    ({"can_guest": False}, {"can_guest": True}, True),         # guest access flipped
    ({"can_guest": True}, {"can_guest": True}, False),         # nothing moved
])
async def test_enable_reports_whether_anything_actually_changed(setup, call, changed):
    """``enable`` is not a setter that always says yes: a caller that logs, audits or bills on
    a change needs the three real changes separated from the no-op."""
    store = InMemoryTenantSkillStore()
    if setup is not None:
        await store.enable("t", "s", can_guest=setup.get("can_guest", False))
        if setup.get("disable"):
            await store.disable("t", "s")
    assert await store.enable("t", "s", **call) is changed


async def test_record_writes_the_whole_row_in_one_go():
    """The seed's write. "enable then disable" is two commits, and a process death between them
    left a premium skill switched ON for a tenant that never bought it — permanently, because a
    seed's idempotency skips ids that already exist."""
    store = InMemoryTenantSkillStore()
    await store.record(TenantSkill("t", "s", can_guest=True, enabled=False))
    rows = await store.list_skills("t")
    assert [(r.enabled, r.can_guest) for r in rows] == [(False, True)]


async def test_listing_is_scoped_to_one_tenant():
    store = InMemoryTenantSkillStore()
    await store.enable("t1", "s")
    await store.enable("t2", "s")
    assert [r.tenant_id for r in await store.list_skills("t1")] == ["t1"]


async def test_the_store_returns_disabled_rows_too():
    """A store that hid them would recreate the very ambiguity ``enabled`` removes."""
    store = InMemoryTenantSkillStore()
    await store.enable("t", "on")
    await store.enable("t", "off")
    await store.disable("t", "off")
    assert sorted(r.skill_id for r in await store.list_skills("t")) == ["off", "on"]


def test_the_in_memory_default_satisfies_the_port():
    assert isinstance(InMemoryTenantSkillStore(), TenantSkillStore)


# ── persona bindings: the full sync, and the empty set that is a full delete ─────────────


@pytest.mark.parametrize("requested,stored,allow_clear,refused", [
    ([], ["a", "b"], False, True),      # the blind wipe
    ([], ["a", "b"], True, False),      # the caller said so
    ([], [], False, False),             # honest no-op: deletes nothing
    (["a"], ["a", "b"], False, False),  # a narrowing sync is a decision, not a wipe
    (["a"], [], False, False),          # first write
])
def test_refuses_clear_is_the_whole_truth_table(requested, stored, allow_clear, refused):
    """Pure, so the two stores that must agree about it can be measured without a database."""
    assert refuses_clear(requested, stored, allow_clear=allow_clear) is refused


async def test_an_empty_set_over_a_persona_that_HAS_bindings_is_refused():
    """Measured, not imagined: an admin panel loaded a persona's bindings lazily and saved from
    another tab, so the save posted the set it had never read — five bindings to zero, with a
    green toast. The refusal lives at the waist every writer passes."""
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", ["a", "b"])
    with pytest.raises(PersonaSkillClearRefused) as excinfo:
        await store.set_skills(CORE_SCOPE, "p", [])
    assert await store.list_skills(CORE_SCOPE, "p") == ["a", "b"]
    assert excinfo.value.stored == ["a", "b"]
    assert excinfo.value.scope == CORE_SCOPE and excinfo.value.persona_id == "p"


def test_the_refusal_names_what_it_SPARED():
    """A bare "conflict" tells the operator nothing. The list they were about to lose is the
    whole point of raising instead of returning False."""
    message = str(PersonaSkillClearRefused("t1", "p", ["a", "b"]))
    assert "2 persona_skills binding(s)" in message
    assert "a, b" in message and "'p'" in message and "'t1'" in message
    assert "allow_clear=True" in message


async def test_a_caller_that_MEANT_to_clear_gets_the_old_behaviour():
    """The default protects the accidental caller; the deliberate one — a migration that mirrors
    a global row into each tenant and then clears the global — says so and is obeyed."""
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", ["a"])
    await store.set_skills(CORE_SCOPE, "p", [], allow_clear=True)
    assert await store.list_skills(CORE_SCOPE, "p") == []


async def test_an_empty_set_over_a_persona_with_nothing_is_allowed():
    """It deletes nothing. Refusing it would turn a harmless idempotent write into an error
    every caller has to special-case."""
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", [])
    assert await store.list_skills(CORE_SCOPE, "p") == []


async def test_a_set_is_a_FULL_SYNC_and_ids_missing_from_it_are_removed():
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", ["a", "b", "c"])
    await store.set_skills(CORE_SCOPE, "p", ["b"])
    assert await store.list_skills(CORE_SCOPE, "p") == ["b"]


async def test_the_core_scope_and_a_tenant_scope_are_different_bindings():
    """``scope=""`` is the global binding on the base persona; ``scope=<tenant>`` is one
    tenant's extra. A tenant that adds a skill must not touch what every tenant gets."""
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", ["core"])
    await store.set_skills("t1", "p", ["extra"])
    assert await store.list_skills(CORE_SCOPE, "p") == ["core"]
    assert await store.list_skills("t1", "p") == ["extra"]
    assert await store.list_skills("t2", "p") == []


async def test_bindings_are_listed_sorted_and_deduplicated():
    """Two workers must render the same persona, and a set's iteration order does not survive
    between processes — CPython randomises string hashing per interpreter — so the read sorts.

    Twelve ids, not three: with three short strings a set very often iterates in sorted order
    anyway, and the assertion then passes over a store that never sorted. (Measured: dropping the
    ``sorted`` left the three-id version of this test green.) Twelve leaves a 1-in-12! chance of
    the same coincidence."""
    ids = [f"s{n:02d}" for n in range(12)]
    store = InMemoryPersonaSkillStore()
    await store.set_skills(CORE_SCOPE, "p", list(reversed(ids)) + [ids[0]])
    assert await store.list_skills(CORE_SCOPE, "p") == ids


async def test_an_unknown_persona_reads_as_empty_not_as_an_error():
    store = InMemoryPersonaSkillStore()
    assert await store.list_skills(CORE_SCOPE, "never-seen") == []


def test_the_in_memory_binding_store_satisfies_the_port():
    assert isinstance(InMemoryPersonaSkillStore(), PersonaSkillStore)


def test_the_core_scope_is_the_empty_string_and_that_is_load_bearing():
    """It has to be a value no tenant id can ever be, because the two live in the same key."""
    assert CORE_SCOPE == ""
