"""
cogno_persona.compose — pure assembly of a persona's effective prompt.

The parent's ``_get_effective_system_prompt`` mixed prompt assembly with infra
(CoreDB lookups, channel context, env vars, MCP file paths). This is the **pure
core** of that: given a ``Persona`` (+ optional global base prompt + a context
dict), produce the final text for a stage slot — placeholder substitution and a
mandatory ``custom_rules`` block, nothing else. Channel brevity, language pins,
correction feedback, UI manuals etc. stay host concerns (append them yourself).
"""

from __future__ import annotations

import re
from typing import Mapping, Optional

from cogno_persona.config_keys import render_config_keys
from cogno_persona.types import Persona

# Header for the tenant-authored rules appended to the execution prompt.
CUSTOM_RULES_HEADER = (
    "## ⚠️ Custom Rules (MANDATORY)\n"
    "The following rules were defined by the business owner. You MUST follow them "
    "strictly without exception:"
)

_PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


def render(template: str, context: Optional[Mapping[str, str]] = None) -> str:
    """Substitute ``{name}`` placeholders from ``context``; unknown ones are left intact.

    Safe by design (no ``str.format``): a stray ``{json}`` in a prompt won't raise.
    """
    if not context:
        return template
    return _PLACEHOLDER.sub(
        lambda m: str(context.get(m.group(1), m.group(0))), template
    )


def compose_prompt(
    persona: Persona,
    slot: str,
    *,
    base: str = "",
    context: Optional[Mapping[str, str]] = None,
    append_rules: bool = True,
) -> str:
    """Build the final prompt text for one stage slot.

    Order: ``base`` (optional global rules) → the persona's slot prompt → the DECLARED
    configuration block → the ``custom_rules`` block (both only for the ``system``/execution
    slot when ``append_rules``, and only when there is something to render) →
    ``{placeholder}`` substitution last so it reaches every section.

    The declared keys go BEFORE the prose, and that order is the point rather than a
    preference: ``custom_rules`` is where a tenant's settings live TODAY, so a persona
    part-migrated to declared keys has the same fact in both places for a while. Whichever
    comes second reads as the correction of the first, and the declaration is the half a tool
    also acts on — a model told one rate and a tool given another is the divergence this
    module exists to close, so the prose must not be the last word about a declared key.

    ``config_keys`` renders through :func:`~cogno_persona.config_keys.render_config_keys`,
    which is expressed over the SAME by-name mapping a tool reads: a key that no tool can ask
    for by name cannot appear here, by construction and not by convention.
    """
    parts = []
    if base.strip():
        parts.append(base.strip())
    slot_text = persona.prompt(slot).strip()
    if slot_text:
        parts.append(slot_text)
    if append_rules and slot == "system":
        block = render_config_keys(persona.config_keys)
        if block:
            parts.append(block)
    if append_rules and slot == "system" and persona.custom_rules.strip():
        parts.append(f"{CUSTOM_RULES_HEADER}\n\n{persona.custom_rules.strip()}")
    return render("\n\n".join(parts), context)
