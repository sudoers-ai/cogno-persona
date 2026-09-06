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
pip install cogno-persona          # model + loader + store + selector + compose + capabilities
pip install "cogno-persona[yaml]"  # + YAML frontmatter parsing in prompts
```

## Six pieces

### 1. `Persona` — the typed container (pydantic)

```python
from cogno_persona import Persona, PersonaPrompts

vet = Persona(
    persona_id="VETERINARY",
    description="pet health specialist",
    allowed_modules=["veterinary", "scheduler"],   # by-name binding (host resolves)
    custom_rules="Always confirm the pet's name first.",
    prompts=PersonaPrompts(system="You are the vet…", scope="…", limits="…", voice="…"),
)
vet.primary_module          # "veterinary"
vet.prompt("voice")         # the voice prompt text
```

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

## Design

| Principle | How |
|---|---|
| Declaration, not execution | `allowed_modules` is names; the host runs tools (praxis) |
| Infra-agnostic | no CoreDB / channel / env; the host loads & injects |
| Runtime-light | one dep (`pydantic`); `Embedder` is type-only from cogno-synapse |
| Aligned to anima | the four slots match the stage signatures exactly |
| Pure helpers | loader/selector/compose/capabilities have no I/O beyond reading prompt files |
| Engine, not content | the capability ENGINE ships here; the TABLE of capabilities is the host's |

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
