# Changelog

## Unreleased

### Added

- **`Persona.domains` — the subject a persona OWNS, declared.** A list in the perception
  layer's closed domain vocabulary (cogno-anima `NER_KNOWLEDGE_DOMAINS`), plus the derived
  `owned_domains` set for the membership test every consumer makes. Nothing in this lib acts
  on it: a host asking *"who owns this turn's domain?"* reads the field.

  **Declared, not derived from `allowed_modules`.** Ownership was first inferred from the tool
  binding, and that inference only holds for a persona that HAS a vertical: a prompts-only
  persona — one that interviews, sells or advises for a living — binds no module, owned nothing
  under the derived rule, and could therefore never be the target of a domain hand-over.
  Measured on a live turn: a request squarely inside such a persona's subject resolved to no
  owner at all, so the only way to reach it was to say its name.

  Values are normalised at the door (upper-cased, trimmed, de-duplicated, order kept) so
  `domains` and `owned_domains` can never disagree and a hand-written manifest compares equal
  to one an admin UI wrote; a bare string is not exploded into characters. NOT validated
  against the closed list here — this lib declares and does not perceive, so it takes no
  dependency on cogno-anima to hold a string — and two personas claiming the same domain is
  not refused: the arbitration is the host's catalogue question.

- **`cogno_persona.capabilities` — the capability engine.** A *capability* is a group of
  tools with a purpose and a way of composing them; it is declared as data
  (`Capability`, with one or more `(requires, text)` variants) and assembled into the
  block a persona's execution prompt carries. Five pieces: `validate` (structural laws —
  one heading per capability, no unreachable variant, no bridge over a tool no part
  requires), `emitting_capabilities` (fold the host's gates; a composed capability rides
  its parts' gates), `select_variant` (the strongest text the turn's tool surface
  honours — a masked tool degrades a block to a weaker AUTHORED text instead of dropping
  it), `render_capabilities` (assembly, plus `rendered` and `unavailable`).
  Exported at the package root, `validate` as `validate_capabilities`.

  The defect it removes: **a prompt that commands a tool the turn withholds** — it orders
  the model not to answer on its own and gives it nothing to call. A variant renders only
  when `requires ⊆ offered`; when none fits, `unavailable` reports what it would have
  taken, which is the fact a judge needs to tell *"there was no tool"* from *"there was a
  tool and it went unused"*.

  **The engine ships here; the TABLE does not.** Nothing in the module knows a
  capability's name, family, purpose or text — those are the host's product content, and
  every gate (`wired`/`emitting`/`offered`) is an answer the host passes in. Extracted
  from the reference host, whose rendered prompt blocks are byte-identical across the
  move.

## 0.1.0 — 2026-07-25

First public release on PyPI.

The prompt store for who a Cogno agent IS — a typed Persona (scope/execution/limits/voice prompts + by-name module binding + custom rules), version-aware loader, retrieval store, embedding selector, and pure prompt composition. Infra-agnostic, host-injected.
