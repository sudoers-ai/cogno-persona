# cogno-persona

**The prompt store for who a Cogno agent *is*.** A light, infra-agnostic library
that models an agent's **declaration** — the prompts that define its scope,
execution behaviour, limits and voice, plus its identity, an opaque by-name binding
to the modules it may use, and any tenant custom rules.

> Persona = **declaration** ("who the agent is / may do"). It does **not** execute
> anything — `allowed_modules` is just *names* the host resolves into real tool
> dispatchers. Execution ("what it does") is a separate concern (cogno-praxis).

Distilled from the parent Cogno's `core/prompt_loader.py` + `ego/persona*.py`, with
all the CoreDB / channel / env infra left to the host.

## Why

The four prompt slots line up **byte-for-byte** with what the cogno-anima stages
consume, so a host loads a persona and injects its prompts straight into the pipeline:

| `persona.prompts.*` | consumed by |
|---|---|
| `system` | `EgoStage.process(..., system_prompt=)` — execution |
| `scope`  | `SuperegoStage.check_input_scope(..., scope_prompt=)` |
| `limits` | `SuperegoStage.evaluate(..., limits_prompt=)` |
| `voice`  | `SuperegoStage.voice(..., voice_prompt=)` |

## Install

```bash
pip install cogno-persona          # model + loader + store + selector + compose + capabilities + config keys
pip install "cogno-persona[yaml]"  # + YAML frontmatter parsing in prompts
```

## Seven pieces

### 1. `Persona` — the typed container (pydantic)

```python
from cogno_persona import Persona, PersonaPrompts

vet = Persona(
    persona_id="VETERINARY",
    description="pet health specialist",
    allowed_modules=["veterinary", "scheduler"],   # by-name binding (host resolves)
    domains=["HEALTH"],                            # the subject it OWNS (NER vocabulary)
    custom_rules="Always confirm the pet's name first.",
    prompts=PersonaPrompts(system="You are the vet…", scope="…", limits="…", voice="…"),
)
vet.primary_module          # "veterinary"
vet.owned_domains           # frozenset({"HEALTH"})
vet.prompt("voice")         # the voice prompt text
```

`domains` is **declared, not derived from `allowed_modules`**: a prompts-only persona
binds no module and would otherwise own nothing, so the only way to reach it is to say
its name. Values are normalised (upper-cased, trimmed, de-duplicated) and are the
perception layer's closed domain vocabulary (cogno-anima `NER_KNOWLEDGE_DOMAINS`) — this
lib does not import it to hold a string, and does not arbitrate two personas claiming the
same domain: that is the host's catalogue question.

### 2. `loader` — version-aware loading from disk

```python
from cogno_persona import load_persona, load_prompt

vet = load_persona("personas/VETERINARY")           # manifest + slot files
vet = load_persona("personas/VETERINARY", version="v1")  # pin a prompt version
text = load_prompt("prompts", "voice.txt", stage="superego", version="v2")
```

A prompt may carry a sibling `<name>_meta.json` mapping version labels → files;
`list_versions` / `current_version` introspect it.

### 3. `store` — the retrieval seam (homeo pattern)

```python
from cogno_persona import FilePersonaStore, InMemoryPersonaStore, PersonaStore

store = FilePersonaStore("personas/")        # lazily loads each subdir
store = InMemoryPersonaStore([vet])          # for tests / seeding
# host implements PersonaStore over its own DB:  async get(id) / async list()
```

### 4. `PersonaSelector` — pick a specialist by embedding

```python
from cogno_persona import PersonaSelector

selector = PersonaSelector(embedder, threshold=0.25)   # any cogno-synapse Embedder
result = await selector.select(
    noumeno.rewritten,                       # the canonical-English text (post-NOUMENO)
    candidates=await store.list(),
    base_persona_id="SECRETARY",
    intent_class=intent.intent_class,        # SOCIAL → base, no embedding
    restrict_to=identity.allowed_personas,   # N:N — compete only among allowed
)
result.persona_id, result.matched, result.score
```

Pure scoring (base penalty + inertia boost + threshold); the host owns candidate
loading and embedding caches (pass `candidate_vectors=` to skip re-embedding). For
a tenant with many *similar* personas, inject a `reranker=` (a `Reranker` Protocol —
a host-provided cross-encoder) to reorder the above-threshold shortlist; it is off
by default and unnecessary for small catalogs. See
[cognobench/ROUTING_BENCH_RESULTS.md](cognobench/ROUTING_BENCH_RESULTS.md).

### 5. `compose` — assemble the effective prompt

```python
from cogno_persona import compose_prompt

system = compose_prompt(vet, "system", base=GLOBAL_RULES,
                        context={"tenant_name": "PetCo"})
# → base + persona.system + mandatory custom_rules block, {placeholders} filled
```

Pure assembly only — channel brevity, language pins, correction feedback and the
like stay host concerns (append them yourself).

### 6. `capabilities` — the engine that appends what the agent may DO

A **capability** is a group of tools with a purpose and a way of composing them
("to cancel a reminder, list first to get the id, then cancel"). You declare yours
as data; the engine turns them into the block the execution prompt carries.

```python
from cogno_persona import Capability, render_capabilities, validate_capabilities

REFUND = Capability(
    name="refund", purpose="Refund an order the customer already paid for.", family="billing",
    variants=(                                   # strongest first — one heading, two strengths
        (frozenset({"issue_refund", "lookup_order"}),
         "## Refund duty\nCall `lookup_order` for the order id first, then `issue_refund`."),
        (frozenset({"issue_refund"}),
         "## Refund duty\nAsk the customer for the order id, then call `issue_refund`."),
    ))
assert validate_capabilities([REFUND]) == []      # a deploy blocker, not a test concern

out = render_capabilities([REFUND], offered={"issue_refund"})  # `lookup_order` masked this turn
out.text          # → the DEGRADED text: it never commands a tool the turn withholds
out.rendered      # → ("refund",)  what this turn was actually told it could do
out.unavailable   # → ()           what emitted and could render nothing, for the judge
```

**The engine is here; the table is yours.** Nothing in it knows a capability's name,
family or text — which capabilities exist is product content, and the gates
(`emitting_capabilities(table, wired=..., emitting=...)`) are answers you pass in.
The defect it removes is a prompt that commands a tool the turn withholds: a variant
renders only when `requires ⊆ offered`, and when none fits, `unavailable` says what it
would have taken — the fact a judge needs to tell *"there was no tool"* from *"there was
a tool and it went unused"*.

### 7. `skills` — the finer binding, and the two rules that travel with it

`allowed_modules` binds a persona to whole verticals. `cogno_persona.skills` is the binding one
notch down — individual skills, bound to a persona and gated per tenant. Same division as
`capabilities`: the **mechanism** ships here, the **catalog** stays with the host. Nothing in
this module names a skill.

```python
from cogno_persona import (CORE_SCOPE, InMemoryPersonaSkillStore,
                           InMemoryTenantSkillStore, SkillInfo, TenantSkill, skill_tier)

skill_tier(SkillInfo(id="x", is_premium=True))                  # "premium"
skill_tier(SkillInfo(id="x", is_premium=True, is_default=True))  # "" — two gates, not one

tenant = InMemoryTenantSkillStore()
await tenant.enable("acme", "x", can_guest=True)   # → True: something actually changed
await tenant.disable("acme", "x")                  # the row STAYS, switched off

bindings = InMemoryPersonaSkillStore()
await bindings.set_skills(CORE_SCOPE, "secretary", ["x", "y"])   # global, every tenant
await bindings.set_skills("acme", "secretary", ["z"])            # one tenant's extra
await bindings.set_skills(CORE_SCOPE, "secretary", [])           # PersonaSkillClearRefused
```

Both rules are here because a caller got each wrong in production, and neither defect is visible
on the happy path:

- **A row survives being switched off.** Deleting on disable made "the admin turned this off"
  and "this was never seeded" the same state in the database, so every backfill was guessing —
  three attempts, three different defects.
- **A full sync of the empty set is a full DELETE.** An admin panel that loaded a persona's
  bindings lazily, and saved from a different tab, posted the set it had never read: `[]`. Five
  bindings to zero, green toast. `refuses_clear` is that decision, pure and shared, so the API
  route, the seed, the migration and the script nobody has written yet cannot each get it wrong
  alone. A caller that MEANT to clear passes `allow_clear=True` and is obeyed.


### 8. `config_keys` — configuration read by the model AND by the tools, from ONE declaration

`custom_rules` is prose, and prose has exactly one reader: the model. A tool that needs the
same fact — the hourly rate, the column a total lives in, a threshold — cannot ask for it by
name. A declared key has **two** readers and they are the same declaration, not a copy.

```python
from cogno_persona import Persona, compose_prompt, config_values, sanitize_config_keys

kept, dropped = sanitize_config_keys(
    '[{"name": "PAY_RATE_PER_HOUR", "value": "120,00", "type": "number",
       "label": "Valor/hora do professor"}]')
assert dropped == ()                       # the door names what it refuses, and never raises

vet = Persona(persona_id="coordinator", config_keys=kept, prompts={"system": "..."})

config_values(vet.config_keys)["PAY_RATE_PER_HOUR"]   # READING 1 — what a TOOL asks, by name
"PAY_RATE_PER_HOUR" in compose_prompt(vet, "system")  # READING 2 — what the MODEL reads
```

`render_config_keys` is **expressed over** `config_values`: the prompt block asks for the
by-name mapping and renders what came back, so a key that leaves one reading leaves the other
in the same edit. That is structural, not a convention a reviewer has to enforce.

The types (`text | number | boolean`) are a promise the door checks: a `number` that does not
parse is refused **at save time**, in front of whoever is typing it, instead of at question
time as "not configured" in front of a contact.

**A key is a scalar; long content is knowledge.** `MAX_CONFIG_VALUE_CHARS` is 200 and it is
enforced — an over-long value is dropped with reason `too_long` and named back, so a host's
admin API can refuse it. The number is measured: in the production row this came from, the
longest declared value is 27 characters and configuration is **5.4%** of a 13 187-character
blob. The other 94.6% is what a knowledge base is for.

## Design

| Principle | How |
|---|---|
| Declaration, not execution | `allowed_modules` is names; the host runs tools (praxis) |
| Declared, not inferred | `domains` says what a persona OWNS; a tool list is not a subject |
| Infra-agnostic | no CoreDB / channel / env; the host loads & injects |
| Runtime-light | one dep (`pydantic`); `Embedder` is type-only from cogno-synapse |
| Aligned to anima | the four slots match the stage signatures exactly |
| Pure helpers | loader/selector/compose/capabilities have no I/O beyond reading prompt files |
| Engine, not content | the capability ENGINE ships here; the TABLE of capabilities is the host's |
| One declaration, two readings | `render_config_keys` is expressed over `config_values`, so prompt and tool cannot drift |

See [docs/HOST_INTEGRATION.md](docs/HOST_INTEGRATION.md) and [LOGGING.md](LOGGING.md).

## The Cogno ecosystem

`cogno-persona` is one organ of **[Cogno](https://github.com/sudoers-ai)** — a family of
small, composable, Apache-2.0 libraries that together form a complete
conversational-agent platform. Each library owns a single concern and stays
infra-agnostic; a **host** assembles them into a running agent:

![The Cogno ecosystem](docs/assets/cogno-ecosystem.svg)

The open-source libraries are the organs; the **host is the body** that joins
them. Our reference host — `cogno-host`, with its `cogno-ui` dashboard — is the
private product layer, but it holds no special powers: everything it does rides
on the public seams documented in each library's `docs/HOST_INTEGRATION.md`, so
you can assemble a body of your own.

## Development

```bash
pip install -e ".[dev]"
ruff check cogno_persona tests examples
mypy cogno_persona
pytest tests/unit -q --cov=cogno_persona
```

## License

Apache-2.0
