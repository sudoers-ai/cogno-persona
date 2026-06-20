# Persona routing bench — results

`python3 cognobench.py` scores the `PersonaSelector` on 12 curated cases (a base
`SECRETARY` + 3 specialists; EN + PT-BR queries). Run `--stub` for a deterministic
keyword embedder (no network) or the default for a real Ollama embedder.

## Baselines

| Embedder | Accuracy | Notes |
|---|---|---|
| stub (keyword one-hot) | **12/12 = 100%** | plumbing guard; a unit smoke asserts this |
| Ollama `nomic-embed-text` (threshold 0.25) | **10/12 = 83.3%** | see failure modes below |

## Failure modes (Ollama `nomic-embed-text`, 2026-06-20)

1. **Cross-lingual miss** — `"meu cachorro está vomitando e não quer comer"`
   routed to **RESTAURANT (0.47)** over VETERINARY (0.45). PT query vs EN
   descriptions: the correct specialist scored just *below* a competitor. This is
   the embedding model's weak cross-lingual range, not a selector bug — it is the
   reason the default threshold is a low 0.25.

2. **Generic greeting hijacked** — `"bom dia, tudo bem?"` routed to
   **RESTAURANT (0.49)** instead of the SECRETARY base. A social greeting cleared
   the 0.25 threshold against a specialist by noise.

## Mitigations (host policy — the core only signals)

- **Skip the selector for SOCIAL/greeting intent** (route straight to base), as the
  parent did off NER `intent_class`. Failure #2 disappears entirely. The pure
  selector deliberately leaves this to the host (`select()` is only called when the
  host wants routing).
- **Use a stronger multilingual embedding model** for PT↔EN tenants — `nomic-embed-text`
  is weak cross-lingually; this lifts failure #1.
- **Calibrate the threshold** with `--threshold`; note there is no single value that
  fixes both (raising it to drop the greeting also drops a legit 0.45 specialist) —
  the real lever is model quality + the SOCIAL skip.

The integration test (`tests/integration/test_selector_live.py`) gates the clear
English specialist cases exactly and the overall accuracy at a **75% floor** to
catch regressions without being flaky on the known cross-lingual cases.
