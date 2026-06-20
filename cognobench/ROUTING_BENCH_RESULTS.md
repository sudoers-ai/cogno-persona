# Persona routing bench — results

`python3 cognobench.py` scores the `PersonaSelector` on 12 curated cases (a base
`SECRETARY` + 3 specialists). Run `--stub` for a deterministic keyword embedder
(no network) or the default for a real Ollama embedder.

**The queries are canonical English** — the text the selector actually sees in the
pipeline, since NOUMENO rewrites every input to English *before* routing. Cases
keep their pre-NOUMENO `original` (PT) for documentation; the `SOCIAL` greeting
case carries `intent="SOCIAL"` to exercise the non-routing short-circuit.

## Baselines

| Embedder | Accuracy | Notes |
|---|---|---|
| stub (keyword one-hot) | **12/12 = 100%** | plumbing guard; a unit smoke asserts this |
| Ollama `nomic-embed-text` (threshold 0.25) | **12/12 = 100%** | realistic (English) input + SOCIAL skip |

## Why an earlier run showed 83%

The first cut fed **raw Portuguese** queries — unrealistic, because the selector
receives `noumeno.rewritten` (English). With English input the two misses vanish:

- The PT veterinary query that lost by 0.02 (RESTAURANT 0.47 vs VET 0.44) becomes
  `"my dog is vomiting and refuses to eat"` → **VETERINARY 0.54**, a clean win.
- The greeting `"bom dia"` that a specialist hijacked at 0.49 now carries
  `intent="SOCIAL"` → the selector **skips embedding entirely** → base.

So for the common case — **a small catalog of distinct personas, English input** —
plain cosine routing saturates. This matches the product reality: many tenants,
most with few personas.

## Levers (host policy — the core only signals)

- **`intent_class`** — pass the NER intent; `SOCIAL` (configurable
  `non_routing_intents`) routes straight to base, no embedding cost.
- **`restrict_to`** — when an identity is allowed only a subset of personas (N:N),
  competition is limited to that set.
- **`reranker`** — an optional injected cross-encoder reorders the above-threshold
  shortlist. **Default off; not needed for small catalogs.** Build a concrete
  reranker only for a tenant with many *similar* personas (mirror cogno-engram's
  reranker; note the recurring per-turn model-call cost). A lexical BM25 hybrid was
  evaluated and **dropped** — its IDF is degenerate over a handful of short
  descriptions. See the `persona-routing-quality` design note.

The integration test gates the clear specialist cases exactly and overall accuracy
at a **90% floor** to catch regressions without being brittle to embedding drift.
