"""
cogno_persona.config_keys — configuration a persona DECLARES: typed, named, read TWICE.

A tenant configures a persona through free prose (``custom_rules``). Anything the product did
not anticipate has nowhere else to go, and prose has exactly one reader: the model. A tool that
needs the same fact — the hourly rate, the column a total lives in, the threshold a rule turns
on — cannot ask for it by name.

This module is the declaration that both sides read:

    declare  → :class:`ConfigKey` (name, type, value, human label)
    sanitize → :func:`sanitize_config_keys` — the door; PURE, never raises, returns what it drops
    read (1) → :func:`config_values`      — the by-NAME mapping a TOOL asks
    read (2) → :func:`render_config_keys` — the prose block the MODEL reads

**Nothing here knows what a key MEANS.** Which keys a persona should carry, what they are called
and what a tool does with one are the host's and the vertical's — product content, declared in
the host's own table and passed in. This module enforces the shape and does nothing else. Same
division the :mod:`~cogno_persona.capabilities` engine and the :mod:`~cogno_persona.skills`
ports already draw: the mechanism is the library's, the catalogue is the host's.

## ONE declaration, two readings — and why that is structural, not a promise

:func:`render_config_keys` is expressed OVER :func:`config_values`. It does not re-walk the
keys and it does not re-apply the inclusion rule; it asks for the by-name mapping and renders
what came back. So a key that leaves the tool's reading leaves the prompt in the same edit, by
construction — the two cannot drift, because there is only one of them. The reverse direction
(a key in the prompt that no tool can ask for) is what `tests/unit/test_config_keys.py` pins.

This is the shape :meth:`PiiDetector.find` already has in cogno-anima, for the same reason: two
readings of one fact must not be two implementations of it.

## Why prose could not serve, measured rather than argued

The prose channel is not merely awkward for configuration; it is LOSSY, and it was measured
losing a live tenant's whole config on 2026-09-09. One vertical already parses typed keys out
of ``custom_rules`` with line-anchored regexes (``cogno_praxis.coordinator.config``: 27 call
sites over ``^KEY: value`` lines). Read straight out of the production table, that tenant's
coordinator row is **13 769 characters on ONE physical line** — 291 literal backslash-n
sequences and not a single real newline, written that way by one of the two writers this column
has. Every one of the 12 keys the tenant correctly declared is therefore invisible to a parser
anchored at ``^``: the vertical survives only because the spreadsheet scan is NOT anchored and
every other key happens to have a default. The one key with no default by design — the hourly
rate — is the one that surfaces, as ``NOT CONFIGURED``, to a professor asking what he earns.

A declaration carried as DATA cannot fail that way, because its structure is not whitespace.

## The boundary: a key is a SCALAR, long content is knowledge

:data:`MAX_CONFIG_VALUE_CHARS` is 200 and it is enforced, not advised — an over-long value is
DROPPED with reason ``too_long`` and named back to the caller, so the host's admin API can
refuse it at save time. The number is measured, not chosen: across the 22 declared ``KEY:
value`` lines in that same production row the longest value is **27 characters** and the median
13, while the row as a whole is 13 187 characters of which **5.4% is configuration** and the
rest is prose. A price table, a syllabus or a knowledge body is the other 94.6%; it belongs in
the knowledge base, which can retrieve the relevant paragraph, and not in a field every turn
pays for in full. 200 leaves that measured maximum a factor of seven of headroom and still
refuses anything a person would call a document.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Sequence, Tuple

__all__ = [
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
]

#: The closed type vocabulary. A type is a PROMISE the door checks: a ``number`` that does not
#: parse is refused HERE, at save time, in front of whoever is typing it — instead of at
#: question time, in front of the contact, as "not configured".
CONFIG_KEY_TYPES: Tuple[str, ...] = ("text", "number", "boolean")

#: Why a declaration was dropped. Closed, because the host renders these to an operator and a
#: free-form reason is a sentence nobody can act on.
CONFIG_DROP_REASONS: Tuple[str, ...] = (
    "malformed",        # not an object / unreadable carrier
    "bad_name",         # empty, or not UPPER_SNAKE within the length bound
    "unknown_type",     # not in CONFIG_KEY_TYPES
    "not_a_number",     # type="number" and the value is not one
    "not_a_boolean",    # type="boolean" and the value is not one
    "empty_value",      # declared with nothing in it — an undeclared key, said the long way
    "too_long",         # over MAX_CONFIG_VALUE_CHARS — see the module docstring
    "duplicate",        # the same name declared twice; the FIRST one wins
    "overflow",         # past MAX_CONFIG_KEYS
)

#: The heading the prompt block carries. The wording says DECLARED BY THE BUSINESS OWNER for the
#: same reason ``CUSTOM_RULES_HEADER`` does: the model must not read a tenant's configuration as
#: something the contact said, nor as something it may negotiate.
CONFIG_KEYS_HEADER = (
    "## Configuration declared by the business owner\n"
    "These are settings this business configured for you. They are FACTS, not suggestions: "
    "use these values as given and never invent, round or replace one. A value that is not "
    "listed here has not been configured — say so plainly rather than guessing it."
)

MAX_CONFIG_KEYS = 40
MAX_CONFIG_NAME_CHARS = 40
MAX_CONFIG_VALUE_CHARS = 200
MAX_CONFIG_LABEL_CHARS = 120
#: A guard on the CARRIER, so a pathological column never reaches the JSON parser. Generous
#: against the bound above: 40 keys of 200 chars, plus names, labels and JSON punctuation.
MAX_CONFIG_CARRIER_CHARS = 20_000

# UPPER_SNAKE. The by-name handle a tool spells in its own source, so it must survive a
# round trip through JSON, an env var and a prompt without a case fold changing it.
_NAME_RE = re.compile(rf"^[A-Z][A-Z0-9_]{{0,{MAX_CONFIG_NAME_CHARS - 1}}}$")
# One optional sign, digits, and AT MOST ONE separator acting as the decimal point. A comma is
# accepted because the tenants this serves write "120,00" — the same figure their invoices use.
# "1.234,56" is deliberately REFUSED rather than guessed at: a thousands separator and a decimal
# separator are the same two characters in different orders, and a library that guesses wrong
# about money is worse than one that asks. The refusal is named (``not_a_number``) and lands at
# save time, where somebody can fix it.
_NUMBER_RE = re.compile(r"^[+-]?(\d+([.,]\d+)?|[.,]\d+)$")
_TRUE = ("true", "yes", "1", "sim", "on")
_FALSE = ("false", "no", "0", "nao", "não", "off")


@dataclass(frozen=True)
class ConfigKey:
    """One declared setting: the by-name handle, its value, its type and a human label.

    ``value`` is kept as the canonical STRING the tenant typed (trimmed). It is not coerced to
    ``float``/``bool`` on the way in, because the two readings want different things — a tool
    that already parses its own config keeps working unchanged, and JSON storage stays exact —
    while :meth:`as_number` and :meth:`as_boolean` give the parsed form to whoever wants it.
    The type is not decoration: the door refused the declaration if it did not parse, so an
    accessor on a key that got through can only answer ``None`` for a type mismatch the caller
    chose (asking a ``text`` key for a number), never for a malformed value.

    ``label`` is what a PERSON calls this setting. It is what the prompt block shows beside the
    value and what an admin screen puts on the field; empty means the host has nothing better
    to say than the name, and the render then uses the name alone rather than an empty gap.
    """

    name: str
    value: str
    type: str = "text"
    label: str = ""

    def as_number(self) -> "float | None":
        """The value as a float, or ``None`` when this key is not a declared ``number``."""
        if self.type != "number":
            return None
        return float(self.value.replace(",", "."))

    def as_boolean(self) -> "bool | None":
        """The value as a bool, or ``None`` when this key is not a declared ``boolean``."""
        if self.type != "boolean":
            return None
        return self.value.strip().lower() in _TRUE


@dataclass(frozen=True)
class DroppedKey:
    """A declaration that did not get through, and WHY — for the operator, not for a log line.

    ``name`` is the declared name when there was a readable one, else a short label of the raw
    entry. ``reason`` is one of :data:`CONFIG_DROP_REASONS`.
    """

    name: str
    reason: str


def _label_of(raw: Any) -> str:
    """A short, safe stand-in for an entry with no usable name. Never the whole value."""
    text = raw if isinstance(raw, str) else type(raw).__name__
    text = " ".join(str(text).split())
    return text[:40] if len(text) <= 40 else text[:37] + "..."


def sanitize_config_keys(raw: Any) -> Tuple[Tuple[ConfigKey, ...], Tuple[DroppedKey, ...]]:
    """The door: any carrier → ``(kept, dropped)``. PURE — no logging, no I/O, never raises.

    Accepts a JSON array string (a text column read raw), an already-decoded list of mappings,
    or a list of :class:`ConfigKey`. Anything else, or a carrier past
    :data:`MAX_CONFIG_CARRIER_CHARS`, yields ``((), (DroppedKey(<label>, "malformed"),))`` —
    a tenant's malformed configuration costs that tenant its keys, never a contact their reply.

    The rules, in order, because the ORDER decides which reason an operator is shown:
    name → type → value-emptiness → type parse → length → duplicate → cap. A duplicate is
    settled BEFORE the cap so a tenant who declared the same key twice (measured: every one of
    the 12 keys in the production row is declared twice) cannot lose a DIFFERENT key to the
    overflow. The FIRST declaration of a name wins, matching what the prose parser this
    replaces already did with a repeated line.

    ``kept`` preserves declaration order: it is the order the prompt block renders in, and a
    persona whose settings reshuffle between workers is one an operator cannot proof-read.
    """
    items = _entries(raw)
    if items is None:
        return (), (DroppedKey(_label_of(raw), "malformed"),)

    kept: List[ConfigKey] = []
    dropped: List[DroppedKey] = []
    seen: set[str] = set()
    for entry in items:
        parsed = _one(entry)
        if isinstance(parsed, DroppedKey):
            dropped.append(parsed)
            continue
        if parsed.name in seen:
            dropped.append(DroppedKey(parsed.name, "duplicate"))
            continue
        if len(kept) >= MAX_CONFIG_KEYS:
            dropped.append(DroppedKey(parsed.name, "overflow"))
            continue
        seen.add(parsed.name)
        kept.append(parsed)
    return tuple(kept), tuple(dropped)


def _entries(raw: Any) -> "List[Any] | None":
    """Normalise any accepted carrier to a list of entries, or ``None`` if it is not one."""
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        if len(text) > MAX_CONFIG_CARRIER_CHARS:
            return None
        try:
            loaded = json.loads(text)
        except Exception:  # noqa: BLE001 — ValueError, RecursionError on '[' * 1e5, …
            return None
        return loaded if isinstance(loaded, list) else None
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return None


def _one(entry: Any) -> "ConfigKey | DroppedKey":
    """One entry → a validated :class:`ConfigKey`, or the :class:`DroppedKey` saying why not."""
    if isinstance(entry, ConfigKey):
        entry = {"name": entry.name, "value": entry.value,
                 "type": entry.type, "label": entry.label}
    if not isinstance(entry, Mapping):
        return DroppedKey(_label_of(entry), "malformed")

    name = entry.get("name")
    name = name.strip().upper() if isinstance(name, str) else ""
    if not _NAME_RE.match(name):
        return DroppedKey(_label_of(entry.get("name")) or "<unnamed>", "bad_name")

    ktype = entry.get("type", "text")
    ktype = ktype.strip().lower() if isinstance(ktype, str) else ""
    if ktype not in CONFIG_KEY_TYPES:
        return DroppedKey(name, "unknown_type")

    value = entry.get("value")
    if isinstance(value, bool):                 # JSON true/false for a boolean key
        value = "true" if value else "false"
    elif isinstance(value, (int, float)):       # JSON 120 / 120.0 for a number key
        value = repr(value) if isinstance(value, float) else str(value)
    value = value.strip() if isinstance(value, str) else ""
    if not value:
        # An empty value is an UNDECLARED key said the long way. Keeping it would put a blank
        # in the prompt and hand a tool an empty string where it expects a figure — the two
        # readings would then disagree about whether the tenant configured anything.
        return DroppedKey(name, "empty_value")

    if ktype == "number" and not _NUMBER_RE.match(value):
        return DroppedKey(name, "not_a_number")
    if ktype == "boolean" and value.lower() not in _TRUE + _FALSE:
        return DroppedKey(name, "not_a_boolean")
    if len(value) > MAX_CONFIG_VALUE_CHARS:
        return DroppedKey(name, "too_long")

    label = entry.get("label")
    label = " ".join(label.split())[:MAX_CONFIG_LABEL_CHARS] if isinstance(label, str) else ""
    return ConfigKey(name=name, value=value, type=ktype, label=label)


def config_values(keys: Sequence[ConfigKey]) -> Dict[str, str]:
    """READING ONE — what a TOOL asks: ``{NAME: value}``, by name, no prose to parse.

    Plain strings, because that is what the consumers this replaces already hold: the vertical
    parsers pull strings out of the rules text and coerce them themselves, so a vertical can
    move onto declared keys by changing where the string comes from and nothing else. A caller
    that wants the parsed form has :meth:`ConfigKey.as_number` / :meth:`ConfigKey.as_boolean`.

    This is the SOURCE of the other reading too — see :func:`render_config_keys`.
    """
    return {key.name: key.value for key in keys}


def render_config_keys(keys: Sequence[ConfigKey], *,
                       header: str = CONFIG_KEYS_HEADER) -> str:
    """READING TWO — what the MODEL reads: the prompt block. ``""`` when nothing is declared.

    **Expressed over :func:`config_values`**, deliberately and structurally: this function does
    not walk ``keys`` to decide what is readable, it asks for the by-name mapping and renders
    exactly what came back. A key the tool reading loses therefore leaves the prompt in the same
    edit — the two readings cannot drift, because the inclusion rule exists once. ``keys`` is
    consulted only for the LABEL and the TYPE, which are how a person and a model read a value
    that a tool takes by name.

    An empty block returns ``""`` rather than a lone header: a heading over nothing tells the
    model this business configured settings and then shows it none, which is worse than silence.
    """
    values = config_values(keys)
    if not values:
        return ""
    by_name = {key.name: key for key in keys}
    lines = [header, ""]
    for name, value in values.items():
        key = by_name[name]
        label = key.label or name
        suffix = "" if key.type == "text" else f" ({key.type})"
        lines.append(f"- **{label}**{suffix}: {value}   [{name}]")
    return "\n".join(lines)
