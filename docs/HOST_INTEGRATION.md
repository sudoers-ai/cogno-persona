# Host integration — cogno-persona

cogno-persona models **who an agent is** (prompts + binding + rules). It does not
talk to your DB, run tools, or read the environment — the host owns all of that and
injects personas into the cogno-anima pipeline. This guide shows the seams.

## 1. Where personas live

Two options, both behind the `PersonaStore` port (`async get(id)` / `async list()`):

- **From disk** — a directory of persona subdirectories, each with a `persona.json`
  manifest and `system.txt` / `scope.txt` / `limits.txt` / `voice.txt`:

  ```
  personas/
    SECRETARY/   persona.json  system.txt  scope.txt  limits.txt  voice.txt
    VETERINARY/  persona.json  system.txt  …  voice_meta.json   # optional versions
  ```
  ```python
  from cogno_persona import FilePersonaStore
  store = FilePersonaStore("personas/")
  ```

- **From your DB** — implement the port over your tables (the parent's
  `tenant_personas` columns map directly: `persona_id`, `description`,
  `mcp_module` → `allowed_modules`, `custom_rules`, `is_text_only` → `text_only`):

  ```python
  class CoreDBPersonaStore:
      def __init__(self, db, tenant_id): ...
      async def get(self, persona_id):
          row = await self._db.get_persona(self._tenant_id, persona_id)
          return Persona(persona_id=row["persona_id"], description=row["description"],
                         allowed_modules=[row["mcp_module"]] if row["mcp_module"] else [],
                         custom_rules=row.get("custom_rules", ""),
                         text_only=row.get("is_text_only", False),
                         prompts=load_persona_prompts(row)) or None
      async def list(self): ...
  ```

## 2. Selecting the active persona

For a multi-persona tenant, route the user's query to a specialist by embedding.
The host owns the embedder (and its cache) and the candidate list:

```python
from cogno_persona import PersonaSelector

selector = PersonaSelector(embedder, threshold=0.25)   # cogno-synapse Embedder

result = await selector.select(
    query=user_text,
    candidates=await store.list(),
    base_persona_id="SECRETARY",          # fallback when nothing clears threshold
    current_persona_id=session.active,    # conversational inertia
    apply_base_penalty=(intent_class in {"ACTION_REQUEST", "INFORMATION_REQUEST"}),
    correction_decay=prior_superego_rejections,
)
active = await store.get(result.persona_id)
```

**Caching embeddings:** re-embedding every description per turn is wasteful. Either
wrap the embedder in `cogno_synapse.CachingEmbedder`, or precompute once and pass
`candidate_vectors={persona_id: vec}` to `select()`. The selector itself is a pure
function of its inputs — the TTL cache the parent kept per tenant is your job.

## 3. Composing prompts for the pipeline

Build the four prompts and hand them to the anima stages. `compose_prompt` does the
*pure* part (base + slot + mandatory custom rules + `{placeholder}` substitution);
append any host-specific sections yourself.

```python
from cogno_persona import compose_prompt

ctx = {"tenant_name": tenant.name, "identity_label": user.label}

system_prompt = compose_prompt(active, "system", base=GLOBAL_RULES, context=ctx)
scope_prompt  = compose_prompt(active, "scope",  context=ctx)
limits_prompt = compose_prompt(active, "limits", context=ctx)
voice_prompt  = compose_prompt(active, "voice",  context=ctx)

# host-specific tails the lib deliberately omits:
if channel in ("whatsapp", "telegram"):
    system_prompt += MOBILE_BREVITY_BLOCK
if force_language:
    voice_prompt += f"\n\n[[ Respond strictly in {force_language}. ]]"

# inject into the pipeline:
await ego.process(ctx_obj, backend, dispatcher, system_prompt=system_prompt)
await superego.check_input_scope(ctx_obj, backend, scope_prompt=scope_prompt)
await superego.evaluate(ctx_obj, backend, limits_prompt=limits_prompt)
await superego.voice(ctx_obj, backend, voice_prompt=voice_prompt)
```

## 3b. Appending capabilities to the execution prompt

The execution prompt says *who the agent is*; a **capability** block says *what it may
do this turn, and how*. Declare your capabilities as data and let the engine assemble
the block — it renders a variant only when every tool that variant's text names is on
the turn's real tool surface, which is what stops a prompt commanding a tool the turn
withholds.

```python
from cogno_persona import (Capability, emitting_capabilities, render_capabilities,
                           validate_capabilities)

CAPABILITIES = (Capability(...), ...)          # YOUR table — product content
errors = validate_capabilities(CAPABILITIES)   # fail the import, loudly, if malformed
if errors:
    raise ValueError("; ".join(errors))

# 1. gates — YOUR answers: what the deployment was built with, what this turn offers
caps = emitting_capabilities(CAPABILITIES, wired=families_wired, emitting=families_offered)

# 2. selection + assembly, against the REAL surface (RBAC-scoped, read-only-masked, …)
out = render_capabilities(caps, offered=tool_names_on_the_dispatcher)

system_prompt = f"{system_prompt}\n\n{out.text}" if out.text else system_prompt
trace["capabilities"] = out.rendered            # what this turn was told it could do
judge_metadata["unavailable"] = [               # …and what it had no tool for
    {"capability": m.capability, "missing": list(m.missing)} for m in out.unavailable]
```

Three things stay yours by design:

- **the table** — which capabilities exist, their families, their prompt text;
- **the gates** — `wired`/`emitting`/`offered` are answers, computed from your wiring,
  your RBAC and your dispatcher. The engine never reads a gate, and a gate never reads
  the table;
- **the tail** — `render_capabilities(..., suffixes={"name": text})` appends per-turn
  data the static table cannot hold (a list of what is reachable right now, say).

Give `unavailable` to whatever judges the reply. Without it a judge cannot tell *"there
was no tool"* from *"there was a tool and it went unused"* — both look like *(no tools
executed)*, and only one of them makes *"I can't do that"* an honest answer.

## 4. Versioning prompts

Drop a `<name>_meta.json` next to a prompt to A/B or roll back without renaming:

```json
{ "current": "voice.txt",
  "versions": { "v1": {"file": "voice_v1.txt"}, "v2": {"file": "voice.txt"} } }
```

Pin a version per request (`load_persona(dir, version="v1")`,
`FilePersonaStore(root, version="v1")`) and introspect with `list_versions` /
`current_version`.

## 5. The binding is by name (persona ≠ praxis)

`allowed_modules` is an opaque list of **names** (e.g. `["veterinary"]`). cogno-persona
never imports or runs them. The host resolves each name into a `ToolDispatcher` for
the EGO. This keeps the light declaration lib decoupled from the heavy,
infra-bound execution layer (cogno-praxis).

## 6. What cogno-persona does NOT do (host)

- **DB/cache** for personas (you implement `PersonaStore`).
- **Embedding** and its caching/TTL (you inject the embedder).
- **Tool execution / MCP / RBAC** — that is praxis + the EGO dispatcher.
- **The capability TABLE** — the engine assembles blocks; which capabilities exist,
  what they say and which gates they ride are yours.
- **Channel brevity, language pins, correction feedback, UI manuals** — append to
  the composed prompts yourself.
- **Reading env / `COGNO_*` vars** — pass values via `context=` / constructor args.
