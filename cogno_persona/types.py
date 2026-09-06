"""
cogno_persona.types — the typed container for **who the agent IS**.

A ``Persona`` is light declaration/config, not execution: the prompts that define
an agent's scope, execution behaviour, limits and voice, plus its identity, an
opaque **binding by name** to the modules it may use (``allowed_modules`` — the
*host* resolves those names into real tool dispatchers), and any tenant custom
rules. The four prompt slots line up byte-for-byte with what the cogno-anima
stages consume:

    prompts.system  → EgoStage.process(..., system_prompt=)        (execution)
    prompts.scope   → SuperegoStage.check_input_scope(..., scope_prompt=)
    prompts.limits  → SuperegoStage.evaluate(..., limits_prompt=)
    prompts.voice   → SuperegoStage.voice(..., voice_prompt=)

No infra here: a Persona is pure data the host loads (from disk via
``cogno_persona.loader`` or its own DB) and injects into the pipeline.
"""

from __future__ import annotations

from typing import Any, Dict, FrozenSet, List

from pydantic import BaseModel, Field, field_validator

# The canonical prompt slots, in pipeline order.
PROMPT_SLOTS = ("system", "scope", "limits", "voice")


class PersonaPrompts(BaseModel):
    """The four prompt texts that define an agent's behaviour across the stages."""

    system: str = ""  # EGO execution / specialist role
    scope: str = ""   # SUPEREGO pre-EGO relevance guard (ALLOW/BLOCK)
    limits: str = ""  # SUPEREGO judge — limits & constraints
    voice: str = ""   # SUPEREGO voicer — persona voice & limits

    def get(self, slot: str) -> str:
        """Return the text for a slot name (``system``/``scope``/``limits``/``voice``)."""
        if slot not in PROMPT_SLOTS:
            raise KeyError(f"unknown prompt slot {slot!r}; valid: {PROMPT_SLOTS}")
        return getattr(self, slot)


class Persona(BaseModel):
    """A declarative agent identity: prompts + binding + rules.

    ``allowed_modules`` is an **opaque by-name** pointer (e.g. ``["veterinary"]``)
    that the host resolves into dispatchers — the persona lib never imports or
    executes anything. ``custom_rules`` are tenant-authored mandatory rules the
    composer appends to the execution prompt.

    ``domains`` is the subject matter the persona OWNS, declared — see the field.
    """

    persona_id: str
    description: str = ""
    version: str = "current"
    prompts: PersonaPrompts = Field(default_factory=PersonaPrompts)
    allowed_modules: List[str] = Field(default_factory=list)
    # ── The knowledge domains this persona OWNS, DECLARED ────────────────────────────
    #
    # The vocabulary is the perception layer's closed domain list (cogno-anima's
    # ``NER_KNOWLEDGE_DOMAINS``): a turn's domain is what the NER answers, so a persona
    # saying which of those it owns is the two halves of one join. A host asking "who
    # owns this turn's domain?" reads this field; nothing here acts on it.
    #
    # **Declared, not derived from ``allowed_modules``.** Ownership was first inferred
    # from the tool binding, and that inference is only true of a persona that HAS a
    # vertical: a prompts-only persona — one that interviews, sells or advises for a
    # living — binds no module, and under the derived rule owned nothing and could
    # therefore never be the target of a domain hand-over. Measured on a live turn: a
    # request squarely inside such a persona's subject resolved to no owner at all, so
    # the only way to reach it was to say its name. Which subject a persona owns is a
    # product decision; a tool list is an implementation detail, and the two stopped
    # agreeing the first time a persona was built out of prompts alone.
    #
    # A persona declaring none owns none — the default, and the honest reading of an
    # unanswered question. Two personas declaring the SAME domain is not resolved here:
    # this lib holds the declaration, the host owns the arbitration (an ambiguous owner
    # is a catalogue question, and refusing it at construction would make a lib refuse a
    # host's catalogue over a rule the host is the only one able to state).
    #
    # NOT validated against the closed list here, deliberately: cogno-persona declares
    # and does not perceive, so it does not depend on cogno-anima to hold a string. The
    # values are normalised (upper-cased, trimmed, de-duplicated, order kept) so that a
    # manifest written by hand and one written by an admin UI compare equal.
    domains: List[str] = Field(default_factory=list)
    custom_rules: str = ""
    text_only: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("domains", mode="before")
    @classmethod
    def _normalise_domains(cls, raw: Any) -> Any:
        """Upper-case, trim, drop blanks, de-duplicate — order preserved.

        Applied at the door so ``domains`` and :attr:`owned_domains` can never disagree
        and no consumer re-derives the normalisation. A non-sequence is left to
        pydantic's own type error; a plain string is NOT split (``"MARKETING"`` is one
        domain, not nine characters).

        A ``set``/``frozenset`` is SORTED first: its iteration order varies between
        processes, and the same persona must not come out of two workers with its
        domains in two different orders (the rule cogno-anima's
        ``sanitize_voice_traits`` already follows, for the same reason).
        """
        if isinstance(raw, str) or not isinstance(raw, (list, tuple, set, frozenset)):
            return raw
        items = sorted(raw, key=str) if isinstance(raw, (set, frozenset)) else raw
        seen: List[str] = []
        for item in items:
            if not isinstance(item, str):
                return raw          # let pydantic report the real type error
            value = item.strip().upper()
            if value and value not in seen:
                seen.append(value)
        return seen

    @property
    def primary_module(self) -> str | None:
        """The first bound module name, or ``None`` if the persona binds none."""
        return self.allowed_modules[0] if self.allowed_modules else None

    @property
    def owned_domains(self) -> FrozenSet[str]:
        """The declared domains as a set, for the membership test every consumer makes."""
        return frozenset(self.domains)

    def prompt(self, slot: str) -> str:
        """Shortcut for ``persona.prompts.get(slot)``."""
        return self.prompts.get(slot)


class SelectionResult(BaseModel):
    """The outcome of ``PersonaSelector.select``.

    ``matched`` is ``True`` when an embedding candidate cleared the threshold;
    ``False`` means the selector fell back to the base persona. ``scores`` lists
    every ``(persona_id, score)`` considered (highest first), for observability.
    """

    persona_id: str
    score: float = 0.0
    matched: bool = False
    scores: List[tuple[str, float]] = Field(default_factory=list)
