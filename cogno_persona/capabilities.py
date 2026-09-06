"""
cogno_persona.capabilities — the capability ENGINE (the table is the host's).

A **capability** is a group of tools with a purpose and a way of composing them ("to
cancel a reminder, list first to get the id, then cancel"). It is declared as DATA — a
:class:`Capability` with one or more :data:`Variant` texts — instead of emitted from a
chain of ``if`` branches, and this module is the four steps that turn that data into the
block a persona's execution prompt actually carries:

    declare  → :class:`Capability` (+ ``includes``: a bridge over a union of capabilities)
    validate → :func:`validate` — the structural laws, checkable at import
    emit     → :func:`emitting_capabilities` — which capabilities this deployment/turn gates in
    select   → :func:`select_variant` — the strongest text this turn's tool surface honours
    render   → :func:`render_capabilities` — the assembled block + what had no variant at all

**Nothing here knows a capability's name, family, purpose or text.** Which capabilities
exist, what they say, which families gate them and which of those families ignore a turn's
filter are the host's — product content, declared in the host's own table and passed in.
The engine only enforces the shape and does the set arithmetic.

## The defect this exists to remove

A prompt that commands a tool the turn withholds. It orders the model not to answer on its
own and gives it nothing to call, which is the under-acting failure the rest of a Cogno
stack fights. The engine closes it structurally: a variant declares the tools its text
names (``requires``), :func:`render_capabilities` renders a variant only when
``requires ⊆ offered``, and a host test that asserts every tool a text NAMES is in that
variant's ``requires`` completes the chain — a rendered block can then never command an
absent tool.

## Availability is DERIVED, never declared

Nothing here gates anything. The host says which families its deployment was BUILT with
and which the turn actually builds a source for; the real tool surface decides which
variant (if any) renders. Gates never read a capability table; a capability table never
reads a gate.

## Variants, and why the strongest is first

A capability at different strengths is ONE capability: its variants share a heading, and
exactly one of them renders. A masked tool therefore degrades a block to a weaker,
AUTHORED text instead of dropping it. The order is preference order — the fullest first —
and a later variant that requires everything an earlier one does can never win, which
:func:`validate` rejects as dead text.

## Composition (``includes``)

A composed capability is the union A ∪ B = C: its parts keep rendering on their own, in
their own table slots, under their own gates, and the composed entry adds only the BRIDGE
— the text that teaches how the parts work together. It emits only when every part emits,
renders only when every part rendered its PRIMARY variant on this very page, and has no
family of its own: the parts carry the gates, so losing one part degrades the union to the
other part with no bridge, never to a bridge over an absent tool.

## What ``unavailable`` is for

When NO variant fits, every one of them needs a tool this turn does not have — and that
subtraction is a FACT worth handing to a judge. Without it a reviewer of the turn cannot
tell "there was no tool" from "there was a tool and it went unused": both look like *(no
tools executed)*, and only one of them makes "I can't do that" an honest reply. What
crosses is the fact (:class:`MissingCapability`), never the prose.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Container, Iterable, Mapping, Optional, Sequence

__all__ = [
    "Variant",
    "Capability",
    "MissingCapability",
    "CapabilityRender",
    "validate",
    "emitting_capabilities",
    "select_variant",
    "render_capabilities",
]

# (tools the text commands, the prompt block). The first line of the block is its heading.
Variant = tuple[frozenset[str], str]


@dataclass(frozen=True)
class Capability:
    """One capability block with the tools it commands, in preference order of variants.

    ``family`` is the gate the block rides — the host says which families its deployment
    wired and which the turn offers. ``variants`` is ordered: the first one whose
    ``requires`` the turn actually offers is the one rendered.

    ``includes`` makes a COMPOSED capability — the union A ∪ B = C. Its parts keep
    rendering on their own, under their own gates; the composed entry adds only the BRIDGE
    (its ``variants``). The bridge emits only when every part emits, renders only when
    every part rendered AND its own ``requires`` fit the surface, and has no family of its
    own.
    """

    name: str
    purpose: str
    family: str                         # "" on a composed capability: it has none of its own
    variants: tuple[Variant, ...]
    includes: tuple[str, ...] = ()

    @property
    def is_composed(self) -> bool:
        return bool(self.includes)

    def parts_in(self, seen: "Container[str]") -> bool:
        """Did every part make it into ``seen``? ONE fold for both stages of composition —
        the emit stage folds over the capabilities that emitted, the render stage over the
        ones that rendered their PRIMARY variant."""
        return all(part in seen for part in self.includes)


@dataclass(frozen=True)
class MissingCapability:
    """A capability that emitted and could not render: no variant's ``requires`` fit.

    ``missing`` is what it would have TAKEN — the tools of the LEAST demanding variant
    that this turn does not offer. Naming the fullest variant's would overstate the gap.
    """

    capability: str
    missing: tuple[str, ...]


@dataclass(frozen=True)
class CapabilityRender:
    """The assembled block, plus the two facts about it a caller needs afterwards.

    ``text`` is what gets appended to the execution prompt (``""`` when nothing rendered).
    ``rendered`` is WHAT THIS TURN WAS ACTUALLY TOLD IT COULD DO — not what the persona is
    wired for and not what the dispatcher offers, but the capabilities whose text reached
    the prompt, after every gate. ``unavailable`` is the other half, for whoever judges the
    reply.
    """

    text: str
    rendered: tuple[str, ...]
    unavailable: tuple[MissingCapability, ...]


def validate(table: "Sequence[Capability]") -> "list[str]":
    """Structural errors in a capability table (empty when it is well-formed).

    Cross-module laws — every family is a real family, every required tool is a real
    skill, every tool a text NAMES is required — belong to whoever owns the table and the
    catalog; they cannot be checked here, and this function does not pretend to.

    A heading belongs to ONE capability (a rendered block is identified by its heading
    line, so two capabilities sharing one would be indistinguishable), while every variant
    of a capability must carry the SAME heading — one capability at different strengths,
    exactly one of them renders.
    """
    errors: "list[str]" = []
    names: "set[str]" = set()
    declared: "dict[str, Capability]" = {}   # in table order — what a part may refer to
    owner: "dict[str, str]" = {}             # heading → the capability that owns it
    for cap in table:
        if cap.name in names:
            errors.append(f"duplicate capability name {cap.name!r}")
        if not cap.purpose.strip():
            errors.append(f"{cap.name}: empty purpose")
        if not cap.variants:
            errors.append(f"{cap.name}: no variants")
        # Composition: a part must be declared EARLIER in the table. That single rule gives
        # render order (parts first, bridge after) and makes a cycle impossible to write.
        # And a bridge may only require tools its parts' PRIMARY variants require: a tool of
        # a family the union does not include would ride no gate at all — emitted whenever
        # the parts emit, silently never rendering for the roles that lack it.
        if cap.is_composed:
            if cap.family:
                errors.append(f"{cap.name}: a composed capability has no family of its own "
                              "(the parts carry the gates)")
            if len(set(cap.includes)) != len(cap.includes):
                errors.append(f"{cap.name}: a part is listed twice")
            pool: "set[str]" = set()
            for part in cap.includes:
                if part not in declared:
                    errors.append(f"{cap.name}: part {part!r} must be declared earlier in "
                                  "the table")
                elif declared[part].variants:
                    pool |= declared[part].variants[0][0]
            for req, _text in (v for v in cap.variants
                               if isinstance(v, tuple) and len(v) == 2
                               and isinstance(v[0], frozenset)):
                if not req <= pool:
                    errors.append(f"{cap.name}: bridge requires {sorted(req - pool)} which no "
                                  "part's primary variant requires")
        elif not cap.family:
            errors.append(f"{cap.name}: an atomic capability needs a family")
        names.add(cap.name)
        declared[cap.name] = cap
        own_heading: "Optional[str]" = None
        earlier: "list[frozenset[str]]" = []
        for variant in cap.variants:
            if not (isinstance(variant, tuple) and len(variant) == 2):
                errors.append(f"{cap.name}: a variant is (requires, text), got {variant!r}")
                continue
            req, text = variant
            if not isinstance(req, frozenset):
                errors.append(f"{cap.name}: requires must be a frozenset")
            else:
                # Selection takes the FIRST variant whose requires the surface honours, so a
                # later variant that requires everything an earlier one does can never win —
                # dead text, including an exact duplicate.
                if any(req >= prev for prev in earlier):
                    errors.append(f"{cap.name}: variant {len(earlier)} is unreachable — it "
                                  "requires everything an earlier variant requires")
                earlier.append(req)
            if not (isinstance(text, str) and text.startswith("## ") and "\n" in text):
                errors.append(f"{cap.name}: a variant must open with a '## heading' line")
                continue
            heading = text.split("\n", 1)[0]
            if own_heading is None:
                own_heading = heading
            elif heading != own_heading:
                errors.append(f"{cap.name}: variants must share one heading "
                              f"({own_heading!r} vs {heading!r})")
            if owner.setdefault(heading, cap.name) != cap.name:
                errors.append(f"{cap.name}: heading {heading!r} belongs to {owner[heading]!r}")
    return errors


def emitting_capabilities(table: "Sequence[Capability]", *,
                          wired: "Mapping[str, bool]",
                          emitting: "Container[str]") -> "list[Capability]":
    """The capabilities a turn may emit, in table order — the GATE stage.

    ``wired`` is what the deployment was built with, family by family; ``emitting`` the
    families this turn actually offers. Both are the caller's answers: this function only
    folds them, and a COMPOSED capability has no gate of its own — it emits exactly when
    every part emits, the parts (declared earlier) carrying the gates.

    ``wired`` is indexed STRICTLY, on purpose: a table family the wiring does not know
    raises ``KeyError`` on the first turn instead of never emitting.
    """
    out: "list[Capability]" = []
    names: "set[str]" = set()
    for cap in table:
        emits = cap.parts_in(names) if cap.is_composed else (
            wired[cap.family] and cap.family in emitting)
        if emits:
            out.append(cap)
            names.add(cap.name)
    return out


def select_variant(cap: Capability, offered: "Container[str]",
                   ) -> "Optional[tuple[int, str]]":
    """The first variant the turn can honour — every tool it requires on the table — as
    ``(index, text)``, or ``None`` (the block is dropped). Table order is preference
    order: the fullest text first (index 0), the degraded ones after it."""
    for i, (req, text) in enumerate(cap.variants):
        if all(tool in offered for tool in req):
            return i, text
    return None


def render_capabilities(caps: "Iterable[Capability]",
                        offered: "Container[str]",
                        *,
                        suffixes: "Optional[Mapping[str, str]]" = None,
                        separator: str = "\n\n") -> CapabilityRender:
    """Assemble the capability block for one turn: select, compose, join.

    ``caps`` is what already passed the gates (:func:`emitting_capabilities`), in table
    order; ``offered`` the turn's REAL tool surface. A capability renders through the first
    of its variants the surface honours; a composed capability's bridge renders only after
    every part it includes rendered its PRIMARY variant on this very page — the bridge is
    written against the parts' fullest text, and over a degraded part (or an absent one) it
    presumes a flow the page no longer instructs, so it stays out.

    ``suffixes`` is text the CALLER appends to a named capability's block — the seam for a
    block whose tail is per-turn data the table cannot hold (a list of the personas
    reachable right now, say). The engine never authors it and never inspects it; a name
    with no rendered block contributes nothing.
    """
    extra = dict(suffixes or {})
    keep: "list[str]" = []
    rendered: "list[str]" = []
    unavailable: "list[MissingCapability]" = []
    primary: "set[str]" = set()             # rendered at variant 0 — what a bridge may span
    for cap in caps:
        if cap.is_composed and not cap.parts_in(primary):
            continue
        chosen = select_variant(cap, offered)
        if chosen is None:
            # NO variant fits: every one of them needs a tool this turn does not have.
            # The tools of the LEAST demanding variant are what it would have taken —
            # naming the fullest variant's would overstate the gap.
            needed = min((req for req, _ in cap.variants), key=len, default=frozenset())
            unavailable.append(MissingCapability(
                capability=cap.name,
                missing=tuple(sorted(t for t in needed if t not in offered))))
            continue
        index, text = chosen
        tail = extra.get(cap.name, "")
        keep.append(f"{text}{tail}" if tail else text)
        if index == 0:
            primary.add(cap.name)
        rendered.append(cap.name)
    return CapabilityRender(text=separator.join(keep),
                            rendered=tuple(rendered),
                            unavailable=tuple(unavailable))
