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
only — WHICH skills exist is the host's catalog), and ``config_keys``: configuration a
persona DECLARES as typed name/value pairs, read BOTH by the model (a prompt block) and
by the tools (by name) from ONE declaration — prose only ever had the first reader.
The four prompt slots line up with the cogno-anima stage signatures — the
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
from cogno_persona.config_keys import (
    CONFIG_DROP_REASONS,
    CONFIG_KEY_TYPES,
    CONFIG_KEYS_HEADER,
    MAX_CONFIG_CARRIER_CHARS,
    MAX_CONFIG_KEYS,
    MAX_CONFIG_LABEL_CHARS,
    MAX_CONFIG_NAME_CHARS,
    MAX_CONFIG_VALUE_CHARS,
    ConfigKey,
    DroppedKey,
    config_values,
    render_config_keys,
    sanitize_config_keys,
)
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
    # config keys (the mechanism; WHICH keys a persona carries is the host's)
    "ConfigKey",
    "DroppedKey",
    "CONFIG_KEY_TYPES",
    "CONFIG_DROP_REASONS",
    "CONFIG_KEYS_HEADER",
    "MAX_CONFIG_KEYS",
    "MAX_CONFIG_NAME_CHARS",
    "MAX_CONFIG_VALUE_CHARS",
    "MAX_CONFIG_LABEL_CHARS",
    "MAX_CONFIG_CARRIER_CHARS",
    "sanitize_config_keys",
    "config_values",
    "render_config_keys",
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
