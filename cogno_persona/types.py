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

from typing import Any, Dict, List

from pydantic import BaseModel, Field

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
    """

    persona_id: str
    description: str = ""
    version: str = "current"
    prompts: PersonaPrompts = Field(default_factory=PersonaPrompts)
    allowed_modules: List[str] = Field(default_factory=list)
    custom_rules: str = ""
    text_only: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def primary_module(self) -> str | None:
        """The first bound module name, or ``None`` if the persona binds none."""
        return self.allowed_modules[0] if self.allowed_modules else None

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
