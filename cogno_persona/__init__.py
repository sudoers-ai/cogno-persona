"""
cogno-persona — the prompt store for **who a Cogno agent IS**.

Light, infra-agnostic declaration/config: the typed ``Persona`` (scope/execution/
limits/voice prompts + identity + an opaque by-name binding to allowed modules +
custom rules), a version-aware loader from disk, a ``PersonaStore`` retrieval seam
(in-memory + file defaults), an embedding-based ``PersonaSelector``, and pure
prompt ``compose`` helpers. The four prompt slots line up with the cogno-anima
stage signatures — the host loads a persona and injects its prompts into the
pipeline. This lib never executes anything: ``allowed_modules`` is just names the
host resolves into tool dispatchers (persona = declaration, praxis = execution).

Adapted from the parent cogno's ``core/prompt_loader.py`` + ``ego/persona*.py``,
with all the CoreDB/channel/env infra left to the host.
"""

from cogno_persona.compose import CUSTOM_RULES_HEADER, compose_prompt, render
from cogno_persona.loader import (
    current_version,
    list_versions,
    load_persona,
    load_prompt,
    parse_frontmatter,
)
from cogno_persona.selector import PersonaSelector, cosine
from cogno_persona.store import FilePersonaStore, InMemoryPersonaStore, PersonaStore
from cogno_persona.types import (
    PROMPT_SLOTS,
    Persona,
    PersonaPrompts,
    SelectionResult,
)

__all__ = [
    # types
    "Persona",
    "PersonaPrompts",
    "SelectionResult",
    "PROMPT_SLOTS",
    # loader
    "load_prompt",
    "load_persona",
    "list_versions",
    "current_version",
    "parse_frontmatter",
    # store
    "PersonaStore",
    "InMemoryPersonaStore",
    "FilePersonaStore",
    # selector
    "PersonaSelector",
    "cosine",
    # compose
    "compose_prompt",
    "render",
    "CUSTOM_RULES_HEADER",
]
