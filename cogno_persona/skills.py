"""
cogno_persona.skills — which skills a persona has, and which a tenant has switched on.

``allowed_modules`` binds a persona to whole VERTICALS by name. This module is the other,
finer binding the same declaration layer needs: individual skills, bound to a persona and
gated per tenant. Like :mod:`cogno_persona.capabilities`, what ships here is the **mechanism**
— the shapes, the ports, the in-memory defaults and the two pure decisions. **The catalog is
the host's**: which skills exist, what each one does, which are premium, which a plan forbids,
which role may reach them. Nothing here names a skill, and nothing here should.

Three things, and they answer three different questions:

* :class:`SkillInfo` + :func:`skill_tier` — *what IS this skill?* One row of the deployment's
  global catalog, carrying the flags that gate it, and the one function that reads a single
  CLASS off those flags instead of letting every consumer re-read three booleans.
* :class:`TenantSkill` + :class:`TenantSkillStore` — *has this tenant switched it on, and may a
  guest use it?* Keyed by ``(tenant_id, skill_id)``.
* :data:`CORE_SCOPE` + :class:`PersonaSkillStore` — *which skills is this persona bound to?*
  Keyed by ``(scope, persona_id)``, where ``scope=""`` is a global binding on the base persona
  and ``scope=<tenant_id>`` is one tenant's extra.

Both stores are async ``Protocol``s with a zero-dependency in-memory default — the same seam
:class:`cogno_persona.store.PersonaStore` uses, so a host plugs its own relational adapter in
and keeps the tests it already has.

**The two rules that travel with them are here because each caller was getting them wrong
alone**, which is the whole argument for a shared mechanism:

1. A binding row's PRESENCE used to mean "on", and disabling deleted it — so "the admin turned
   this off" and "this was never seeded" were the same state in the database. Nothing could tell
   them apart, so every backfill was guessing; three attempts produced three different production
   defects. :attr:`TenantSkill.enabled` is why the row survives being switched off.
2. A full sync of the EMPTY set is a DELETE of everything. Set writes are full syncs (the payload
   is the desired list; missing ids are removed), and a caller that posts a set it never READ
   posts ``[]``. Measured: an admin panel that loaded a persona's bindings lazily, and saved from
   a different tab, wiped five of them and showed a green toast. The refusal therefore lives at
   the one waist every writer passes — the API route, the seed, a migration, a script nobody has
   written yet — as :func:`refuses_clear`, and not as a comment each of them re-derives.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable


@dataclass(frozen=True)
class SkillInfo:
    """One row of the deployment's global skill catalog. ``id`` is the stable skill name the
    tenant enablement and the persona bindings both reference.

    The display fields and the three gating flags are here because the catalog is what the
    admin surface renders; the flags' MEANING (what "premium" costs, which plan grants it) is
    the host's, and this library never asks.
    """

    id: str
    name: str = ""
    description: str = ""
    is_premium: bool = False
    is_system: bool = False
    is_default: bool = False
    # Can a GUEST ever use it? False for skills whose source the host never builds for an
    # unauthenticated identity — the UI then hides the can_guest toggle instead of showing a
    # switch that could never take effect.
    guest_capable: bool = True
    # Does it START open to guests? Distinct from ``guest_capable``: that one answers whether
    # the switch EXISTS, this one answers where the seed leaves it. Collapsing them forces a
    # false choice — hide a toggle the admin should have, or hand out third-party data by
    # default — and a catalog needs only ONE skill of that shape for the collapse to cost.
    guest_by_default: bool = True


# ── the ONE gating class ─────────────────────────────────────────────────────────────
# ``system`` | ``default`` | ``premium``. Three boxes and no fourth. Everything that gates a
# skill — an admin panel, a persona-binding filter, a plan gate — reads the class from HERE, off
# the catalog row, so there is never a second named list to drift from the first.
SKILL_TIERS: "tuple[str, ...]" = ("system", "default", "premium")


def skill_tier(info: "SkillInfo") -> str:
    """The skill's ONE class, or ``""`` when the flags do not name exactly one.

    ``""`` is returned for BOTH failure shapes and they are genuinely different mistakes —
    no flag at all (a new skill nobody classified) and two flags at once (``is_default`` AND
    ``is_premium``, whose gates are opposite: one is opt-in, the other opt-in PLUS a paid
    plan). A predicate that only asked "is it present" would pass the second, so the class is
    read as a single value instead of three booleans, and every consumer inherits the check.

    Callers must treat ``""`` as NOT system — the unnarrowable floor is the one answer an
    unclassified skill must never get by accident. A deployment is expected to refuse a catalog
    that produces it at all, so the runtime branch is a belt beside a brace.
    """
    named = [tier for tier, on in (("system", info.is_system),
                                   ("default", info.is_default),
                                   ("premium", info.is_premium)) if on]
    return named[0] if len(named) == 1 else ""


@dataclass(frozen=True)
class TenantSkill:
    """A tenant's DECISION about one skill. ``can_guest`` — may an unauthenticated GUEST use it.

    ``enabled`` exists because the row's mere PRESENCE used to mean "on", and disabling
    deleted it — so "the admin turned this off" and "this was never seeded" were the same
    state in the database. Nothing could tell them apart, and every backfill was therefore
    guessing: three attempts produced three different production defects (re-enabling a
    capability a tenant had closed, then revoking every other default, then re-enabling it
    again). The row is the decision; it survives being switched off, and ``can_guest`` is
    remembered for when it comes back."""

    tenant_id: str
    skill_id: str
    can_guest: bool = False
    enabled: bool = True


@runtime_checkable
class TenantSkillStore(Protocol):
    """Per-(tenant, skill) enablement. Async — real adapters do I/O."""

    # Returns EVERY decision, enabled or not — callers filter on ``enabled``. A store that
    # hid the disabled rows would recreate the ambiguity this model exists to remove.
    async def list_skills(self, tenant_id: str) -> list[TenantSkill]: ...
    async def enable(self, tenant_id: str, skill_id: str, *, can_guest: bool = False) -> bool: ...
    async def disable(self, tenant_id: str, skill_id: str) -> bool: ...
    # ATOMIC full-row upsert — the seed's write. It exists because "enable then disable"
    # is two commits, and a process death between them left a premium skill switched ON
    # for a free tenant, permanently (a seed's idempotency skips existing rows, so no
    # rerun ever repaired it). One write, no window.
    async def record(self, skill: TenantSkill) -> None: ...
    # REMOVE the row entirely — the only legitimate caller is a seed's own rollback, undoing
    # writes it just made. ``disable`` cannot serve there: it now KEEPS the row, so a
    # half-failed seed would leave the tenant "curated with everything off", stranding its
    # guests in a state no later seed repairs (the ids are already present). Not an admin
    # operation: an admin turning something off is ``disable``, and that decision must persist.
    async def forget(self, tenant_id: str, skill_id: str) -> bool: ...


class InMemoryTenantSkillStore:
    """Process-local tenant-skill enablement — dev/test. Production injects a real adapter."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], TenantSkill] = {}   # (tenant, skill) → row

    async def list_skills(self, tenant_id: str) -> list[TenantSkill]:
        return [s for (t, _s), s in self._by_key.items() if t == tenant_id]

    async def enable(self, tenant_id: str, skill_id: str, *, can_guest: bool = False) -> bool:
        # changed = newly enabled, re-enabled, or can_guest flipped
        prev = self._by_key.get((tenant_id, skill_id))
        self._by_key[(tenant_id, skill_id)] = TenantSkill(tenant_id, skill_id, can_guest,
                                                          enabled=True)
        return prev is None or not prev.enabled or prev.can_guest != can_guest

    async def forget(self, tenant_id: str, skill_id: str) -> bool:
        return self._by_key.pop((tenant_id, skill_id), None) is not None

    async def record(self, skill: TenantSkill) -> None:
        self._by_key[(skill.tenant_id, skill.skill_id)] = skill

    async def disable(self, tenant_id: str, skill_id: str) -> bool:
        prev = self._by_key.get((tenant_id, skill_id))
        if prev is not None and not prev.enabled:
            return False
        # UPSERT, not update: switching OFF a skill the tenant has no row for yet (the catalog
        # gained it after this tenant was seeded — the very case a backfill exists for) is
        # still a decision, and recording nothing let the next seed resurrect it.
        # KEEP the row and its can_guest: it is the admin's decision, not its absence.
        self._by_key[(tenant_id, skill_id)] = TenantSkill(
            tenant_id, skill_id, prev.can_guest if prev else False, enabled=False)
        return True


# scope sentinel for a core (global, persona-level) binding — distinct from any tenant_id.
CORE_SCOPE = ""


class PersonaSkillClearRefused(Exception):
    """A full sync of the EMPTY set would have deleted bindings that exist.

    Raised by every :class:`PersonaSkillStore` implementation instead of performing the delete.
    Carries the scope/persona and the ids that were SPARED, so the caller can say what it
    refused to destroy — an admin API turns this into a 409 naming them, and the operator reads
    the list they were about to lose rather than a bare "conflict".
    """

    def __init__(self, scope: str, persona_id: str, stored: "Sequence[str]") -> None:
        self.scope = scope
        self.persona_id = persona_id
        self.stored = list(stored)
        super().__init__(
            f"refusing to clear {len(self.stored)} persona_skills binding(s) for "
            f"persona={persona_id!r} scope={scope!r} ({', '.join(self.stored)}): an empty set is "
            f"a full delete. Pass allow_clear=True if erasing them is what you meant.")


def refuses_clear(requested: "Sequence[str]", stored: "Sequence[str]", *,
                  allow_clear: bool) -> bool:
    """THE decision, once, so two stores can never disagree about it.

    ``True`` when this write is a blind wipe: nothing requested, something stored, no explicit
    consent. Pure — takes the two sets and the flag, touches no I/O — so the twins can be
    measured without a database.

    ``allow_clear=False`` is the default precisely because the accidental caller is the one that
    never thought about clearing; a caller that DID think passes ``True`` and gets the old
    behaviour byte for byte (a migration that mirrors a global row into each tenant and then
    clears the global one is the deliberate shape). The empty set over a persona that has
    NOTHING is allowed: it is an honest no-op, it deletes nothing, and refusing it would turn a
    harmless idempotent write into an error every caller has to special-case.
    """
    return not allow_clear and not list(requested) and bool(list(stored))


@runtime_checkable
class PersonaSkillStore(Protocol):
    """Persona↔skill bindings (core + per-scope extras). Async — real adapters do I/O.

    ``scope`` is :data:`CORE_SCOPE` for a global binding on the base persona, or a tenant's own
    id for an extra that tenant added. Sets are **full syncs**: the payload is the complete
    desired list for that ``(scope, persona_id)``, and ids missing from it are removed — which
    is why ``allow_clear`` exists and why :func:`refuses_clear` is not optional.
    """

    async def list_skills(self, scope: str, persona_id: str) -> list[str]: ...
    async def set_skills(self, scope: str, persona_id: str, skill_ids: Sequence[str],
                         *, allow_clear: bool = False) -> None: ...


class InMemoryPersonaSkillStore:
    """Process-local persona↔skill bindings — dev/test. Production injects a real adapter."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], set[str]] = {}   # (scope, persona) → {skill_id}

    async def list_skills(self, scope: str, persona_id: str) -> list[str]:
        return sorted(self._by_key.get((scope, persona_id), set()))

    async def set_skills(self, scope: str, persona_id: str, skill_ids: Sequence[str],
                         *, allow_clear: bool = False) -> None:
        # full sync — the payload is the complete desired set for this (scope, persona)
        stored = sorted(self._by_key.get((scope, persona_id), set()))
        if refuses_clear(skill_ids, stored, allow_clear=allow_clear):
            raise PersonaSkillClearRefused(scope, persona_id, stored)
        self._by_key[(scope, persona_id)] = set(skill_ids)
