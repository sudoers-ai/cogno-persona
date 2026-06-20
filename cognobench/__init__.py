"""
cognobench — persona-routing quality benchmark for cogno-persona.

cogno-persona has exactly one cognitive surface: the embedding-based
``PersonaSelector`` that routes a user query to the right specialist. This bench
scores that routing on a curated set of ``(query → expected persona)`` cases, the
same way cogno-core/cogno-engram benchmark their cognitive stages.

Kept **decoupled** from the library and **out of the wheel** (``packages.find``
only includes ``cogno_persona*``). Run it two ways:

* ``--stub`` — a deterministic keyword embedder (no network); guards the plumbing
  in CI and must score 100% (a smoke test asserts this).
* default — a real Ollama embedder via cogno-synapse, to measure true routing
  accuracy / calibrate the threshold.
"""
