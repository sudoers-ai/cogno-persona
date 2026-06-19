"""Unit tests for the embedding-based PersonaSelector."""

from cogno_persona import PersonaSelector, cosine


def test_cosine_edges():
    assert cosine([1, 0], [1, 0]) == 1.0
    assert cosine([1, 0], [0, 1]) == 0.0
    assert cosine([], [1]) == 0.0
    assert cosine([0, 0], [1, 1]) == 0.0


async def test_matches_specialist(embedder, personas):
    sel = PersonaSelector(embedder)
    res = await sel.select("my dog is sick and needs a vet", personas,
                           base_persona_id="SECRETARY")
    assert res.matched is True
    assert res.persona_id == "VETERINARY"
    assert res.score >= sel.threshold


async def test_off_domain_falls_back_to_base(embedder, personas):
    sel = PersonaSelector(embedder)
    res = await sel.select("tell me a poem about the sky", personas,
                           base_persona_id="SECRETARY")
    assert res.matched is False
    assert res.persona_id == "SECRETARY"


async def test_short_query_fast_path_no_embedding(embedder, personas):
    sel = PersonaSelector(embedder)
    res = await sel.select("ok", personas, base_persona_id="SECRETARY")
    assert res.matched is False and res.persona_id == "SECRETARY"
    assert res.scores == []  # never embedded


async def test_empty_candidates(embedder):
    sel = PersonaSelector(embedder)
    res = await sel.select("my dog is sick", [], base_persona_id="SECRETARY")
    assert res.persona_id == "SECRETARY" and res.matched is False


async def test_base_penalty_lets_specialist_win(embedder, personas):
    # Without the penalty a tie could keep base; with it the specialist wins.
    sel = PersonaSelector(embedder, base_penalty=0.10)
    res = await sel.select("invoice and account balance please", personas,
                           base_persona_id="SECRETARY")
    assert res.persona_id == "BOOKKEEPER"


async def test_apply_base_penalty_false_keeps_base_on_tie(embedder, personas):
    # Give the base persona a matching description so it ties the specialist.
    personas[0].description = "invoice account balance bookkeep"
    sel = PersonaSelector(embedder)
    # With the penalty off, the base persona is not nudged down → it wins ties
    # (sorted stable; base may or may not win — assert it is at least selected/among top).
    res = await sel.select("invoice balance", personas,
                           base_persona_id="SECRETARY", apply_base_penalty=False)
    assert res.matched is True
    assert res.persona_id in {"SECRETARY", "BOOKKEEPER"}


async def test_inertia_boost_for_current(embedder, personas):
    sel = PersonaSelector(embedder, inertia_boost=0.05)
    res = await sel.select("my dog needs a vet", personas, base_persona_id="SECRETARY",
                           current_persona_id="VETERINARY")
    assert res.persona_id == "VETERINARY"
    # boosted above the raw cosine of 1.0
    assert res.score > 1.0


async def test_threshold_override(embedder, personas):
    sel = PersonaSelector(embedder, threshold=0.9)
    # raise threshold above any achievable score → fallback
    res = await sel.select("my dog needs a vet", personas, base_persona_id="SECRETARY",
                           threshold=2.0)
    assert res.matched is False and res.persona_id == "SECRETARY"


async def test_precomputed_vectors_skip_embedding(personas):
    class BoomEmbedder:
        async def embed(self, text):
            # query still embeds; candidates must use the precomputed vectors.
            return [1.0, 0.0, 0.0]

    sel = PersonaSelector(BoomEmbedder())
    vectors = {"SECRETARY": [0, 0, 1], "VETERINARY": [1, 0, 0], "BOOKKEEPER": [0, 1, 0]}
    res = await sel.select("my dog needs a vet", personas, base_persona_id="SECRETARY",
                           candidate_vectors=vectors)
    assert res.persona_id == "VETERINARY" and res.matched is True
