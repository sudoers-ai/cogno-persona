"""
cogno-persona — the prompt store for **who a Cogno agent IS**.

Light, infra-agnostic declaration/config: the typed ``Persona`` (scope/execution/
limits/voice prompts + identity + an opaque by-name binding to allowed modules +
custom rules), a version-aware loader from disk, a ``PersonaStore`` retrieval seam
(in-memory + file defaults), an embedding-based ``PersonaSelector``, pure prompt
``compose`` helpers, a ``capabilities`` engine that turns a host's own
declared capability table into the block a persona's execution prompt carries (the
ENGINE is here; the TABLE — which capabilities exist and what they say — is the
host's), and a ``skills`` layer for the finer binding: the catalog row's shape, the
per-tenant enablement port and the persona↔skill binding port (again the mechanism
only — WHICH skills exist is the host's catalog). The four prompt slots line up with the cogno-anima stage signatures — the
host loads a persona and injects its prompts into the pipeline. This lib never
executes anything: ``allowed_modules`` is just names the host resolves into tool
dispatchers (persona = declaration, praxis = execution).

Adapted from the parent cogno's ``core/prompt_loader.py`` + ``ego/persona*.py``,
with all the CoreDB/channel/env infra left to the host.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version

try:
    __version__ = _dist_version("cogno-persona")
except PackageNotFoundError:  # source tree without an installed dist (e.g. vendored checkout)
    __version__ = "0.0.0"


from cogno_persona.capabilities import (
    Capability,
    CapabilityRender,
    MissingCapability,
    Variant,
    emitting_capabilities,
    render_capabilities,
    select_variant,
)
from cogno_persona.capabilities import validate as validate_capabilities
from cogno_persona.compose import CUSTOM_RULES_HEADER, compose_prompt, render
from cogno_persona.loader import (
    current_version,
    list_versions,
    load_persona,
    load_prompt,
    parse_frontmatter,
)
from cogno_persona.selector import PersonaSelector, Reranker, cosine
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
    "Reranker",
    "cosine",
    # compose
    "compose_prompt",
    "render",
    "CUSTOM_RULES_HEADER",
    # capabilities (the engine; the table is the host's)
    "Capability",
    "Variant",
    "MissingCapability",
    "CapabilityRender",
    "validate_capabilities",
    "emitting_capabilities",
    "select_variant",
    "render_capabilities",
    # skills (the ports + the two rules; the CATALOG is the host's)
    "SkillInfo",
    "SKILL_TIERS",
    "skill_tier",
    "TenantSkill",
    "TenantSkillStore",
    "InMemoryTenantSkillStore",
    "CORE_SCOPE",
    "PersonaSkillStore",
    "InMemoryPersonaSkillStore",
    "PersonaSkillClearRefused",
    "refuses_clear",
]
