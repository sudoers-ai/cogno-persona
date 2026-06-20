"""
Integration: PersonaSelector + FilePersonaStore against a **real Ollama embedder**.

The unit suite uses a deterministic stub embedder, so the actual embedding-routing
path (cogno-synapse OllamaEmbedder → cosine → threshold) is never exercised. These
tests route real queries through a live embedder and load personas from disk.

Auto-skips unless cogno-synapse is importable AND Ollama serves the embed model.
Override with ``COGNO_TEST_OLLAMA_EMBED_MODEL`` / ``OLLAMA_BASE_URL``.
"""

import json
import os

import pytest

pytest.importorskip("cogno_synapse")

import httpx  # noqa: E402

from cogno_persona import FilePersonaStore, PersonaSelector, load_persona  # noqa: E402
from cogno_synapse import OllamaEmbedder  # noqa: E402
from cogno_synapse.cache import CachingEmbedder  # noqa: E402

from cognobench.routing_cases import BASE_ID, CATALOG  # noqa: E402

BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
EMBED_MODEL = os.getenv("COGNO_TEST_OLLAMA_EMBED_MODEL", "nomic-embed-text")


def _has_embed_model() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/api/tags", timeout=3)
        r.raise_for_status()
        base = EMBED_MODEL.split(":", 1)[0]
        return any(t["name"].split(":", 1)[0] == base for t in r.json().get("models", []))
    except Exception:
        return False


requires_embed = pytest.mark.skipif(
    not _has_embed_model(), reason=f"Ollama embed model {EMBED_MODEL} unavailable"
)


def _embedder() -> CachingEmbedder:
    return CachingEmbedder(OllamaEmbedder(model=EMBED_MODEL, base_url=BASE_URL))


@requires_embed
@pytest.mark.parametrize("query,expected", [
    ("my dog has been vomiting since yesterday", "VETERINARY"),
    ("what's my current account balance and unpaid invoices?", "BOOKKEEPER"),
    ("I'd like to reserve a table for four tonight", "RESTAURANT"),
])
async def test_routes_clear_english_specialists(query, expected):
    selector = PersonaSelector(_embedder())
    res = await selector.select(query, CATALOG, base_persona_id=BASE_ID)
    assert res.persona_id == expected
    assert res.matched is True
    assert res.score >= selector.threshold


@requires_embed
async def test_overall_accuracy_floor():
    # Full suite = the single-tenant cases + the ported parent-bench tenant cases
    # (multitenant_cases.py 16b). With English (post-NOUMENO) queries + the SOCIAL
    # skip, nomic-embed-text routes them at 100%. Floor at 90% to catch regressions
    # without being brittle to one-off embedding drift (see ROUTING_BENCH_RESULTS.md).
    from cognobench.routing_cases import ALL_CASES
    from cognobench.runner import run_bench
    report = await run_bench(_embedder(), cases=ALL_CASES)
    assert report.accuracy >= 90.0, f"routing accuracy regressed to {report.accuracy:.1f}%"


@requires_embed
async def test_store_load_then_route(tmp_path):
    # Realistic host flow: personas on disk → FilePersonaStore → selector.
    for p in CATALOG:
        d = tmp_path / p.persona_id
        d.mkdir()
        (d / "persona.json").write_text(json.dumps({
            "persona_id": p.persona_id,
            "description": p.description,
            "allowed_modules": p.allowed_modules,
        }), encoding="utf-8")
        (d / "system.txt").write_text(f"You are {p.persona_id}.", encoding="utf-8")

    store = FilePersonaStore(tmp_path)
    candidates = await store.list()
    assert {p.persona_id for p in candidates} == {p.persona_id for p in CATALOG}

    selector = PersonaSelector(_embedder())
    res = await selector.select("my cat needs a vaccine", candidates, base_persona_id=BASE_ID)
    assert res.persona_id == "VETERINARY"

    # the loaded persona carries its prompt + binding
    vet = await store.get("VETERINARY")
    assert load_persona(tmp_path / "VETERINARY").prompt("system") == "You are VETERINARY."
    assert vet.allowed_modules == ["veterinary"]
